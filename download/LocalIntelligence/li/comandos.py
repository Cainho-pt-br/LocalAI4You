"""Comandos da CLI que dependem dos módulos maiores (radar, decisão, painel, offline…)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import PROTOCOLO, config, decide, desafio, offline, papeis, parque, report, scout
from .ollama import Ollama
from .util import agora_iso, fmt_gb, gravar_json


def _o(iniciar=True) -> Ollama:
    o = Ollama()
    if iniciar and not o.no_ar():
        print("Ollama fora do ar — iniciando…")
        if not o.iniciar_servidor():
            raise SystemExit("Não consegui iniciar o Ollama.")
    return o


def cmd_radar(a):
    snap = scout.varrer(forcar=a.forcar, ao_progredir=lambda s: print(" ", s), com_hf=not a.sem_hf)
    n = scout.novidades(snap)
    print(f"\n{snap['total']} candidatos (fontes: {snap['fontes']}).")
    por_id = {c["id"]: c for c in snap["candidatos"]}
    if n["primeira_varredura"]:
        print("Primeira varredura: ela vira a linha de base — nas próximas, 'novo' = o que não estava aqui.")
    else:
        print(f"Apareceram desde {n['desde']}: {len(n['apareceram'])}")
        for i in n["apareceram"][:15]:
            print("   +", por_id[i]["nome"], f"({por_id[i]['params_b']:g}B, {por_id[i].get('dias')} dias)")
    print(f"Lançados nos últimos {config.carregar()['radar_dias_novo']} dias: {len(n['lancamentos_recentes'])}")
    for i in n["lancamentos_recentes"][:12]:
        c = por_id[i]
        print(f"   • {c['nome']:<40} {c['params_b']:>6g}B  {c.get('confianca'):<14} {c.get('dias')} dias")


def cmd_decidir(a):
    o = _o(False)
    mesa = decide.mesa_de_decisao(o if o.no_ar() else None)
    print("\n" + "=" * 78 + f"\n  {mesa['manchete']['texto']}\n" + "=" * 78)
    print("\nSUA ESQUADRA (medido):")
    por_id = {m["id"]: m for m in mesa["instalados"]}
    for p in papeis.PAPEIS:
        mid = mesa["titulares"].get(p["id"])
        m = por_id.get(mid) if mid else None
        r = ((m or {}).get("medido") or {}).get("papeis", {}).get(p["id"]) or {}
        nota = f"nota {r['nota']}" if r.get("nota") is not None else ("capacidade" if p.get("sem_nota") else "sem nota")
        print(f"  {p['icone']} {p['rotulo']:<42} {mid or '—':<22} {nota}")
    if mesa["dispensaveis"]:
        print("\nPODEM SAIR: " + "; ".join(f"{d['modelo']} (libera {d['liberaria']}: {d['motivo']})" for d in mesa["dispensaveis"]))
    print("\nAÇÕES SUGERIDAS:")
    for ac in mesa["acoes"] or [{"titulo": "nenhuma", "detalhe": ""}]:
        print(f"  → {ac['titulo']}\n      {ac['detalhe']}")


def cmd_testar(a):
    o = _o()
    if not a.sim:
        pl = desafio.plano(a.candidato, a.papel, o)
        print(f"Vai baixar {pl['pull']} ({pl['tamanho']}, {pl['quant']}) e medi-lo no protocolo {PROTOCOLO}. Livre em disco: {pl['espaco_livre_gb']} GB.")
        if input("Continuar? [s/N] ").strip().lower() != "s":
            return
    v = desafio.testar(o, a.candidato, a.papel, a.nivel, lambda d: print(" ", d.get("msg", "")))
    print("\n" + v["resumo"])
    for pid, r in v["por_papel"].items():
        if r.get("nota_novo") is not None:
            print(f"  {papeis.POR_ID[pid]['rotulo']:<42} novo {r['nota_novo']} vs {r['titular']} {r['nota_titular']}  → {r['veredito']}  (IC dif {r['ic']})")


def cmd_baixar(a):
    o = _o()
    print(f"Baixando {a.modelo}…")
    o.baixar(a.modelo, lambda d: print(f"\r  {d['pct']}% · {d['mb_s']} MB/s   ", end="", flush=True))
    print("\nPronto.")


def cmd_remover(a):
    o = _o()
    if not a.sim and input(f"Apagar {a.modelo} do disco? [s/N] ").strip().lower() != "s":
        return
    o.remover(a.modelo)
    print("Removido.")


def cmd_offline(a):
    o = _o(False)
    if a.acao == "status":
        e = offline.estado(o if o.no_ar() else None)
        print(e["resumo"] + "\n")
        for i in e["itens"]:
            print(f"  [{i['status']:^7}] {i['titulo']}\n            {i['detalhe']}" + (f"\n            → {i['acao']}" if i.get("acao") else ""))
    elif a.acao == "exportar":
        if not a.destino:
            raise SystemExit("Use --destino <pasta>")
        modelos = a.modelo or [m["id"] for m in o.instalados()]
        r = offline.exportar_kit(a.destino, modelos, lambda d: print(f"\r  {d['msg']}   ", end="", flush=True))
        config.salvar({"backup_modelos_dir": a.destino})
        print(f"\nKit pronto em {r['destino']} ({fmt_gb(r['bytes'])}).")
    elif a.acao == "verificar":
        for m in (a.modelo or [x["id"] for x in o.instalados()]):
            r = offline.verificar_profundo(m, lambda d: print(f"\r  {d['msg']}   ", end="", flush=True))
            print(f"\n  {m}: {'íntegro' if r['ok'] else 'PROBLEMAS ' + str(r['ruins'])}")


def cmd_relatorio(a):
    o = _o(False)
    p = report.salvar(o if o.no_ar() else None)
    print("Relatório gravado em", p)


def cmd_parque(a):
    snap = scout.ultimo()
    if not snap:
        raise SystemExit("Rode `python cli.py radar` primeiro.")
    o = _o(False)
    for e in decide.recomendacoes_parque(snap, o if o.no_ar() else None, por_maquina=a.top, com_broker=not a.sem_broker):
        m = e["maquina"]
        print(f"\n### {m['nome']} — {m['cpu']} · {m.get('ram_gb')} GB" + (f" · {m['gpu']['nome']}" if m.get("gpu") else "") + f"  [{m.get('fonte')}]")
        for pid, lst in e["papeis"].items():
            for x in lst:
                v = x["encaixe"]["variante"]
                tps = x["encaixe"].get("tps_est")
                inst = "✓ " if x.get("instalado_como") else "  "
                print(f"  {papeis.POR_ID[pid]['rotulo']:<38} {inst}{x['nome']:<28} {v['quant']:<10} {fmt_gb(v['bytes']):>8}  ~{tps[0]:g}-{tps[1]:g} tok/s  prio {x['prioridade']['pontos']}  {v['pull']}" if tps else f"  {x['nome']} {v['quant']}")


def cmd_painel(a):
    from .server import servir
    servir(a.porta, not a.sem_navegador)


def cmd_vigia(a):
    """Rotina agendada: varre, lista o que há de novo e grava alerta + relatório curto. Não baixa nada."""
    snap = scout.varrer(forcar=True, ao_progredir=lambda s: print(" ", s))
    n = scout.novidades(snap)
    o = _o(False)
    inst = decide._instalados(o if o.no_ar() else None)
    destaques = []
    for maq in parque.carregar_parque(False)["maquinas"]:      # boss (GPU) e as máquinas pequenas: o que é ótimo para a Pi também vira alerta
        for p in papeis.PAPEIS:
            for x in decide.candidatos_para(maq, inst, snap, p["id"], limite=6):
                if not x["instalado_como"] and x["prioridade"]["pontos"] >= decide.LIMIAR_TESTAR and (x["novo"] or x["id"] in n["apareceram"]):
                    destaques.append({"id": x["id"], "nome": x["nome"], "papel": p["id"], "prioridade": x["prioridade"]["pontos"], "maquina": maq["id"],
                                      "dias": x["dias"], "quant": x["encaixe"]["variante"]["quant"], "gb": round(x["encaixe"]["variante"]["bytes"] / 1e9, 1)})
    vistos, uniq = set(), []
    for d in sorted(destaques, key=lambda d: -d["prioridade"]):
        if (d["id"], d["maquina"]) not in vistos:
            vistos.add((d["id"], d["maquina"]))
            uniq.append(d)
    alerta = {"em": agora_iso(), "apareceram": len(n["apareceram"]), "recentes": len(n["lancamentos_recentes"]), "destaques": uniq[:12],
              "texto": (f"{len(uniq)} desafiante(s) novo(s) valem teste: " + ", ".join(f"{d['nome']} ({d['maquina']})" for d in uniq[:5])) if uniq else "Nada novo que valha teste."}
    gravar_json(config.ESTADO / "alertas.json", alerta)
    print("\n" + alerta["texto"])
    if a.relatorio:
        print("Relatório:", report.salvar(o if o.no_ar() else None))


def cmd_migrar(a):
    """Resume o state.json do protocolo v1 (referência histórica; NÃO comparável com a nota v2)."""
    arq = Path(a.arquivo)
    if not arq.exists():
        raise SystemExit(f"{arq} não existe")
    s = json.loads(arq.read_text("utf-8"))
    mapa = {"MMLU-PT": "mmlu_pt", "MMLU-Pro sample": "mmlu_pro", "CAPITU pt-BR single-turn": "capitu", "IFEval subset": "ifeval",
            "BFCL V4 live/simple": "bfcl_prompt", "BFCL V4 live/multiple": "bfcl_prompt",
            "BFCL V4 native/simple": "bfcl_native", "BFCL V4 native/multiple": "bfcl_native"}
    out = {}
    for r in s.get("results", []):
        if not r.get("valid") or r.get("dataset") not in mapa:
            continue
        m = out.setdefault(r["model_id"], {})
        e = m.setdefault(mapa[r["dataset"]], [0, 0])
        e[0] += 1 if r["passed"] else 0
        e[1] += 1
    hist = {"origem": str(arq), "protocolo": "v1 (contexto 2048, num_predict 512, corretores antigos)", "importado_em": agora_iso(),
            "modelos": {k: {s_: {"k": v[0], "n": v[1], "acc": round(100 * v[0] / v[1], 1)} for s_, v in d.items()} for k, d in out.items()},
            "velocidade": {m["id"]: m.get("median_tps") for m in s.get("models", [])}}
    gravar_json(config.ESTADO / "historico_v1.json", hist)
    print(f"Histórico v1 resumido: {len(out)} modelos → estado/historico_v1.json")


def cmd_calculadora(a):
    """Exporta a calculadora de hardware como UM arquivo HTML (dados da última varredura embutidos): abre offline em qualquer navegador."""
    from datetime import date
    from . import calc
    o = _o(False)
    try:
        html = calc.html_autonomo(o if o.no_ar() else None, incluir_parque=a.com_parque)
    except RuntimeError as e:
        raise SystemExit(str(e))
    destino = Path(a.saida) if a.saida else config.RELATORIOS / f"calculadora-de-hardware-{date.today().isoformat()}.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    print(f"Calculadora gravada em {destino} ({destino.stat().st_size / 1e6:.1f} MB). Abra no navegador; funciona sem internet.")


def cmd_token(a):
    """Mostra o token desta máquina (para o painel controlador registrá-la). Segredo: não vai para o git."""
    print(config.token_painel())


def cmd_painel_remoto(a):
    """Libera este painel para o tailnet: aceita o host publicado pelo `tailscale serve` (com token ou login permitido)."""
    cfg = config.carregar()
    hosts = sorted(set(cfg["hosts_painel"]) | set(a.host or []))
    logins = sorted(set(cfg["logins_permitidos"]) | set(a.login or []))
    novo = {"hosts_painel": hosts, "logins_permitidos": logins}
    if a.id:
        novo["maquina_id"] = a.id
    config.salvar(novo)
    print("máquina:", a.id or cfg.get("maquina_id") or "(detectada pelo hostname)", "| hosts liberados:", hosts, "| logins:", logins)


def cmd_maquinas(a):
    from . import remoto
    if a.acao == "registrar":
        if not a.id or not a.token:
            raise SystemExit("Use: maquinas registrar <id> --token <token da outra máquina>")
        try:
            print("registrada:", remoto.registrar(a.id, a.token, a.url))
        except ValueError as e:
            raise SystemExit(str(e))
    elif a.acao == "remover":
        remoto.remover(a.id or "")
        print("removida.")
    elif a.acao == "importar":
        # o instalador imprime LI_ID/LI_TOKEN no log do job do broker: registra a máquina sem copiar o token à mão
        import re
        from .util import http_json
        if not a.id:
            raise SystemExit("Use: maquinas importar <número do job do broker>")
        j = http_json(config.carregar()["broker_url"].rstrip("/") + f"/api/jobs/{a.id}", timeout=15, tentativas=1)
        if j.get("status") != "concluido":
            raise SystemExit(f"O job {a.id} está '{j.get('status')}' (a máquina precisa estar ligada para ele rodar).")
        texto = f"{j.get('resultado') or ''}\n{j.get('log') or ''}"
        mid, tok = re.search(r"LI_ID=(\S+)", texto), re.search(r"LI_TOKEN=(\S+)", texto)
        if not (mid and tok):
            raise SystemExit("O job terminou, mas não achei LI_ID/LI_TOKEN na saída: veja o log no painel do orquestrador.")
        try:
            print("registrada:", remoto.registrar(mid.group(1), tok.group(1)))
        except ValueError as e:
            raise SystemExit(str(e))
    for m in remoto.lista():
        print(f"  {m['id']:<14} {'ONLINE ' if m.get('online') else 'offline'}  {m['url']}  {m.get('erro') or ''}")


def registrar(sp):
    r = sp.add_parser("radar", help="varre Ollama e Hugging Face em busca de modelos novos")
    r.add_argument("--forcar", action="store_true", help="ignora o cache")
    r.add_argument("--sem-hf", action="store_true")
    r.set_defaults(f=cmd_radar)
    sp.add_parser("decidir", help="a mesa de decisão no terminal").set_defaults(f=cmd_decidir)
    t = sp.add_parser("testar", help="baixa um modelo novo, mede e compara com o modelo atual")
    t.add_argument("candidato", help="id do radar, ex.: ollama:qwen3.8:27b")
    t.add_argument("--papel")
    t.add_argument("--nivel", choices=["minimo", "rapido", "padrao", "profundo"], default="padrao")
    t.add_argument("--sim", action="store_true", help="não perguntar antes de baixar")
    t.set_defaults(f=cmd_testar)
    b = sp.add_parser("baixar", help="ollama pull com progresso")
    b.add_argument("modelo")
    b.set_defaults(f=cmd_baixar)
    rm = sp.add_parser("remover", help="apaga um modelo do disco")
    rm.add_argument("modelo")
    rm.add_argument("--sim", action="store_true")
    rm.set_defaults(f=cmd_remover)
    of = sp.add_parser("offline", help="prontidão offline, verificação e kit de backup")
    of.add_argument("acao", choices=["status", "exportar", "verificar"], nargs="?", default="status")
    of.add_argument("--destino")
    of.add_argument("--modelo", nargs="*")
    of.set_defaults(f=cmd_offline)
    sp.add_parser("relatorio", help="gera relatorios/AAAA-MM-DD-decisao.md").set_defaults(f=cmd_relatorio)
    pq = sp.add_parser("parque", help="melhores modelos para cada máquina do parque")
    pq.add_argument("--top", type=int, default=2)
    pq.add_argument("--sem-broker", action="store_true")
    pq.set_defaults(f=cmd_parque)
    pn = sp.add_parser("painel", help="abre o painel web")
    pn.add_argument("--porta", type=int)
    pn.add_argument("--sem-navegador", action="store_true")
    pn.set_defaults(f=cmd_painel)
    vg = sp.add_parser("vigia", help="rotina agendada: varre e grava alertas (não baixa nada)")
    vg.add_argument("--relatorio", action="store_true")
    vg.set_defaults(f=cmd_vigia)
    mg = sp.add_parser("migrar", help="resume o state.json antigo (protocolo v1) como histórico")
    mg.add_argument("arquivo", nargs="?", default=str(config.RAIZ / "legado" / "state.json"))
    mg.set_defaults(f=cmd_migrar)
    ca = sp.add_parser("calculadora", help="exporta a calculadora de hardware como um arquivo HTML único para compartilhar")
    ca.add_argument("--saida", help="caminho do .html (padrão: relatorios/calculadora-de-hardware-AAAA-MM-DD.html)")
    ca.add_argument("--com-parque", action="store_true", help="inclui as máquinas do parque como perfis prontos (padrão: não, para compartilhar)")
    ca.set_defaults(f=cmd_calculadora)
    sp.add_parser("token", help="mostra o token desta máquina (segredo; para registrá-la no painel controlador)").set_defaults(f=cmd_token)
    pr = sp.add_parser("painel-remoto", help="libera este painel para o tailnet (host do tailscale serve + logins permitidos)")
    pr.add_argument("--host", action="append", help="ex.: maquina.example.ts.net:10000 (repetível)")
    pr.add_argument("--id", help="id desta máquina em parque/parque.json (o hostname do Windows nem sempre coincide)")
    pr.add_argument("--login", action="append", help="login do Tailscale com acesso direto pelo navegador (repetível)")
    pr.set_defaults(f=cmd_painel_remoto)
    mq = sp.add_parser("maquinas", help="outras máquinas do parque controladas por este painel")
    mq.add_argument("acao", choices=["listar", "registrar", "remover", "importar"], nargs="?", default="listar")
    mq.add_argument("id", nargs="?")
    mq.add_argument("--token")
    mq.add_argument("--url")
    mq.set_defaults(f=cmd_maquinas)
