"""Prompts e execução de cada suíte. Um item entra, um dicionário de resultado sai."""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from ..ollama import ErroOllama, Ollama
from . import pontuacao as P

ORDEM = ["mmlu_pt", "mmlu_pro", "capitu", "ifeval", "bfcl_prompt", "bfcl_native", "humaneval", "gsm8k", "visao"]
EXIGE = {"bfcl_native": ["tools"], "visao": ["vision"], "visao_leve": ["vision"], "visao_fotos": ["vision"]}
# Suítes fora da ordem padrão: só rodam quando pedidas (aba Medir → Visão). Não entram nas notas por função nem no "n_itens".
SUITES_EXTRAS = ["visao_leve", "visao_fotos"]  # capacidade que o modelo precisa declarar no /api/show
# suítes usadas no modo "raciocínio" (think ligado): onde pensar mais ajuda e custa o que vale
SUITES_THINK = ["mmlu_pro", "gsm8k", "humaneval"]


def _perguntar(oll: Ollama, modelo: str, msgs: List[dict], ctx: int, max_tokens: int, think: Any,
               tools: Optional[list] = None) -> tuple:
    """Chama o modelo. Se a resposta veio vazia porque o 'pensar' comeu o orçamento, repete com 4× tokens."""
    t0 = time.perf_counter()
    r = oll.chat(modelo, msgs, ctx=ctx, max_tokens=max_tokens, think=think, tools=tools)
    reintentou = False
    msg = r.get("message") or {}
    if not P.limpar(msg.get("content", "")) and not msg.get("tool_calls") and int(r.get("eval_count", 0)) >= max_tokens - 2:
        r = oll.chat(modelo, msgs, ctx=ctx, max_tokens=min(max_tokens * 4, 6144), think=think, tools=tools)
        reintentou = True
    return r, reintentou, time.perf_counter() - t0


def _metricas(r: dict, lat: float, ctx: int, reintentou: bool) -> dict:
    ev, ed = int(r.get("eval_count", 0)), int(r.get("eval_duration", 0))
    pt = int(r.get("prompt_eval_count", 0))
    return {"tps": round(ev / (ed / 1e9), 1) if ev >= 24 and ed else None, "pt": pt, "gt": ev,
            "lat": round(lat, 2), "truncado": pt >= ctx - 16, "reintentou": reintentou}


def _mcq(oll, modelo, item, ctx, think, mult):
    rot, txt = item["rotulos"], item["textos"]
    ops = "\n".join(f"{a}. {b}" for a, b in zip(rot, txt))
    p = (f"Responda à questão de múltipla escolha. Escolha apenas uma alternativa e retorne somente sua letra "
         f"({', '.join(rot)}).\n\n{item['enunciado']}\n\n{ops}")
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "Você é um assistente que responde com precisão. Siga exatamente o formato pedido."},
                                           {"role": "user", "content": p}], ctx, 512 * mult, think)
    letra = P.extrair_letra((r.get("message") or {}).get("content", ""), "".join(rot))
    return letra == item["resposta"], {"previsto": letra, "esperado": item["resposta"]}, r, rei, lat


def s_mmlu_pt(oll, modelo, item, ctx, think, mult):
    return _mcq(oll, modelo, item, ctx, think, mult)


def s_mmlu_pro(oll, modelo, item, ctx, think, mult):
    letras = [chr(65 + i) for i in range(len(item["opcoes"]))]
    ops = "\n".join(f"{l}. {t}" for l, t in zip(letras, item["opcoes"]))
    p = f"Answer the multiple-choice question. Choose one option and return only its letter ({letras[0]}-{letras[-1]}). Do not explain.\n\n{item['pergunta']}\n\n{ops}"
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "Return only the requested answer letter."},
                                           {"role": "user", "content": p}], ctx, 512 * mult, think)
    letra = P.extrair_letra((r.get("message") or {}).get("content", ""), "".join(letras))
    return letra == item["resposta"], {"previsto": letra, "esperado": item["resposta"], "categoria": item["categoria"]}, r, rei, lat


def s_capitu(oll, modelo, item, ctx, think, mult):
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "Responda em português brasileiro. Siga todas as instruções explicitamente. Entregue apenas a resposta solicitada."},
                                           {"role": "user", "content": item["prompt"]}], ctx, 1536 * mult, think)
    texto = (r.get("message") or {}).get("content", "")
    ok, checks = P.capitu(item, texto)
    return ok, {"restricoes_ok": sum(checks), "restricoes": len(checks), "dificuldade": item["dificuldade"]}, r, rei, lat


def s_ifeval(oll, modelo, item, ctx, think, mult):
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "Follow the user instruction exactly. Provide only the requested answer."},
                                           {"role": "user", "content": item["prompt"]}], ctx, 768 * mult, think)
    ok = bool(P.ifeval(item["regra"], item["kwargs"], (r.get("message") or {}).get("content", "")))
    return ok, {"regra": item["regra"]}, r, rei, lat


def s_bfcl_prompt(oll, modelo, item, ctx, think, mult):
    q = "\n".join(m.get("content", "") for turn in item["pergunta"] for m in turn if m.get("role") == "user")
    p = ("You are evaluating an API tool call. Select the single correct function and arguments from the supplied functions. "
         "Return ONLY one JSON object with exactly this shape: {\"tool\":\"function.name\",\"arguments\":{...}}. "
         "Do not explain. Use argument names exactly as specified. If a value is ambiguous, use the explicit user request.\n\n"
         "FUNCTIONS:\n" + json.dumps(item["funcoes"], ensure_ascii=False, indent=1) + "\n\nUSER REQUEST:\n" + q)
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "Emitir somente a chamada de ferramenta em JSON válido."},
                                           {"role": "user", "content": p}], ctx, 512 * mult, think)
    ok, why = P.bfcl_prompt((r.get("message") or {}).get("content", ""), item["gt"])
    return ok, {"checagem": why, "tipo": item["tipo"]}, r, rei, lat


def s_bfcl_native(oll, modelo, item, ctx, think, mult):
    q = "\n".join(m.get("content", "") for turn in item["pergunta"] for m in turn if m.get("role") == "user")
    tools = [{"type": "function", "function": {"name": f["name"], "description": f.get("description", ""),
                                               "parameters": P.normalizar_schema(json.loads(json.dumps(f.get("parameters", {}))))}}
             for f in item["funcoes"]]
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "Select and call the correct function. Use the provided tool schema. Do not answer in prose."},
                                           {"role": "user", "content": q}], ctx, 512 * mult, think, tools=tools)
    ok, why, call = P.bfcl_nativo(r, item["gt"])
    return ok, {"checagem": why, "chamada": call, "tipo": item["tipo"]}, r, rei, lat


def s_humaneval(oll, modelo, item, ctx, think, mult):
    p = ("Complete the following Python function. Return ONLY valid Python code inside a ```python block. "
         "Do not write explanations:\n\n" + item["prompt"])
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "You are an expert Python coder. Output code only."},
                                           {"role": "user", "content": p}], ctx, 900 * mult, think)
    ok, why = P.humaneval(item, (r.get("message") or {}).get("content", ""))
    return ok, {"checagem": why}, r, rei, lat


def s_gsm8k(oll, modelo, item, ctx, think, mult):
    p = f"{item['pergunta']}\n\nShow your calculation step by step. Conclude your answer on the last line with: #### <final_number>"
    r, rei, lat = _perguntar(oll, modelo, [{"role": "system", "content": "You are a precise mathematician. Show calculation steps and end strictly with '#### <number>'."},
                                           {"role": "user", "content": p}], ctx, 900 * mult, think)
    ok, got = P.gsm8k((r.get("message") or {}).get("content", ""), item["resposta"])
    return ok, {"previsto": got, "esperado": item["resposta"]}, r, rei, lat


def s_visao(oll, modelo, item, ctx, think, mult):
    msgs = [
        {"role": "system", "content": "Analise a imagem com atenção e responda exatamente no formato pedido, sem explicações extras."},
        {"role": "user", "content": item["pergunta"], "images": [item["imagem"]]},
    ]
    r, rei, lat = _perguntar(oll, modelo, msgs, ctx, 384 * mult, think)
    ok, got = P.visao(item, (r.get("message") or {}).get("content", ""))
    return ok, {"previsto": got, "esperado": item["resposta"], "categoria": item.get("categoria")}, r, rei, lat


def _visao_curta(oll, modelo, item, ctx, think):
    msgs = [{"role": "user", "content": item["pergunta"], "images": [item["imagem"]]}]
    r, rei, lat = _perguntar(oll, modelo, msgs, ctx, 80, think)   # pergunta NATURAL (sem 'responda em uma palavra'): o Moondream devolve lixo com esse tipo de instrução; a resposta é lida da frase
    return r, rei, lat


def s_visao_leve(oll, modelo, item, ctx, think, mult):
    r, rei, lat = _visao_curta(oll, modelo, item, ctx, think)
    ok, got = P.visao_leve(item, (r.get("message") or {}).get("content", ""))
    return ok, {"previsto": got, "esperado": item["resposta"], "categoria": item.get("categoria")}, r, rei, lat


def s_visao_fotos(oll, modelo, item, ctx, think, mult):
    r, rei, lat = _visao_curta(oll, modelo, item, ctx, think)
    ok, got = P.visao_leve(item, (r.get("message") or {}).get("content", ""))
    return ok, {"previsto": got, "esperado": item["resposta"], "categoria": "foto", "arquivo": item.get("arquivo"), "detector": item.get("detector")}, r, rei, lat


EXECUTORES: Dict[str, Callable] = {
    "mmlu_pt": s_mmlu_pt, "mmlu_pro": s_mmlu_pro, "capitu": s_capitu, "ifeval": s_ifeval,
    "bfcl_prompt": s_bfcl_prompt, "bfcl_native": s_bfcl_native, "humaneval": s_humaneval, "gsm8k": s_gsm8k,
    "visao": s_visao, "visao_leve": s_visao_leve, "visao_fotos": s_visao_fotos,
}


def descobrir_think_base(oll: Ollama, modelo: str) -> Any:
    """O que significa "sem pensar" para ESTE modelo. O gpt-oss ignora `think:false` (pensa sempre, 1.500–6.000 tokens
    por resposta, e estoura o orçamento em tarefas longas); para ele o mais próximo de "base" é esforço `low`.
    Detecta pelo comportamento: pede uma conta simples com think=false e vê se veio raciocínio mesmo assim."""
    try:
        r = oll.chat(modelo, [{"role": "user", "content": "Quanto é 2+2? Responda só o número."}], ctx=2048, max_tokens=200, think=False, timeout=300)
    except ErroOllama:
        return False
    if not (r.get("message") or {}).get("thinking"):
        return False
    try:
        r = oll.chat(modelo, [{"role": "user", "content": "Quanto é 2+2? Responda só o número."}], ctx=2048, max_tokens=200, think="low", timeout=300)
        return "low" if r.get("message") is not None else False
    except ErroOllama:
        return False


def executar_item(oll: Ollama, suite: str, modelo: str, item: dict, ctx: int, modo: str = "base", think_base: Any = False) -> dict:
    think = True if modo == "think" else think_base
    mult = 4 if modo == "think" else 1
    t0 = time.perf_counter()
    try:
        ok, det, r, rei, lat = EXECUTORES[suite](oll, modelo, item, ctx, think, mult)
        msg = r.get("message") or {}
        m = _metricas(r, lat, ctx, rei)
        resp = P.limpar(msg.get("content", ""))
        if msg.get("tool_calls") and not resp:
            resp = json.dumps(msg["tool_calls"], ensure_ascii=False)
        return {"ok": bool(ok), "valido": not m["truncado"], "det": det, "resp": resp[:1200], **m,
                "pensou": bool(msg.get("thinking"))}
    except ErroOllama as e:
        return {"ok": False, "valido": False, "det": {"erro": str(e)[:300]}, "resp": "", "lat": round(time.perf_counter() - t0, 2)}
    except Exception as e:  # corretor quebrou: não pune o modelo
        return {"ok": False, "valido": False, "det": {"erro": f"corretor: {type(e).__name__}: {e}"[:300]}, "resp": "",
                "lat": round(time.perf_counter() - t0, 2)}
