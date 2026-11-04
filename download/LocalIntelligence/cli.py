#!/usr/bin/env python3
"""Local Intelligence — linha de comando.  `python cli.py --help`

Os comandos importam seus módulos sob demanda: `status` e `radar` funcionam mesmo com o Ollama desligado.
"""
from __future__ import annotations

import argparse

from li import PROTOCOLO, __version__, config
from li.util import fmt_gb


def _ollama(iniciar: bool = True):
    from li.ollama import Ollama, ErroOllama
    o = Ollama()
    if not o.no_ar():
        if not iniciar:
            return o
        print("Ollama fora do ar — iniciando (flash attention + KV cache q8_0)…")
        try:
            if not o.iniciar_servidor():
                raise SystemExit("Não consegui iniciar o Ollama. Abra o app do Ollama e tente de novo.")
        except ErroOllama as e:
            raise SystemExit(str(e))
    return o


def _tarefa_pesada(tipo: str, titulo: str):
    """Trava compartilhada com o painel (estado/progresso.json): duas tarefas pesadas juntas falsificam a medição."""
    from li import jobs
    e = jobs.externo()
    if e:
        raise SystemExit(f"Já há uma tarefa pesada em andamento ({e.get('titulo')}, origem {e.get('origem')}). Espere terminar.")
    return jobs.registrar("cli", tipo, titulo, fase="rodando", msg="iniciando…")


def _modelos_instalados(o, nomes=None):
    inst = o.instalados()
    if not nomes or nomes == ["todos"]:
        return inst
    sel = [m for m in inst if m["id"] in nomes or m["id"].split(":")[0] in nomes]
    faltam = [n for n in nomes if not any(m["id"] == n or m["id"].split(":")[0] == n for m in inst)]
    if faltam:
        raise SystemExit("Modelo(s) não instalado(s): " + ", ".join(faltam) + "  (use `python cli.py baixar <modelo>`)")
    return sel


def cmd_status(a):
    from li import resultados, scout, parque
    from li.bench import sonda
    o = _ollama(False)
    print(f"Local AI Search {__version__} · protocolo {PROTOCOLO}")
    print(f"Ollama: {'no ar ' + str(o.versao()) if o.no_ar() else 'FORA DO AR'} ({o.url})")
    g = parque._nvidia()
    if g:
        print(f"GPU: {g['nome']} · {g['vram_gb']} GiB · livre {g['vram_livre_gb']} GiB · driver {g['driver']}")
    if o.no_ar():
        print("\nModelos instalados:")
        for m in o.instalados():
            r = resultados.resumo(m["id"], m["digest"])
            nota = f"{r['n_itens']} itens medidos" if r else "NÃO MEDIDO neste protocolo"
            print(f"  {m['id']:<22} {fmt_gb(m['bytes']):>8}  {','.join(m['caps']):<38} {nota}")
    s = scout.ultimo()
    print(f"\nRadar: {'último em ' + s['criado'] + f' · {s['total']} candidatos' if s else 'nunca rodou (use `python cli.py radar`)'}")


def cmd_bench(a):
    from li import resultados
    from li.bench import runner
    o = _ollama()
    ms = _modelos_instalados(o, a.modelo)
    print(f"Protocolo {PROTOCOLO} · nível {a.nivel} · modo {a.modo} · {len(ms)} modelo(s)")
    trava = _tarefa_pesada("bench", f"Benchmark {a.nivel} ({len(ms)} modelo(s), terminal)")

    def prog(d):
        trava.set(fase=d.get("fase", "rodando"), msg=d.get("msg"), feitos=d.get("feitos"), total=d.get("total"), eta_s=d.get("eta_s"))
        if d.get("fase") == "bench" and d.get("feitos", 0) % 10 and "modelo" in d and "suite" in d:
            return
        eta = f" · ETA {d['eta_s'] // 60}min" if d.get("eta_s") else ""
        print(f"[{d.get('feitos', 0)}/{d.get('total', 0)}] {d.get('msg', '')}{eta}", flush=True)
    try:
        res = runner.executar(o, [{"id": m["id"], "digest": m["digest"], "caps": m["caps"]} for m in ms], a.nivel,
                              a.suites or None, a.modo, prog)
    except BaseException:
        trava.set(fase="erro", msg="interrompido")
        raise
    trava.set(fase="concluido", msg="benchmark concluído")
    for mid, r in res.items():
        print(f"\n== {mid}: {'ok' if r['ok'] else r.get('motivo')} · {r['feitos']} itens novos")
        for p in r["pulados"]:
            print(f"   pulou {p['suite']}: {p['motivo']}")
        s = resultados.resumo(mid, modo=a.modo)
        if s:
            print("   " + " · ".join(f"{k} {v['acc']}% (n={v['n']})" for k, v in s["suites"].items()))
            print("   " + " · ".join(f"{k}: {v['nota']}" for k, v in s["papeis"].items() if v.get("nota") is not None))
    print("\nAs notas aparecem no painel (1_ABRIR_PAINEL.bat → Decidir).")
    print("Se o Local AI Search te ajudou: ♥ https://github.com/Cainho-pt-br/LocalAISearch#apoiar-o-projeto")


def cmd_sonda(a):
    from li.bench import sonda
    o = _ollama()
    trava = _tarefa_pesada("sonda", "Medindo VRAM e velocidade (terminal)")
    for m in _modelos_instalados(o, a.modelo):
        trava.set(fase="rodando", msg=f"sonda de {m['id']}")
        d = sonda.sondar_modelo(o, m["id"], m["digest"], [int(x) for x in a.ctx.split(",")], lambda s: print(" ", s))
        sonda.salvar_modelo(m["id"], m["digest"], d)
        for c, v in d.items():
            print(f"  {m['id']} ctx {c}: " + (f"{fmt_gb(v['total_bytes'])} · {v['pct_gpu']}% GPU · {v['tps']} tok/s" if v.get("ok") else v.get("erro")))
    trava.set(fase="concluido", msg="sonda concluída")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python cli.py", description="Local AI Search: descobrir, medir e escolher modelos de IA locais para o seu computador.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status", help="estado do Ollama, GPU, modelos e radar").set_defaults(f=cmd_status)
    b = sp.add_parser("bench", help="roda o protocolo de benchmark nos modelos instalados")
    b.add_argument("--modelo", nargs="*", help="tags (padrão: todos os instalados)")
    b.add_argument("--nivel", choices=["rapido", "padrao", "profundo"], default=config.carregar()["nivel_padrao"])
    b.add_argument("--modo", choices=["base", "think"], default="base")
    b.add_argument("--suites", nargs="*")
    b.set_defaults(f=cmd_bench)
    s = sp.add_parser("sonda", help="mede VRAM e velocidade por tamanho de contexto")
    s.add_argument("--modelo", nargs="*")
    s.add_argument("--ctx", default="4096,16384,32768")
    s.set_defaults(f=cmd_sonda)
    try:
        from li.comandos import registrar  # comandos que dependem de módulos maiores (radar, decidir, painel…)
        registrar(sp)
    except ImportError:
        pass
    a = ap.parse_args(argv)
    config.garantir_pastas()
    a.f(a)


if __name__ == "__main__":
    main()
