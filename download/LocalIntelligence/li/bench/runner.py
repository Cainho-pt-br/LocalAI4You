"""Executa o protocolo v2 num ou mais modelos: gate de GPU, retomada, progresso e cancelamento."""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from .. import config, resultados
from ..ollama import ErroOllama, Ollama
from . import amostras, suites
from .sonda import _linha_ps


def _tem_gpu_nvidia() -> bool:
    from ..parque import _nvidia
    return _nvidia() is not None


def _motivo_gate(g: dict) -> str:
    erro = g.get("erro") or ""
    if g.get("lento"):
        return f"lento demais para esta máquina: {g.get('tps')} tok/s medidos (mínimo configurado em tps_minimo). Benchmark pulado; refaça com “forçar” se quiser mesmo assim"
    if "unknown model architecture" in erro:
        return "o Ollama desta máquina não conhece a arquitetura do modelo (atualize o Ollama ou use outro modelo): não carregou"
    if erro:
        return f"não carregou: {erro[:140]}"
    return f"não ficou 100% na GPU ({g.get('pct_gpu')}%): excluído do ranking"


def ctx_nativo(oll: Ollama, modelo: str) -> Optional[int]:
    """Contexto máximo do próprio modelo (moondream: 2048). Pedir mais que isso faz modelo pequeno devolver lixo (visto no Moondream com 8k)."""
    try:
        for k, v in (oll.show(modelo).get("model_info") or {}).items():
            if k.endswith(".context_length"):
                return int(v)
    except (ErroOllama, ValueError, TypeError):
        pass
    return None


def medir_tps(oll: Ollama, modelo: str, ctx: int) -> Optional[float]:
    """Velocidade de geração (tok/s) com uma resposta curta, para cortar cedo o modelo lento demais para a máquina. O modelo já está aquecido (gate)."""
    try:
        r = oll.chat(modelo, [{"role": "user", "content": "Conte de 1 a 40 separando por vírgulas."}], ctx=ctx, max_tokens=40, think=False, keep_alive="10m", timeout=900)
        n, dur = int(r.get("eval_count") or 0), float(r.get("eval_duration") or 0)
        return round(n / (dur / 1e9), 2) if n >= 8 and dur else None
    except (ErroOllama, ValueError, TypeError):
        return None


def gate_gpu(oll: Ollama, modelo: str, ctx_lista: List[int]) -> dict:
    """Carrega o modelo no menor risco: tenta cada contexto até o modelo ficar 100% na GPU (size_vram ≥ size)."""
    gpu = _tem_gpu_nvidia()
    ultimo = {}
    for ctx in ctx_lista:
        oll.descarregar(modelo)
        time.sleep(0.5)
        try:
            oll.chat(modelo, [{"role": "user", "content": "Retorne apenas OK."}], ctx=ctx, max_tokens=8, think=False, keep_alive="10m", timeout=900)
            # segunda chamada: a 1ª inclui compilação de kernels; aqui o ps já reflete o estado estável
            oll.chat(modelo, [{"role": "user", "content": "Retorne apenas OK."}], ctx=ctx, max_tokens=8, think=False, keep_alive="10m", timeout=900)
        except ErroOllama as e:
            ultimo = {"ok": False, "ctx": ctx, "erro": str(e)[:200]}
            continue
        linha = _linha_ps(oll, modelo) or {}
        tam, vram = int(linha.get("size", 0)), int(linha.get("size_vram", 0))
        ok = (not gpu) or bool(tam and vram >= tam)
        ultimo = {"ok": ok, "ctx": ctx, "total_bytes": tam, "vram_bytes": vram, "gpu": gpu,
                  "pct_gpu": round(100 * vram / tam, 1) if tam else None}
        if ok:
            return ultimo
    return ultimo or {"ok": False, "erro": "sem tentativa"}


def executar(oll: Ollama, modelos: List[dict], nivel: str = "padrao", suites_pedidas: Optional[List[str]] = None,
             modo: str = "base", ao_progredir: Optional[Callable[[dict], None]] = None,
             cancelar: Optional[threading.Event] = None, exigir_gpu: bool = True, tps_minimo: float = 0) -> dict:
    """`modelos` = [{'id','digest','caps'}]. Devolve {modelo: {'ok':bool,'feitos':n,'pulados':[...]}}."""
    cfg = config.carregar()
    ctx_lista = [int(cfg["ctx_bench"])] + [int(c) for c in cfg.get("ctx_fallback", [])]
    pedidas = [s for s in (suites_pedidas or suites.ORDEM + suites.SUITES_EXTRAS) if s in suites.EXECUTORES]   # visão leve/fotos entram sempre; quem não declara visão é pulado em "pulados"
    if modo == "think":
        pedidas = [s for s in pedidas if s in suites.SUITES_THINK]
    cancelar = cancelar or threading.Event()
    oll.cancelar = cancelar
    prog = ao_progredir or (lambda d: None)

    plano = []  # (modelo, suite, item) pendentes — define o total honesto da barra de progresso
    resumo_final: Dict[str, dict] = {}
    for m in modelos:
        feitos = resultados.chaves_feitas(m["id"], m["digest"], modo)
        pulados = []
        if modo == "think" and "thinking" not in (m.get("caps") or []):
            resumo_final[m["id"]] = {"ok": True, "feitos": 0, "pulados": [{"suite": s, "motivo": "modelo não declara 'thinking'"} for s in pedidas]}
            continue  # pedir think a modelo sem esse modo dá erro 400 e poluiria o resultado
        for s in pedidas:
            exige = suites.EXIGE.get(s, [])
            if any(c not in (m.get("caps") or []) for c in exige):
                pulados.append({"suite": s, "motivo": "modelo não declara: " + ", ".join(exige)})
                continue
            if s == "capitu":
                from . import pontuacao
                if pontuacao.capitu_registro() is None:
                    pulados.append({"suite": s, "motivo": "nltk indisponível (pip install nltk)"})
                    continue
            for it in amostras.itens_do_nivel(s, nivel):
                if (s, it["id"]) not in feitos:
                    plano.append((m, s, it))
        resumo_final[m["id"]] = {"ok": True, "feitos": 0, "pulados": pulados}

    total, feitos_n, t_ini, lat_acum = len(plano), 0, time.time(), 0.0
    prog({"fase": "bench", "total": total, "feitos": 0, "msg": f"{total} itens pendentes em {len(modelos)} modelo(s) · nível {nivel}"})
    modelo_atual = None
    gate: Dict[str, dict] = {}
    ctx_modelo: Dict[str, List[int]] = {}
    for m, s, it in plano:
        if cancelar.is_set():
            prog({"fase": "cancelado", "total": total, "feitos": feitos_n, "msg": "benchmark cancelado"})
            break
        mid = m["id"]
        if mid != modelo_atual:
            if modelo_atual:
                oll.descarregar(modelo_atual)
            modelo_atual = mid
            prog({"fase": "bench", "modelo": mid, "total": total, "feitos": feitos_n, "msg": f"{mid}: verificando se cabe 100% na GPU…"})
            nat = ctx_nativo(oll, mid)
            ctx_modelo[mid] = sorted({min(c, nat) if nat else c for c in ctx_lista}, reverse=True)
            g = gate_gpu(oll, mid, ctx_modelo[mid])
            if tps_minimo and g.get("ok"):
                g["tps"] = medir_tps(oll, mid, g.get("ctx") or ctx_modelo[mid][0])
                if g["tps"] is not None and g["tps"] < tps_minimo:
                    g.update({"ok": False, "lento": True})
                prog({"fase": "bench", "modelo": mid, "total": total, "feitos": feitos_n, "msg": f"{mid}: {g['tps']} tok/s medidos (mínimo {tps_minimo})"})
            prog({"fase": "bench", "modelo": mid, "total": total, "feitos": feitos_n, "msg": f"{mid}: carregado; checando se ele 'pensa' mesmo com o raciocínio desligado (em CPU leva alguns minutos)…"})
            g["think_base"] = suites.descobrir_think_base(oll, mid) if g.get("ok") or not exigir_gpu else False
            if cancelar.is_set():   # a requisição foi derrubada no meio: o "erro" não é do modelo, não grava
                break
            gate[mid] = g
            resultados.anexar({"modelo": mid, "digest": m["digest"], "suite": "_meta", "item": "gate", "modo": modo,
                               "valido": True, "ok": g.get("ok", False), "det": {**g, "nivel": nivel, "ctx_usado": g.get("ctx")}})
            if not g.get("ok") and exigir_gpu:
                resumo_final[mid] = {**resumo_final[mid], "ok": False, "motivo": _motivo_gate(g)}
        g = gate.get(mid, {})
        if not g.get("ok") and exigir_gpu:
            feitos_n += 1  # pula o modelo inteiro sem gastar tempo
            continue
        res = suites.executar_item(oll, s, mid, it, g.get("ctx") or ctx_modelo.get(mid, ctx_lista)[0], modo, g.get("think_base", False))
        if cancelar.is_set():
            break
        resultados.anexar({"modelo": mid, "digest": m["digest"], "suite": s, "item": it["id"], "modo": modo,
                           "ctx": g.get("ctx"), "gpu": g.get("ok"), **res})
        resumo_final[mid]["feitos"] += 1
        feitos_n += 1
        lat_acum += res.get("lat", 0) or 0
        restante = (total - feitos_n) * (lat_acum / max(feitos_n, 1))
        prog({"fase": "bench", "modelo": mid, "suite": s, "item": it["id"], "total": total, "feitos": feitos_n,
              "eta_s": round(restante), "ultimo_ok": res["ok"],
              "msg": f"{mid} · {s} · {feitos_n}/{total}"})
    if modelo_atual:
        oll.descarregar(modelo_atual)
    prog({"fase": "concluido", "total": total, "feitos": feitos_n, "msg": "benchmark concluído", "duracao_s": round(time.time() - t_ini)})
    return resumo_final
