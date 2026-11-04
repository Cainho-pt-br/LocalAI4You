"""Armazém e agregação dos resultados (um único arquivo JSONL, uma linha por tentativa).

Chave de unicidade: (digest do modelo, protocolo, suíte, item, modo). Se a tag do Ollama for
atualizada o digest muda e os resultados antigos deixam de valer para o modelo novo — sem apagar nada.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from . import PROTOCOLO, config, papeis
from .bench import stats
from .util import anexar_jsonl, ler_jsonl, agora_iso


def anexar(linha: dict) -> None:
    linha.setdefault("ts", agora_iso())
    linha.setdefault("protocolo", PROTOCOLO)
    anexar_jsonl(config.RESULTADOS, linha)


def carregar(protocolo: Optional[str] = PROTOCOLO) -> List[dict]:
    rows = ler_jsonl(config.RESULTADOS)
    return [r for r in rows if protocolo is None or r.get("protocolo") == protocolo]


def chaves_feitas(modelo: str, digest: str, modo: str, nivel_suites: Optional[set] = None) -> set:
    """{(suite, item)} já medidos com resposta válida — base do 'retomar de onde parou'."""
    feitos = set()
    for r in carregar():
        if r.get("modelo") == modelo and r.get("digest") == digest and r.get("modo", "base") == modo and r.get("valido") and r.get("suite") != "_meta":
            feitos.add((r["suite"], r["item"]))
    return feitos


def _indice(rows: List[dict]) -> Dict[Tuple[str, str, str], dict]:
    """(modelo, digest, modo) → {'suites': {suite: {item: 0/1}}, 'tps': [..], 'meta': {...}}"""
    idx: Dict[Tuple[str, str, str], dict] = {}
    for r in rows:
        k = (r["modelo"], r.get("digest", ""), r.get("modo", "base"))
        e = idx.setdefault(k, {"suites": defaultdict(dict), "tps": [], "meta": {}, "ultima": ""})
        e["ultima"] = max(e["ultima"], r.get("ts", ""))
        if r.get("suite") == "_meta":
            e["meta"] = r.get("det", {})
            continue
        if not r.get("valido"):
            continue
        e["suites"][r["suite"]][r["item"]] = 1 if r.get("ok") else 0
        if r.get("tps"):
            e["tps"].append(r["tps"])
    return idx


def resumo(modelo: str, digest: Optional[str] = None, modo: str = "base", rows: Optional[List[dict]] = None) -> Optional[dict]:
    rows = rows if rows is not None else carregar()
    idx = _indice(rows)
    cand = [(k, v) for k, v in idx.items() if k[0] == modelo and k[2] == modo and (digest is None or k[1] == digest)]
    if not cand:
        return None
    (_, dg, _), e = max(cand, key=lambda kv: kv[1]["ultima"])
    suites = {}
    for s, itens in e["suites"].items():
        n, k = len(itens), sum(itens.values())
        suites[s] = {"n": n, "k": k, "acc": round(100 * k / n, 1), "ic": stats.wilson(k, n)}
    ac = {s: list(i.values()) for s, i in e["suites"].items()}
    pap = {}
    for p in papeis.PAPEIS:
        if p.get("sem_nota"):
            continue
        pesos = p["pesos"]
        cob = stats.cobertura(ac, pesos)
        if cob < 0.5:
            pap[p["id"]] = {"nota": None, "cobertura": round(cob, 2)}
            continue
        ic = stats.bootstrap_composto(ac, pesos, reps=800)
        pap[p["id"]] = {"nota": stats.composto(ac, pesos), "ic": ic, "cobertura": round(cob, 2)}
    return {"modelo": modelo, "digest": dg, "modo": modo, "suites": suites, "papeis": pap,
            "tps_mediana": stats.mediana(e["tps"]), "meta": e["meta"], "ultima": e["ultima"],
            "n_itens": sum(len(i) for s, i in e["suites"].items() if s not in ("visao_leve", "visao_fotos"))}   # extras não contam para "nível atingido"


def acertos(modelo: str, digest: str, modo: str = "base", rows: Optional[List[dict]] = None) -> Dict[str, Dict[str, int]]:
    idx = _indice(rows if rows is not None else carregar())
    e = idx.get((modelo, digest, modo))
    return {s: dict(i) for s, i in e["suites"].items()} if e else {}


def modelos_medidos(rows: Optional[List[dict]] = None) -> List[dict]:
    rows = rows if rows is not None else carregar()
    return [{"modelo": k[0], "digest": k[1], "modo": k[2], "ultima": v["ultima"], "itens": sum(len(i) for i in v["suites"].values())}
            for k, v in _indice(rows).items()]


def comparar(a: Tuple[str, str], b: Tuple[str, str], papel_id: str, modo: str = "base", reps: int = 2000,
             rows: Optional[List[dict]] = None) -> Optional[dict]:
    rows = rows if rows is not None else carregar()
    pesos = papeis.pesos_do_papel(papel_id)
    if not pesos:
        return None
    ca = acertos(a[0], a[1], modo, rows)
    cb = acertos(b[0], b[1], modo, rows)
    c = stats.comparar_pareado(ca, cb, pesos, reps=reps)
    if not c:
        return None
    c["veredito"] = stats.veredito_pareado(c)
    c["papel"] = papel_id
    return c
