"""Amostras congeladas dos conjuntos públicos.

Regras: (1) determinísticas — o mesmo item vai para todo modelo, hoje e daqui a dois meses;
(2) ordenadas de forma balanceada — qualquer prefixo da lista (nível "rápido" ⊂ "padrão" ⊂ "profundo")
mantém o equilíbrio entre domínios/dificuldades, então resultados de níveis diferentes são comparáveis
nos itens em comum; (3) congeladas em data/amostras/ depois da 1ª vez, para funcionar sem internet.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict, List

from .. import config
from ..util import agora_iso, gravar_json, http_json, ler_json, sha256_texto
from . import visao_gerador

DADOS = config.DADOS
VERSAO_AMOSTRAS = "2026-10-a"

NIVEIS = {
    # "minimo": para CPU/Raspberry (cada item leva minutos). Mesmos itens congelados, só menos deles: a margem de erro é grande e o painel mostra.
    "minimo":   {"mmlu_pt": 6, "mmlu_pro": 4, "capitu": 2, "ifeval": 3, "bfcl_prompt": 3, "bfcl_native": 3, "humaneval": 4, "gsm8k": 4, "visao": 0, "visao_leve": 5, "visao_fotos": 3},
    "rapido":   {"mmlu_pt": 16, "mmlu_pro": 14, "capitu": 12, "ifeval": 9, "bfcl_prompt": 12, "bfcl_native": 12, "humaneval": 16, "gsm8k": 16, "visao": 6, "visao_leve": 10, "visao_fotos": 8},
    "padrao":   {"mmlu_pt": 48, "mmlu_pro": 56, "capitu": 36, "ifeval": 27, "bfcl_prompt": 24, "bfcl_native": 24, "humaneval": 40, "gsm8k": 40, "visao": 12, "visao_leve": 20, "visao_fotos": 20},
    "profundo": {"mmlu_pt": 96, "mmlu_pro": 98, "capitu": 72, "ifeval": 45, "bfcl_prompt": 48, "bfcl_native": 48, "humaneval": 80, "gsm8k": 80, "visao": 18, "visao_leve": 30, "visao_fotos": 60},
}
IFEVAL_REGRAS = ['punctuation:no_comma', 'change_case:english_lowercase', 'change_case:english_capital',
                 'keywords:existence', 'keywords:forbidden_words', 'keywords:frequency',
                 'detectable_format:json_format', 'detectable_format:number_bullet_lists', 'startend:end_checker']
DS = "https://datasets-server.huggingface.co/rows?dataset={ds}&config={cfg}&split={split}&offset={off}&length={n}"


def _jsonl(path: Path) -> List[dict]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def _intercalar(grupos: List[List[Any]]) -> List[Any]:
    """[[a1,a2],[b1,b2]] → [a1,b1,a2,b2] (rodízio: mantém o balanço em qualquer prefixo)."""
    out, i = [], 0
    while any(i < len(g) for g in grupos):
        for g in grupos:
            if i < len(g):
                out.append(g[i])
        i += 1
    return out


def _espacado(itens: List[Any], n: int) -> List[Any]:
    if len(itens) <= n:
        return list(itens)
    return [itens[round(i * (len(itens) - 1) / (n - 1))] for i in range(n)] if n > 1 else [itens[0]]


def _linhas_ds(ds: str, cfg: str, split: str, offset: int, n: int) -> List[dict]:
    url = DS.format(ds=ds.replace("/", "%2F"), cfg=cfg, split=split, off=offset, n=n)
    return [r["row"] for r in http_json(url, timeout=40)["rows"]]


# ------------------------------------------------------------------ construtores

def _mmlu_pt(maximo: int) -> List[dict]:
    por_dom: Dict[str, List[dict]] = {}
    antigo = ler_json(DADOS / "mmlu_pt_sample.json", []) or []
    for r in antigo:
        por_dom.setdefault(r.get("_domain", "?"), []).append(r)
    dominios = ["health_and_biological_sciences", "humanities", "languages", "stem"]
    falta = max(maximo // 4, 8)
    for d in dominios:
        if len(por_dom.get(d, [])) < falta:
            try:
                rows = _linhas_ds("mmlu-pt/mmlu-pt-high-school-hard", "default", d, 0, falta)
                for r in rows:
                    r["_domain"] = d
                por_dom[d] = rows
            except Exception:
                pass  # sem internet: fica com o que já existe
    itens = []
    for dom, rows in por_dom.items():
        for r in rows:
            alt = r["alternatives"]
            if isinstance(alt, str):
                alt = ast.literal_eval(alt)
            itens.append((dom, {"id": f"{dom}:{r.get('num')}", "dominio": dom, "enunciado": r["statement"],
                                "rotulos": alt.get("label", []), "textos": alt.get("text", []), "resposta": r["answer"].strip().upper()}))
    grupos = [[it for d, it in itens if d == dom] for dom in dominios]
    return _intercalar(grupos)


def _mmlu_pro(maximo: int) -> List[dict]:
    antigos = ler_json(DADOS / "mmlu_pro_sample.json", []) or []
    pool: Dict[str, List[dict]] = {}
    for r in antigos:
        pool.setdefault(r["category"], []).append(r)
    por_cat = max(maximo // 14, 2)
    if len(pool) < 14 or min(len(v) for v in pool.values()) < por_cat:
        import time
        for off in list(range(0, 12000, 400)) + list(range(200, 12000, 400)):
            if len(pool) >= 14 and min(len(v) for v in pool.values()) >= por_cat:
                break
            try:
                rows = _linhas_ds("TIGER-Lab/MMLU-Pro", "default", "test", off, 100)
            except Exception:
                continue
            for r in rows:
                lista = pool.setdefault(r["category"], [])
                if len(lista) < 40 and all(x["question_id"] != r["question_id"] for x in lista):
                    lista.append(r)
            time.sleep(0.5)
    ids_antigos = {r["question_id"] for r in antigos}
    grupos = []
    for c in sorted(pool):
        rows = sorted(pool[c], key=lambda r: r["question_id"])
        rows = [r for r in rows if r["question_id"] in ids_antigos] + [r for r in rows if r["question_id"] not in ids_antigos]
        grupos.append([{"id": str(r["question_id"]), "categoria": c, "pergunta": r["question"], "opcoes": r["options"],
                        "resposta": r["answer"].strip().upper()} for r in rows[:por_cat]])
    return _intercalar(grupos)


def _capitu(maximo: int) -> List[dict]:
    def parse(v):
        return ast.literal_eval(v) if isinstance(v, str) else v
    todos = _jsonl(DADOS / "capitu" / "input_questions.jsonl")
    antigos = {str(x["key"]) for x in (ler_json(DADOS / "capitu_sample.json", []) or [])}
    grupos = []
    for dif in ("easy", "medium", "hard"):
        rows = [r for r in todos if r.get("difficulty") == dif]
        rows.sort(key=lambda r: (str(r["key"]) not in antigos, int(r["key"])))
        grupos.append([{"id": str(r["key"]), "dificuldade": dif, "prompt": r["prompt"],
                        "instrucoes": parse(r["instruction_id_list"]), "kwargs": parse(r["kwargs"])} for r in rows[: maximo // 3]])
    return _intercalar(grupos)


def _ifeval(maximo: int) -> List[dict]:
    por_regra: Dict[str, List[dict]] = {r: [] for r in IFEVAL_REGRAS}
    for x in _jsonl(DADOS / "ifeval_input_data.jsonl"):
        ids, kw = x.get("instruction_id_list", []), x.get("kwargs", {})
        if len(ids) != 1 or ids[0] not in por_regra:
            continue
        kw = kw[0] if isinstance(kw, list) and kw else (kw if isinstance(kw, dict) else {})
        if ids[0] == "keywords:frequency" and int(kw.get("frequency", 0) or 0) > 5:
            continue
        if ids[0] == "detectable_format:number_bullet_lists" and int(kw.get("num_bullets", 0) or 0) > 5:
            continue
        por_regra[ids[0]].append({"id": str(x["key"]), "regra": ids[0], "prompt": x["prompt"], "kwargs": kw})
    return _intercalar([v[: maximo // len(IFEVAL_REGRAS) + 1] for v in por_regra.values()])


def _bfcl(maximo: int) -> List[dict]:
    out = []
    for nome, arq, resp in (("simple", "bfcl_v4_live_simple.jsonl", "bfcl_v4_live_simple_answers.jsonl"),
                            ("multiple", "bfcl_v4_live_multiple.jsonl", "bfcl_v4_live_multiple_answers.jsonl")):
        itens = {x["id"]: x for x in _jsonl(DADOS / arq)}
        gt = {x["id"]: x["ground_truth"] for x in _jsonl(DADOS / resp)}
        ids = sorted(itens)
        out.append([{"id": i, "tipo": nome, "pergunta": itens[i]["question"], "funcoes": itens[i]["function"], "gt": gt[i]}
                    for i in _espacado(ids, maximo // 2) if i in gt])
    return _intercalar(out)


def _humaneval(maximo: int) -> List[dict]:
    try:
        rows = _linhas_ds("openai/openai_humaneval", "openai_humaneval", "test", 0, 100) + \
               _linhas_ds("openai/openai_humaneval", "openai_humaneval", "test", 100, 100)
    except Exception:
        rows = ler_json(DADOS / "humaneval_sample.json", []) or []
    rows.sort(key=lambda r: int(r["task_id"].split("/")[1]))
    sel = _espacado(rows, maximo)
    return [{"id": r["task_id"], "prompt": r["prompt"], "teste": r["test"], "entrada": r["entry_point"]} for r in sel]


def _gsm8k(maximo: int) -> List[dict]:
    rows: List[dict] = []
    try:
        for off in range(0, 1319, 100):
            rows += _linhas_ds("openai/gsm8k", "main", "test", off, min(100, 1319 - off))
    except Exception:
        rows = [{"question": r["question"], "answer": r["answer"]} for r in (ler_json(DADOS / "gsm8k_sample.json", []) or [])]
    sel = _espacado(rows, maximo)
    return [{"id": f"gsm8k-{i}", "pergunta": r["question"], "resposta": r["answer"].split("####")[-1].strip().replace(",", "")}
            for i, r in enumerate(sel)]


def _visao(maximo: int) -> List[dict]:
    return visao_gerador.construir_itens(maximo)


CONSTRUTORES = {"mmlu_pt": _mmlu_pt, "mmlu_pro": _mmlu_pro, "capitu": _capitu, "ifeval": _ifeval,
                "bfcl": _bfcl, "humaneval": _humaneval, "gsm8k": _gsm8k, "visao": _visao,
                "visao_leve": visao_gerador.construir_itens_leve}
_ARQUIVO = {"bfcl_prompt": "bfcl", "bfcl_native": "bfcl"}


def carregar(suite: str, forcar: bool = False) -> dict:
    """Amostra congelada da suíte (constrói e grava na 1ª vez)."""
    base = _ARQUIVO.get(suite, suite)
    arq = config.AMOSTRAS / f"{base}.json"
    dado = None if forcar else ler_json(arq)
    if not dado or dado.get("versao") != VERSAO_AMOSTRAS:
        maximo = max(n[suite] for n in NIVEIS.values())
        itens = CONSTRUTORES[base](maximo)
        dado = {"suite": base, "versao": VERSAO_AMOSTRAS, "gerado_em": agora_iso(), "n": len(itens),
                "sha256": sha256_texto(json.dumps(itens, sort_keys=True, ensure_ascii=False)), "itens": itens}
        gravar_json(arq, dado, indent=0)
    return _ids_unicos(dado)


def _ids_unicos(dado: dict) -> dict:
    """O MMLU-PT repete `exame:número` entre edições da prova (10 colisões em 96 itens): o 2º, 3º… ganha sufixo `#n`.
    Feito na leitura, na ordem congelada — determinístico, sem mexer no arquivo nem no hash da amostra."""
    vistos: Dict[str, int] = {}
    for it in dado["itens"]:
        vistos[it["id"]] = vistos.get(it["id"], 0) + 1
        if vistos[it["id"]] > 1:
            it["id"] = f"{it['id']}#{vistos[it['id']]}"
    return dado


FOTOS = DADOS / "fotos-visao"   # fotos reais do Caio + gabarito.json (ver visao_gerador.itens_fotos)


def itens_do_nivel(suite: str, nivel: str) -> List[dict]:
    n = NIVEIS[nivel][suite]
    if suite == "visao_fotos":
        return visao_gerador.itens_fotos(FOTOS, n)
    if suite == "visao_leve":   # gerado na hora (determinístico): sem arquivo congelado, assim mudar uma pergunta não fica preso num cache velho
        return visao_gerador.construir_itens_leve(n)
    return carregar(suite)["itens"][:n]


def resumo() -> Dict[str, dict]:
    out = {}
    for s in NIVEIS["padrao"]:
        if s == "visao_fotos":
            out[s] = {"n_total": len(visao_gerador.itens_fotos(FOTOS)), "sha": "suas fotos"}
            continue
        if s == "visao_leve":
            out[s] = {"n_total": len(visao_gerador.construir_itens_leve(30)), "sha": "gerado"}
            continue
        try:
            d = carregar(s)
            out[s] = {"n_total": d["n"], "sha": d["sha256"][:12]}
        except Exception as e:
            out[s] = {"erro": str(e)[:120]}
    return out
