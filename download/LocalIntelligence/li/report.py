"""Relatório em Markdown (legível por humanos e por outros modelos do parque) a partir do estado atual."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import PROTOCOLO, config, decide, offline, papeis, parque, scout
from .ollama import Ollama
from .util import dias_desde, fmt_gb


def _tps(t) -> str:
    return "?" if not t else f"{t[0]:g}–{t[1]:g}".replace(".", ",")


def _ic(ic) -> str:
    return f" (±{(ic[1] - ic[0]) / 2:.0f})" if ic else ""


def gerar_markdown(oll: Optional[Ollama]) -> str:
    mesa = decide.mesa_de_decisao(oll)
    snap = scout.ultimo()
    pk = parque.carregar_parque(True)
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    L: List[str] = [f"# Decisão de modelos locais — {hoje}", "",
                    f"> {mesa['manchete']['texto']}", "",
                    f"Protocolo de benchmark **{PROTOCOLO}**. Três níveis de evidência, nunca misturados: **medido** (rodou aqui, com intervalo de confiança), "
                    "**estimado** (conta de memória/velocidade com arquivos reais) e **prioridade** (heurística de 'vale testar?' — não é nota de qualidade).", ""]
    boss = mesa.get("boss")
    if boss:
        g = boss.get("gpu") or {}
        L += ["## Hardware desta máquina", "",
              f"- {boss.get('cpu')} · {boss.get('ram_gb')} GB RAM · {g.get('nome')} {g.get('vram_gb')} GiB (banda {g.get('bw_gbs')} GB/s)", ""]
    L += ["## Melhor modelo por uso (medido)", "", "| Uso | Modelo atual | Nota | tok/s | Memória | Contexto 100% GPU |", "|---|---|---:|---:|---:|---:|"]
    por_id = {m["id"]: m for m in mesa["instalados"]}
    for p in papeis.PAPEIS:
        mid = mesa["titulares"].get(p["id"])
        m = por_id.get(mid) if mid else None
        if p.get("sem_nota"):
            L.append(f"| {p['icone']} {p['rotulo']} | {mid or '—'} | só capacidade | | | |")
            continue
        r = ((m or {}).get("medido") or {}).get("papeis", {}).get(p["id"]) or {}
        s = (m or {}).get("sonda") or {}
        L.append(f"| {p['icone']} {p['rotulo']} | {mid or '—'} | {r.get('nota', '—')}{_ic(r.get('ic'))} | {((m or {}).get('medido') or {}).get('tps_mediana', '—')} | "
                 f"{fmt_gb(m['bytes']) if m else '—'} | {s.get('ctx_max_gpu') or '—'} |")
    L += ["", "Nota de 0–100 = média ponderada de acertos nos testes daquela função; o ± é metade do intervalo de confiança de ~90%. "
          "Diferenças menores que o ± são ruído.", ""]
    L += ["## Medições por modelo", ""]
    for m in mesa["instalados"]:
        r = m.get("medido")
        if not r:
            L.append(f"### {m['id']}\n\n_Sem medição no protocolo {PROTOCOLO}._\n")
            continue
        L += [f"### {m['id']} ({fmt_gb(m['bytes'])}, {m.get('quant')})", "",
              "| Teste | Acerto | n | IC 90% |", "|---|---:|---:|---|"]
        for s, v in sorted(r["suites"].items()):
            L.append(f"| {papeis.SUITES.get(s, s)} | {v['acc']}% | {v['n']} | {v['ic'][0]}–{v['ic'][1]}% |")
        L += ["", f"Velocidade mediana: **{r.get('tps_mediana')} tok/s**.", ""]
    if mesa["dispensaveis"]:
        L += ["## Instalados que podem sair (inferiores ou dominados)", ""] + [f"- `{d['modelo']}` — libera {d['liberaria']}: {d['motivo']}" for d in mesa["dispensaveis"]] + [""]
    L += ["## Desafiantes no radar para a RTX 5060 Ti", "",
          "_Prioridade ≠ qualidade. Só o teste (`python cli.py testar <id>`) responde se vale trocar._", ""]
    for p in papeis.PAPEIS:
        lst = mesa["desafiantes"].get(p["id"]) or []
        if not lst:
            continue
        L.append(f"**{p['icone']} {p['rotulo']}**")
        for x in lst:
            v = x["encaixe"]["variante"]
            L.append(f"- {x['nome']} — prioridade {x['prioridade']['pontos']}/100 · {v['quant']} ({fmt_gb(v['bytes'])}) · cabe com contexto até {x['encaixe']['encaixe']['ctx_max']} · "
                     f"~{_tps(x['encaixe'].get('tps_est'))} tok/s (estimado) · `ollama pull {v['pull']}`")
        L.append("")
    L += ["## Recomendação por máquina do parque (estimado)", ""]
    for e in decide.recomendacoes_parque(snap, oll, por_maquina=2, com_broker=False):
        m = e["maquina"]
        L += [f"### {m['nome']} — {m['cpu']} · {m.get('ram_gb')} GB RAM" + (f" · {m['gpu']['nome']}" if m.get("gpu") else ""), ""]
        if not e["papeis"]:
            L += ["_Sem radar: rode `python cli.py radar`._", ""]
            continue
        for pid, lst in e["papeis"].items():
            if not lst:
                continue
            x = lst[0]
            v = x["encaixe"]["variante"]
            L.append(f"- **{papeis.POR_ID[pid]['rotulo']}**: {x['nome']} em {v['quant']} ({fmt_gb(v['bytes'])}) · ~{_tps(x['encaixe'].get('tps_est'))} tok/s · `ollama pull {v['pull']}`")
        L.append("")
    off = offline.estado(oll)
    L += ["## Prontidão offline", "", f"**{off['resumo']}**", ""]
    ic = {"ok": "✅", "atencao": "⚠️", "falta": "❌", "info": "ℹ️"}
    for i in off["itens"]:
        L.append(f"- {ic[i['status']]} {i['titulo']} — {i['detalhe']}" + (f" → {i['acao']}" if i.get("acao") else ""))
    L += ["", "## Limitações", "",
          "- Amostras pequenas (dezenas de itens por teste): por isso o painel diz 'empate técnico' em vez de coroar vencedor sem prova.",
          "- HumanEval mede funções Python curtas; não equivale a editar repositórios reais.",
          "- Velocidade e memória das máquinas SEM GPU são estimativas por banda de memória (±2×) até alguém medir lá.",
          f"- Radar atualizado há {round(dias_desde(snap['criado']) or 0, 1)} dias." if snap else "- Radar nunca rodou.", ""]
    return "\n".join(L)


def salvar(oll: Optional[Ollama], destino: Optional[Path] = None) -> Path:
    config.garantir_pastas()
    destino = destino or config.RELATORIOS / (datetime.now().strftime("%Y-%m-%d") + "-decisao.md")
    Path(destino).write_text(gerar_markdown(oll), encoding="utf-8")
    return Path(destino)
