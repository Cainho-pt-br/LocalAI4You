"""Gera uma nota Markdown com os modelos do parque a partir dos dados (reproduzível). Uso pessoal do autor; fica fora da ajuda."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from . import decide, fit, papeis, scout
from .ollama import Ollama
from .report import _ic, _tps
from .util import GB, fmt_gb


def _orcamento_gb(maq: dict) -> float:
    return fit.orcamento_bytes(maq) / GB


def gerar(oll: Optional[Ollama]) -> str:
    mesa = decide.mesa_de_decisao(oll)
    snap = scout.ultimo()
    hoje = datetime.now().strftime("%Y-%m-%d")
    L: List[str] = [
        "# Modelos Locais para o Parque de Máquinas", "",
        f"Quais modelos abertos rodar em cada máquina do parque, com tamanho exato, quantização e velocidade **medida** (só no `boss`) ou "
        f"**estimada** (nas demais) — recalculado em {hoje} pelo Local Intelligence ([[radar-de-modelos-locais]]), que substitui a versão "
        "anterior desta nota. Estado atual, não diário: quando o radar mudar, regenere com `python cli.py nota-parque`.", "",
        "## Como ler", "",
        "- **Medido** = rodou na máquina, no protocolo v2, com intervalo de confiança. **Estimado** = conta de memória/velocidade a partir do "
        "arquivo real do modelo; em CPU vale ±2× até alguém medir lá (`python deploy/medir-maquina.py --texto`).",
        "- **Prioridade** (0–100) só ordena o que vale testar (recência, porte, adoção, confiança do autor): **não é nota de qualidade**.",
        "- Os modelos locais não substituem Claude/Gemini/Codex do orquestrador ([[modelos-e-cerebro-compartilhado]]): são o plano B sem "
        "internet/cota e o trabalhador barato para lote.", ""]
    boss = mesa.get("boss")
    if boss:
        g = boss.get("gpu") or {}
        L += [f"## 1. `boss` — {boss.get('cpu')} · {boss.get('ram_gb')} GB RAM · {g.get('nome')} {g.get('vram_gb')} GiB", "",
              "### Modelos instalados (medido)", "",
              "| Uso | Modelo atual | Nota | tok/s | Memória | Contexto 100% GPU |", "|---|---|---:|---:|---:|---:|"]
        por_id = {m["id"]: m for m in mesa["instalados"]}
        for p in papeis.PAPEIS:
            mid = mesa["titulares"].get(p["id"])
            m = por_id.get(mid) if mid else None
            if p.get("sem_nota") or not m:
                continue
            r = ((m.get("medido") or {}).get("papeis") or {}).get(p["id"]) or {}
            s = m.get("sonda") or {}
            L.append(f"| {p['rotulo']} | `{mid}` | {r.get('nota', '—')}{_ic(r.get('ic'))} | {(m.get('medido') or {}).get('tps_mediana', '—')} | "
                     f"{fmt_gb(m['bytes'])} | {s.get('ctx_max_gpu') or '—'} |")
        L += ["", "Notas de 0–100 por função; o ± é metade do intervalo de confiança de ~90%. **Empate técnico** é comum e significa "
              "'mantenha o que já está instalado'. Detalhe por modelo e por teste: relatório do dia em `relatorios/`.", ""]
        L += ["### Desafiantes que cabem na RTX 5060 Ti (estimado — o teste decide)", ""]
        vistos = set()
        for p in papeis.PAPEIS:
            for x in (mesa["desafiantes"].get(p["id"]) or [])[:2]:
                if x["id"] in vistos:
                    continue
                vistos.add(x["id"])
                v = x["encaixe"]["variante"]
                L.append(f"- **{x['nome']}** ({p['rotulo']}) — prioridade {x['prioridade']['pontos']}/100 · `{v['quant']}` "
                         f"{fmt_gb(v['bytes'] + int(v.get('extra_bytes', 0)))} · contexto até {x['encaixe']['encaixe']['ctx_max'] // 1024}k · "
                         f"~{_tps(x['encaixe'].get('tps_est'))} tok/s · `ollama pull {v['pull']}`")
        L.append("")
    recs = decide.recomendacoes_parque(snap, oll, por_maquina=2, com_broker=True)
    L += ["## 2. Demais máquinas (sem GPU) — recomendação estimada", ""]
    for e in recs:
        m = e["maquina"]
        if (m.get("gpu") or {}).get("vram_gb"):
            continue
        L += [f"### {m['nome']} — {m['cpu']} · {m.get('ram_gb')} GB RAM", "",
              f"**Classe {e.get('classe')}.** {e.get('nota')} Limite para modelo+contexto: ~{_orcamento_gb(m):.1f} GB. "
              f"Instruções: {', '.join(m.get('simd') or []) or '?'}. {m.get('notas', '')}", ""]
        if e.get("kit"):
            L.append("Instalar o essencial:")
            for k in e["kit"]:
                x = k["candidato"]
                v = x["encaixe"]["variante"]
                L.append(f"- **{x['nome']}** — {k['para']} · `{v['quant']}` {fmt_gb(v['bytes'])} · ~{_tps(x['encaixe'].get('tps_est'))} tok/s "
                         f"(estimado) · `ollama pull {v['pull']}`")
            L.append("")
        if e["papeis"]:
            L += ["| Função | 1ª opção | 2ª opção |", "|---|---|---|"]
            for pid, lst in e["papeis"].items():
                if not lst:
                    continue
                cel = [f"{x['nome']} `{x['encaixe']['variante']['quant']}` ({fmt_gb(x['encaixe']['variante']['bytes'])}, "
                       f"~{_tps(x['encaixe'].get('tps_est'))} tok/s)" for x in lst[:2]]
                L.append(f"| {papeis.POR_ID[pid]['rotulo']} | {cel[0]} | {cel[1] if len(cel) > 1 else '—'} |")
            L.append("")
    L += ["## Correções em relação à versão anterior desta nota", "",
          "- A quantização `IQ3_M` do Qwen 3.8 27B **não existe** no repositório da unsloth (o registro responde 400): as reais perto de 12 GB são "
          "`UD-IQ3_S` (12,0 GB) e `UD-Q3_K_XL` (13,1 GB) — e o projetor de visão (0,9 GB) também é baixado e entra na conta de memória.",
          "- As velocidades da versão anterior (35–45 tok/s no 27B; 12–18 tok/s num 4B no i5-7200U) não tinham medição por trás. Estimativa atual "
          "para o 27B em IQ3: 22–35 tok/s; um 4B no i5-7200U: 2–5 tok/s. **Medir antes de depender.**",
          "- Que 'o Ollama aborta com Illegal instruction em CPU sem AVX2' não procede nas versões atuais: o Ollama 0.35 traz backends de CPU por "
          "instrução (`sse42`, `sandybridge`, `ivybridge`, `haswell`…). Confirmar na máquina; llama.cpp é o plano B.",
          "- Quantizações abaixo de ~3 bits por peso não são mais recomendadas (perda perceptível); prefira um modelo menor em Q4.", "",
          "## Como confirmar nas máquinas", "",
          "1. `python deploy/medir-maquina.py --texto` do projeto — CPU, RAM, instruções e banda de memória (arquivo único, só Python 3).",
          "2. Instalar o Ollama, `ollama pull` do modelo do 'essencial' e `ollama run <modelo> \"olá\"` para ver a velocidade real.",
          "3. Para uma nota comparável com a do boss: `OLLAMA_HOST=<máquina> python cli.py bench --nivel rapido` a partir do boss.", ""]
    return "\n".join(L)
