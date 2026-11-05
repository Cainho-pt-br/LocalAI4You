"""Servidor local do painel (somente 127.0.0.1) + API JSON.

Endurecimento (o painel antigo servia a pasta inteira com CORS aberto):
  • escuta só em loopback; Host precisa ser 127.0.0.1/localhost com a porta do painel (barra DNS-rebinding);
  • POST exige cabeçalho X-LI e, se houver Origin, que seja o próprio painel (barra CSRF de outras abas);
  • sem CORS; só serve arquivos de web/; ações destrutivas pedem confirmação explícita no corpo.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from . import PROTOCOLO, __version__, aposentados, calc, config, decide, desafio, lab, offline, papeis, parque, quants, remoto, report, resultados, scout
from .bench import amostras, custo, runner, sonda, stats
from .jobs import Gerente
from .ollama import ErroOllama, Ollama, instalado as ollama_instalado, pasta_modelos
from .util import ERROS_PARALELO, ler_json, slug

GERENTE = Gerente()
_CACHE: Dict[str, tuple] = {}


def _memo(chave: str, ttl: float, fn: Callable[[], Any]) -> Any:
    t, v = _CACHE.get(chave, (0, None))
    if time.time() - t < ttl and v is not None:
        return v
    v = fn()
    _CACHE[chave] = (time.time(), v)
    return v


def _invalidar() -> None:
    _CACHE.clear()


def _oll() -> Ollama:
    return Ollama()


class Erro(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------------ rotas GET

def r_saude(q):
    o = _oll()
    up = o.no_ar()
    g = parque._gpu_local()
    return {"versao_painel": __version__, "protocolo": PROTOCOLO, "ollama": {"no_ar": up, "instalado": up or ollama_instalado(), "versao": o.versao() if up else None, "url": o.url},
            "gpu": g, "disco_modelos_livre_gb": parque.espaco_livre_gb(pasta_modelos()), "pasta_modelos": str(pasta_modelos()),
            "tarefa_pesada": GERENTE.bloqueio(),
            "avisos_internos": ERROS_PARALELO[-3:]}


def r_mesa(q):
    return _memo("mesa", 4, lambda: decide.mesa_de_decisao(_oll()))


def r_radar(q):
    maq = q.get("maquina", ["boss"])[0]
    papel = q.get("papel", [None])[0]
    snap = scout.ultimo()
    pk = parque.carregar_parque(False)
    m = next((x for x in pk["maquinas"] if x["id"] == maq), None)
    if not m and maq == "boss":
        m = parque.maquina_local(pk)
    if not m:
        raise Erro("Máquina desconhecida", 404)
    inst = decide._instalados(_oll())
    lista = decide.candidatos_para(m, inst if m.get("local") else [], snap, papel or None,
                                   incluir_comunidade=q.get("comunidade", ["0"])[0] == "1",
                                   incluir_antigos=q.get("antigos", ["0"])[0] == "1", limite=int(q.get("limite", ["30"])[0]))
    return {"maquina": m["id"], "papel": papel, "candidatos": lista, "radar": decide._resumo_radar(snap)}


def r_radar_info(q):
    snap = scout.ultimo()
    if not snap:
        return {"existe": False}
    n = scout.novidades(snap)
    por_id = {c["id"]: c for c in snap["candidatos"]}
    resumir = lambda ids: [{"id": i, "nome": por_id[i]["nome"], "dias": por_id[i].get("dias"), "params_b": por_id[i]["params_b"],
                            "origem": por_id[i]["origem"], "confianca": por_id[i].get("confianca")} for i in ids if i in por_id]
    return {"existe": True, "criado": snap["criado"], "total": snap["total"], "fontes": snap["fontes"],
            "apareceram": resumir(n["apareceram"]), "recentes": resumir(n["lancamentos_recentes"])[:25],
            "desde": n["desde"], "primeira_varredura": n["primeira_varredura"]}


def r_parque(q):
    def calc_pk():
        snap = scout.ultimo()
        pk = parque.carregar_parque(q.get("broker", ["1"])[0] == "1")
        return {"maquinas": decide.recomendacoes_parque(snap, _oll(), pk=pk), "fontes": pk["fontes"], "radar": decide._resumo_radar(snap)}
    return _memo("parque" + q.get("broker", ["1"])[0], 20, calc_pk)


def r_jobs(q):
    return GERENTE.lista_com_externa()


def r_job(q, jid):
    j = GERENTE.jobs.get(jid)
    if not j:
        raise Erro("Tarefa não encontrada", 404)
    return j.dict()


def r_comparar(q):
    a, b, p = q.get("a", [""])[0], q.get("b", [""])[0], q.get("papel", ["chat_pt"])[0]
    o = _oll()
    inst = {m["id"]: m for m in decide.modelos_do_boss(o)} if o.no_ar() else {}
    ia, ib = inst.get(a), inst.get(b)
    if not ia or not ib:
        raise Erro("Os dois modelos precisam estar instalados (ou use 'Rodar Batalha' para baixar e testar).", 404)
    papeis_alvo = [x["id"] for x in papeis.PAPEIS if not x.get("sem_nota")] if p in ("todas", "todos", "") else [p]
    por_papel = {}
    for pid in papeis_alvo:
        c = resultados.comparar((a, ia["digest"]), (b, ib["digest"]), pid)
        if c and c.get("cobertura", 0) >= 0.5:
            por_papel[pid] = {**c, "veredito": stats.veredito_pareado(c)}
    if not por_papel:
        return {"ok": False, "motivo": "sem medições em comum para essa função"}
    prim = por_papel.get(p) or next(iter(por_papel.values()))
    return {
        "ok": True,
        **prim,
        "veredito": prim["veredito"],
        "por_papel": por_papel,
        "modelo_a": {
            "id": a, "bytes": ia["bytes"],
            "tps": (ia.get("medido") or {}).get("tps_mediana"),
            "ctx_gpu": (ia.get("sonda") or {}).get("ctx_max_gpu") or ((ia.get("ctx_por_kv") or {}).get("q8_0") or {}).get("ctx_max"),
            "indice_pratico": ia.get("indice_pratico"),
        },
        "modelo_b": {
            "id": b, "bytes": ib["bytes"],
            "tps": (ib.get("medido") or {}).get("tps_mediana"),
            "ctx_gpu": (ib.get("sonda") or {}).get("ctx_max_gpu") or ((ib.get("ctx_por_kv") or {}).get("q8_0") or {}).get("ctx_max"),
            "indice_pratico": ib.get("indice_pratico"),
        },
    }


def r_offline(q):
    return offline.estado(_oll())


def r_relatorio(q):
    return {"markdown": report.gerar_markdown(_oll())}


def r_config(q):
    c = config.carregar()
    c["ollama_url_efetiva"] = config.ollama_url()
    return c


def r_plano(q):
    o = _oll()   # a máquina de destino é escolhida no seletor "Controlando" (o painel dela responde): nunca se fala com o Ollama de outra máquina
    try:
        return desafio.plano(q.get("candidato", [""])[0], q.get("papel", [None])[0] or None, o, q.get("pull", [None])[0] or None)
    except desafio.ErroDesafio as e:
        raise Erro(str(e))


def r_bench_niveis(q):
    """Tempo estimado de cada nível NESTA máquina para os modelos pedidos (ids instalados ou `bytes=n,n`)."""
    maq = parque.maquina_local()
    pesos = [int(x) for x in (q.get("bytes", [""])[0]).split(",") if x.strip().isdigit()]
    ids = [x for x in (q.get("modelos", [""])[0]).split(",") if x.strip()]
    visao = [False] * len(pesos)
    if ids:
        sel = [m for m in _oll().instalados() if m["id"] in ids]
        pesos += [m["bytes"] for m in sel]
        visao += ["vision" in (m.get("caps") or []) for m in sel]
    pesos = pesos or [1_000_000_000]
    visao = visao or [False]
    return custo.resumo(maq, pesos, visao)


def _nivel_para_a_maquina(nivel: str, pesos: list, forcado: bool, visao: Optional[list] = None) -> tuple:
    """(nível, aviso): reduz sozinho um nível que levaria mais de 3 h nesta máquina, a menos que o usuário tenha forçado."""
    if forcado:
        return nivel, ""
    novo = custo.limitar(parque.maquina_local(), pesos, nivel, visao)
    if novo == nivel:
        return nivel, ""
    return novo, f" — nível {nivel} reduzido para {novo}: levaria mais de 3 h nesta máquina"


def r_quants(q):
    try:
        return quants.explorar(q.get("candidato", [""])[0], forcar=q.get("forcar", ["0"])[0] == "1")
    except quants.ErroQuants as e:
        raise Erro(str(e), 404)


def r_calc_dados(q):
    o = _oll()
    return _memo("calc", 30, lambda: calc.dados(o if o.no_ar() else None))


def r_aposentados(q):
    return {"aposentados": aposentados.listar(decide._instalados(_oll()))}


def r_lab_plano(q):
    o = _oll()
    mesa = r_mesa(q) if o.no_ar() else None
    return _memo("lab", 8, lambda: lab.plano(o if o.no_ar() else None, mesa))


def r_amostras(q):
    return {"niveis": amostras.NIVEIS, "amostras": amostras.resumo(), "suites": papeis.SUITES}


def r_modelo(q, mid):
    o = _oll()
    inst = {m["id"]: m for m in o.instalados()} if o.no_ar() else {}
    m = inst.get(mid)
    rows = resultados.carregar()
    digest = m["digest"] if m else None
    r = resultados.resumo(mid, digest, "base", rows)
    if not r:
        raise Erro("Sem medições para esse modelo", 404)
    return {"modelo": mid, "instalado": bool(m), "resumo": r, "think": resultados.resumo(mid, digest, "think", rows),
            "sonda": sonda.da_sonda(mid, digest), "caps": (m or {}).get("caps")}


def r_historico(q):
    return ler_json(config.ESTADO / "historico_v1.json", {}) or {}


GET_ROTAS = {"/api/historico": r_historico, "/api/saude": r_saude, "/api/mesa": r_mesa, "/api/radar": r_radar, "/api/radar/info": r_radar_info, "/api/parque": r_parque,
             "/api/jobs": r_jobs, "/api/comparar": r_comparar, "/api/offline": r_offline, "/api/relatorio": r_relatorio,
             "/api/config": r_config, "/api/plano": r_plano, "/api/amostras": r_amostras, "/api/quants": r_quants,
             "/api/calc/dados": r_calc_dados, "/api/aposentados": r_aposentados, "/api/lab/plano": r_lab_plano}


# ------------------------------------------------------------------ rotas POST

def _exige_ollama() -> Ollama:
    o = _oll()
    if not o.no_ar():
        try:
            if not o.iniciar_servidor():
                raise Erro("Ollama fora do ar e não consegui iniciar.", 503)
        except ErroOllama as e:
            raise Erro(str(e), 503)
    return o


def _iniciar(tipo, titulo, fn):
    try:
        return GERENTE.iniciar(tipo, titulo, fn).dict()
    except RuntimeError as e:
        raise Erro(str(e), 409)


def p_varrer(b):
    forcar = bool(b.get("forcar"))

    def tarefa(ctx):
        snap = scout.varrer(forcar=forcar, ao_progredir=lambda s: ctx.prog({"msg": s}))
        _invalidar()
        n = scout.novidades(snap)
        ctx.prog({"msg": f"{snap['total']} candidatos · {len(n['apareceram'])} novos desde a última varredura"})
        return {"total": snap["total"], "novos": len(n["apareceram"])}
    return _iniciar("varredura", "Varrendo Ollama e Hugging Face", tarefa)


def p_bench(b):
    o = _exige_ollama()
    nivel = b.get("nivel", config.carregar()["nivel_padrao"])
    if nivel not in amostras.NIVEIS:
        raise Erro("Nível inválido")
    modo = b.get("modo", "base")
    alvo = b.get("modelos") or []
    inst = o.instalados()
    ms = [m for m in inst if not alvo or m["id"] in alvo]
    if not ms:
        raise Erro("Nenhum modelo instalado corresponde ao pedido.", 404)
    nivel, aviso_nivel = _nivel_para_a_maquina(nivel, [m["bytes"] for m in ms], bool(b.get("nivel_forcado")), ["vision" in (m.get("caps") or []) for m in ms])

    def tarefa(ctx):
        res = runner.executar(o, [{"id": m["id"], "digest": m["digest"], "caps": m["caps"]} for m in ms], nivel, b.get("suites"), modo, ctx.prog, ctx.cancelar,
                              tps_minimo=0 if b.get("nivel_forcado") else float(config.carregar().get("tps_minimo") or 0))
        _invalidar()
        return res
    return _iniciar("bench", f"Benchmark ({nivel}, {len(ms)} modelo(s)){aviso_nivel}", tarefa)


def p_sonda(b):
    o = _exige_ollama()
    alvo = b.get("modelos") or []
    ate_ctx = int(b["ate_ctx"]) if b.get("ate_ctx") else None
    kv_pedido = (b.get("kv_cache") or config.carregar().get("kv_cache") or "q8_0").strip()
    if kv_pedido not in ("f16", "q8_0", "q4_0"):
        kv_pedido = "q8_0"
    ms = [m for m in o.instalados() if not alvo or m["id"] in alvo]
    vram_gb, sem_gpu = parque.memoria_modelo(parque.maquina_local())

    def tarefa(ctx):
        kv_atual = config.carregar().get("kv_cache", "q8_0")
        if kv_pedido != kv_atual:
            ctx.prog({"msg": f"Reiniciando servidor Ollama com KV cache {kv_pedido}…", "pct": 1.0})
            o.reiniciar_com_kv(kv_pedido)

        lista_trabalho = []
        for m in ms:
            c_deg = sonda.degraus_sonda(m, vram_gb, ate_ctx=ate_ctx, cpu=sem_gpu, kv_tipo=kv_pedido)
            lista_trabalho.append((m, c_deg))
        total_passos = max(1, sum(len(deg) for _, deg in lista_trabalho))
        passo_atual = 0

        for m, ctxs in lista_trabalho:
            if ctx.cancelar.is_set():
                break

            def cb_prog(**kw):
                m_txt = kw.get("msg", "")
                f_idx = kw.get("feitos", passo_atual)
                p_val = kw.get("pct", round(100.0 * f_idx / total_passos, 1))
                ctx.prog({
                    "msg": f"[{kv_pedido}] {m_txt}",
                    "feitos": f_idx,
                    "total": total_passos,
                    "pct": min(100.0, max(0.0, p_val))
                })

            res = sonda.sondar_modelo(o, m["id"], m["digest"], ctxs, cb_prog,
                                      passo_inicial=passo_atual, total_passos=total_passos,
                                      cancelar=ctx.cancelar, enchimento_max=3072 if sem_gpu else 8192, cpu=sem_gpu)
            if res:
                sonda.salvar_modelo(m["id"], m["digest"], res, kv_tipo=kv_pedido)
            passo_atual += len(ctxs)
            ctx.prog({"feitos": passo_atual, "total": total_passos, "pct": round(100.0 * passo_atual / total_passos, 1)})
        _invalidar()
    return _iniciar("sonda", f"Medindo VRAM e velocidade (KV {kv_pedido})", tarefa)


def p_desafio(b):
    if not b.get("confirmo_download"):
        raise Erro("Confirme o download: o teste baixa o modelo se ele não estiver instalado.")
    o = _exige_ollama()
    cand, papel, nivel = b.get("candidato"), b.get("papel") or None, b.get("nivel", "padrao")
    pull = (b.get("pull") or "").strip() or None
    if not cand:
        raise Erro("Informe o candidato.")
    if nivel not in amostras.NIVEIS:
        raise Erro("Nível inválido")
    try:
        pl = desafio.plano(cand, papel, o, pull)
    except desafio.ErroDesafio as e:
        raise Erro(str(e))
    nivel, aviso_nivel = _nivel_para_a_maquina(nivel, [int(pl.get("bytes") or 0)] * 2, bool(b.get("nivel_forcado")))   # candidato + titular

    def tarefa(ctx):
        v = desafio.testar(o, cand, papel, nivel, ctx.prog, ctx.cancelar, pull=pull)
        _invalidar()
        return {"veredito": v["id"], "resumo": v["resumo"], "recomendacao": v["recomendacao"]}
    return _iniciar("desafio", f"Teste do desafiante {pl['candidato']}{aviso_nivel}", tarefa)


def p_duelo(b):
    if not b.get("confirmo_download"):
        raise Erro("Confirme a execução: se algum dos modelos não estiver instalado, ele será baixado.")
    o = _exige_ollama()
    ma = (b.get("a") or "").strip()
    mb = (b.get("b") or "").strip()
    papel = (b.get("papel") or "chat_pt").strip()
    nivel = b.get("nivel", "rapido")
    if not ma or not mb:
        raise Erro("Informe os dois modelos para o duelo.")
    if nivel not in amostras.NIVEIS:
        raise Erro("Nível inválido")
    pesos = [m["bytes"] for m in o.instalados() if m["id"] in (ma, mb)]
    nivel, aviso_nivel = _nivel_para_a_maquina(nivel, pesos, bool(b.get("nivel_forcado")))

    def tarefa(ctx):
        v = desafio.duelo(o, ma, mb, papel, nivel, ctx.prog, ctx.cancelar)
        _invalidar()
        return {"veredito": v["id"], "resumo": v["resumo"], "recomendacao": v["recomendacao"]}
    return _iniciar("duelo", f"Duelo {ma} × {mb}{aviso_nivel}", tarefa)


def p_fixar_ctx(b):
    o = _exige_ollama()
    base = (b.get("modelo") or b.get("base") or "").strip()
    ctx = int(b.get("ctx") or b.get("num_ctx") or 16384)
    if not base or any(ch in base for ch in " \t\r\n\"'<>|&;`$"):
        raise Erro("Nome de modelo inválido.")
    if ctx < 1024 or ctx > 524288:
        raise Erro("Tamanho de contexto fora do intervalo permitido.")
    sufixo = f"{ctx // 1024}k" if ctx >= 1024 else str(ctx)
    alias = (b.get("alias") or "").strip() or f"{slug(base.split('/')[-1])}-{sufixo}"
    if any(ch in alias for ch in " \t\r\n\"'<>|&;`$"):
        raise Erro("Alias inválido.")
    try:
        res = o.criar_variante_ctx(base, alias, ctx)
    except ErroOllama as e:
        raise Erro(str(e), 502)
    _invalidar()
    return res


def p_baixar(b):
    if not b.get("confirmo_download"):
        raise Erro("Confirme o download.")
    pull = (b.get("pull") or "").strip()
    if not pull or len(pull) > 200 or any(ch in pull for ch in " \t\r\n\"'<>|&;`$"):
        raise Erro("Nome de modelo inválido.")
    o = _exige_ollama()

    def tarefa(ctx):
        o.baixar(pull, lambda d: ctx.prog({"msg": f"Baixando {pull}: {d['pct']}% · {d['mb_s']} MB/s", "pct": d["pct"]}), ctx.cancelar,
                 int(b.get("bytes_esperados") or 0))
        _invalidar()
    return _iniciar("download", f"Baixando {pull}", tarefa)


def p_atualizar(b):
    o = _exige_ollama()
    alvo = b.get("modelos") or []
    inst = o.instalados()
    ms = [m for m in inst if not alvo or m["id"] in alvo]
    if not ms:
        raise Erro("Nenhum modelo instalado corresponde ao pedido.", 404)

    def tarefa(ctx):
        atualizados = []
        total = max(1, len(ms))
        for i, m in enumerate(ms):
            if ctx.cancelar.is_set():
                break
            mid = m["id"]
            dg_antes = m.get("digest", "")
            ctx.prog({"msg": f"Verificando/atualizando {mid} ({i + 1}/{total})…", "feitos": i, "total": total, "pct": round(100.0 * i / total, 1)})
            o.baixar(mid, lambda d, n=mid, idx=i: ctx.prog({
                "msg": f"Atualizando {n}: {d['pct']}% · {d['mb_s']} MB/s",
                "feitos": idx, "total": total,
                "pct": round(100.0 * (idx + (d["pct"] / 100.0)) / total, 1)
            }), ctx.cancelar, int(m.get("bytes") or 0))
            depois = next((x for x in o.instalados() if x["id"] == mid), None)
            if depois and depois.get("digest") != dg_antes:
                atualizados.append(mid)
        _invalidar()
        ctx.prog({"msg": f"Concluído: {len(atualizados)} modelo(s) receberam nova versão" if atualizados else "Todos os modelos já estavam na versão mais recente", "feitos": total, "total": total, "pct": 100.0})
        return {"verificados": len(ms), "atualizados": atualizados}
    return _iniciar("atualizar", f"Atualizando {len(ms)} modelo(s) instalado(s)", tarefa)


def p_promover(b):
    try:
        s = desafio.promover(b.get("papel", ""), b.get("modelo", ""), b.get("motivo", "escolha manual"))
    except desafio.ErroDesafio as e:
        raise Erro(str(e))
    _invalidar()
    return s


def p_veredito(b):
    try:
        v = desafio.resolver_veredito(b.get("id", ""), b.get("acao", ""), _oll(), bool(b.get("confirmar_remocao")))
    except desafio.ErroDesafio as e:
        raise Erro(str(e))
    _invalidar()
    return v


def p_remover(b):
    if not b.get("confirmo"):
        raise Erro("Remover apaga os arquivos do modelo do disco: confirme.")
    mid = b.get("modelo", "")
    o = _exige_ollama()
    if mid not in {m["id"] for m in o.instalados()}:
        raise Erro("Modelo não está instalado.", 404)
    try:
        r = desafio.aposentar(o, mid, (b.get("motivo") or "removido pelo painel").strip()[:300], b.get("herdeiros") or {})
    except (ErroOllama, desafio.ErroDesafio) as e:
        raise Erro(str(e), 502)
    _invalidar()
    return r


def p_exportar(b):
    destino = (b.get("destino") or config.carregar().get("backup_modelos_dir") or "").strip()
    if not destino:
        raise Erro("Informe a pasta do kit.")
    modelos = b.get("modelos") or []
    if not modelos:
        raise Erro("Escolha ao menos um modelo.")
    config.salvar({"backup_modelos_dir": destino})

    def tarefa(ctx):
        r = offline.exportar_kit(destino, modelos, ctx.prog, ctx.cancelar)
        _invalidar()
        return r
    return _iniciar("exportar", f"Exportando kit offline para {destino}", tarefa)


def p_verificar(b):
    mid = b.get("modelo", "")
    return _iniciar("verificar", f"Verificação profunda de {mid}", lambda ctx: offline.verificar_profundo(mid, ctx.prog, ctx.cancelar))


def p_cancelar(b):
    return {"ok": GERENTE.cancelar(b.get("job", ""))}


def p_config(b):
    c = config.salvar(b)
    _invalidar()
    return c


def p_relatorio(b):
    caminho = report.salvar(_oll())
    return {"arquivo": str(caminho)}


def r_maquinas(q):
    return {"remotas": remoto.lista(), "parque": sorted(remoto.ids_do_parque()), "porta_tailnet": remoto.PORTA_TAILNET}


def r_radar_snapshot(q):
    snap = scout.ultimo()
    if not snap:
        raise Erro("Este painel ainda não tem radar.", 404)
    return snap


def p_radar_importar(b):
    """Recebe o radar de outro painel: o boss varre uma vez e as outras máquinas usam o mesmo catálogo (o encaixe é calculado aqui, com o hardware daqui)."""
    if not isinstance(b.get("candidatos"), list) or not b.get("criado") or not b["candidatos"] or "id" not in b["candidatos"][0]:
        raise Erro("Radar inválido.")
    scout.salvar_snapshot(b)
    _invalidar()
    return {"ok": True, "total": len(b["candidatos"])}


def p_maq_registrar(b):
    try:
        return remoto.registrar((b.get("id") or "").strip(), (b.get("token") or "").strip(), (b.get("url") or "").strip() or None)
    except ValueError as e:
        raise Erro(str(e))


def p_maq_remover(b):
    remoto.remover((b.get("id") or "").strip())
    return {"ok": True}


def p_maq_sincronizar(b):
    mid = (b.get("id") or "").strip()
    snap = scout.ultimo()
    if not snap:
        raise Erro("Este painel ainda não tem radar para enviar: varra primeiro.", 404)
    try:
        st, corpo, _ = remoto._pedido(mid, "POST", "/api/radar/importar", json.dumps(snap, ensure_ascii=False).encode("utf-8"), 120)
    except ValueError as e:
        raise Erro(str(e), 404)
    except Exception as e:
        raise Erro(f"A máquina '{mid}' não respondeu: {getattr(e, 'reason', e)}", 502)
    if st != 200:
        raise Erro(f"A máquina '{mid}' recusou o radar: {corpo.decode('utf-8', 'replace')[:200]}", 502)
    return json.loads(corpo.decode("utf-8"))


GET_ROTAS.update({"/api/visao/comparar": lambda q: lab.visao_comparar(), "/api/bench/niveis": r_bench_niveis, "/api/maquinas": r_maquinas, "/api/radar/snapshot": r_radar_snapshot})
CONTROLE = {"/api/encerrar", "/api/maquinas", "/api/maquinas/registrar", "/api/maquinas/remover", "/api/maquinas/sincronizar-radar"}   # só pelo loopback: o remoto não encadeia


_SERVIDOR: Dict[str, Any] = {}


def p_encerrar(corpo):
    """Botão "Fechar o app": no Windows o painel roda sem janela, então é assim que se encerra."""
    srv = _SERVIDOR.get("srv")
    if srv:
        threading.Timer(0.4, srv.shutdown).start()
    return {"ok": True}


def p_ollama_iniciar(corpo):
    """Assistente de primeiros passos: liga o Ollama instalado (o mesmo que o painel faz ao precisar dele)."""
    o = _exige_ollama()
    return {"ok": True, "versao": o.versao()}


POST_ROTAS = {"/api/encerrar": p_encerrar, "/api/ollama/iniciar": p_ollama_iniciar, "/api/aposentar": p_remover, "/api/radar/varrer": p_varrer, "/api/bench": p_bench, "/api/sonda": p_sonda,
              "/api/desafio": p_desafio, "/api/duelo": p_duelo, "/api/fixar-ctx": p_fixar_ctx,
              "/api/baixar": p_baixar, "/api/atualizar": p_atualizar, "/api/promover": p_promover, "/api/veredito": p_veredito, "/api/remover": p_remover,
              "/api/offline/exportar": p_exportar, "/api/offline/verificar": p_verificar, "/api/cancelar": p_cancelar,
              "/api/config": p_config, "/api/relatorio/gerar": p_relatorio, "/api/radar/importar": p_radar_importar,
              "/api/maquinas/registrar": p_maq_registrar, "/api/maquinas/remover": p_maq_remover, "/api/maquinas/sincronizar-radar": p_maq_sincronizar}


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "LocalIntelligence"
    porta = 8765

    def log_message(self, *a):
        pass

    def _acesso(self) -> str:
        return remoto.acesso(self.headers.get("Host") or "", self.headers.get("X-LI-Token"), self.headers.get("Tailscale-User-Login"), self.porta)

    def _repassar(self, ac: str, metodo: str, u, corpo: Optional[bytes]):
        """/api/m/<id>/<rota> → painel da outra máquina (só quem entra pelo loopback controla outras máquinas)."""
        if ac != "local":
            return self._json({"erro": "controle de outras máquinas só pelo painel local"}, 403)
        partes = u.path.split("/", 4)
        if len(partes) < 5:
            return self._json({"erro": "rota inválida"}, 404)
        try:
            st, dado, tipo = remoto.repassar(partes[3], metodo, partes[4], u.query, corpo)
        except ValueError as e:
            return self._json({"erro": str(e)}, 404)
        self._enviar(st, dado, tipo)

    def _enviar(self, status: int, corpo: bytes, tipo: str = "application/json; charset=utf-8", extras: Optional[dict] = None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        for k, v in (extras or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dado: Any, status: int = 200):
        self._enviar(status, json.dumps(dado, ensure_ascii=False, default=str).encode("utf-8"))

    def do_GET(self):
        ac = self._acesso()
        if ac == "negado":
            return self._enviar(421, b"host nao permitido", "text/plain")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path.startswith("/api/m/"):
                return self._repassar(ac, "GET", u, None)
            if ac != "local" and u.path in CONTROLE:
                return self._json({"erro": "só pelo painel local"}, 403)
            if u.path == "/api/calc/html":
                o = _oll()
                corpo = calc.html_autonomo(o if o.no_ar() else None).encode("utf-8")
                return self._enviar(200, corpo, "text/html; charset=utf-8", {"Content-Disposition": 'attachment; filename="calculadora-de-hardware-ia-local.html"'})
            if u.path in GET_ROTAS:
                return self._json(GET_ROTAS[u.path](q))
            if u.path.startswith("/api/jobs/"):
                return self._json(r_job(q, u.path.rsplit("/", 1)[1]))
            if u.path.startswith("/api/modelo/"):
                from urllib.parse import unquote
                return self._json(r_modelo(q, unquote(u.path[len("/api/modelo/"):])))
            if u.path.startswith("/api/"):
                raise Erro("Rota não encontrada", 404)
            return self._estatico(u.path)
        except Erro as e:
            self._json({"erro": str(e)}, e.status)
        except Exception as e:
            self._json({"erro": f"{type(e).__name__}: {e}", "detalhe": traceback.format_exc(limit=4)}, 500)

    def _estatico(self, caminho: str):
        rel = "index.html" if caminho in ("/", "") else caminho.lstrip("/")
        arq = (config.WEB / rel).resolve()
        if config.WEB.resolve() not in arq.parents or not arq.is_file():
            return self._enviar(404, b"nao encontrado", "text/plain")
        tipo = mimetypes.guess_type(str(arq))[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "application/json"):
            tipo += "; charset=utf-8"
        self._enviar(200, arq.read_bytes(), tipo)

    def do_POST(self):
        ac = self._acesso()
        if ac == "negado":
            return self._enviar(421, b"host nao permitido", "text/plain")
        origem = self.headers.get("Origin")
        permitidas = (f"http://127.0.0.1:{self.porta}", f"http://localhost:{self.porta}") if ac == "local" else (f"https://{self.headers.get('Host')}",)
        if origem and origem not in permitidas:
            return self._json({"erro": "origem não permitida"}, 403)
        if self.headers.get("X-LI") != "1":
            return self._json({"erro": "cabeçalho X-LI ausente"}, 403)
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > (12_000_000 if (u.path.startswith("/api/m/") or u.path in ("/api/radar/importar", "/api/maquinas/sincronizar-radar")) else 1_000_000):
                raise Erro("corpo grande demais", 413)
            if u.path.startswith("/api/m/"):
                return self._repassar(ac, "POST", u, self.rfile.read(n) if n else None)
            if ac != "local" and u.path in CONTROLE:
                raise Erro("só pelo painel local", 403)
            corpo = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            if not isinstance(corpo, dict):
                raise Erro("corpo deve ser um objeto JSON")
            fn = POST_ROTAS.get(u.path)
            if not fn:
                raise Erro("Rota não encontrada", 404)
            self._json(fn(corpo))
        except Erro as e:
            self._json({"erro": str(e)}, e.status)
        except json.JSONDecodeError:
            self._json({"erro": "JSON inválido"}, 400)
        except Exception as e:
            self._json({"erro": f"{type(e).__name__}: {e}", "detalhe": traceback.format_exc(limit=4)}, 500)


class Servidor(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def servir(porta: Optional[int] = None, abrir: bool = True, iniciar_ollama: bool = True) -> None:
    config.garantir_pastas()
    porta = porta or int(config.carregar()["painel_porta"])
    Handler.porta = porta
    if iniciar_ollama:
        o = _oll()
        if not o.no_ar():
            print("Ollama fora do ar — iniciando…")
            try:
                o.iniciar_servidor()
            except ErroOllama as e:
                print("  aviso:", e)
    url = f"http://127.0.0.1:{porta}/"
    try:
        srv = Servidor(("127.0.0.1", porta), Handler)
    except OSError:
        print(f"A porta {porta} já está em uso — provavelmente o painel já está aberto. Abrindo {url}")
        if abrir:
            webbrowser.open(url)
        return
    _SERVIDOR["srv"] = srv
    print(f"Painel em {url}  (Ctrl+C para encerrar)")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nPainel encerrado.")
