"""Estatística honesta para amostras pequenas: intervalo de Wilson e bootstrap pareado.

Com n≈30 por teste, 10 pontos de diferença é ruído. Estas funções existem para o painel dizer
"empate técnico" em vez de coroar um vencedor que a amostra não sustenta.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple


def wilson(k: int, n: int, z: float = 1.645) -> Tuple[float, float]:
    """Intervalo de confiança de ~90% para uma proporção (devolve 0–100)."""
    if n <= 0:
        return (0.0, 100.0)
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    margem = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(100 * max(0.0, centro - margem), 1), round(100 * min(1.0, centro + margem), 1))


def composto(acertos: Dict[str, List[int]], pesos: Dict[str, float]) -> Optional[float]:
    """Média ponderada das taxas de acerto por suíte (pesos renormalizados sobre o que existe)."""
    num = den = 0.0
    for s, p in pesos.items():
        v = acertos.get(s)
        if v:
            num += p * (sum(v) / len(v))
            den += p
    return round(100 * num / den, 1) if den else None


def cobertura(acertos: Dict[str, List[int]], pesos: Dict[str, float]) -> float:
    tot = sum(pesos.values())
    return sum(p for s, p in pesos.items() if acertos.get(s)) / tot if tot else 0.0


def bootstrap_composto(acertos: Dict[str, List[int]], pesos: Dict[str, float], reps: int = 1500,
                       seed: int = 7) -> Optional[Tuple[float, float]]:
    """IC de ~90% do composto, reamostrando itens dentro de cada suíte."""
    rng = random.Random(seed)
    suites = [s for s in pesos if acertos.get(s)]
    if not suites:
        return None
    vals = []
    for _ in range(reps):
        amostra = {s: [acertos[s][rng.randrange(len(acertos[s]))] for _ in acertos[s]] for s in suites}
        vals.append(composto(amostra, pesos))
    vals.sort()
    return (vals[int(0.05 * reps)], vals[int(0.95 * reps) - 1])


def comparar_pareado(a: Dict[str, Dict[str, int]], b: Dict[str, Dict[str, int]], pesos: Dict[str, float],
                     reps: int = 2000, seed: int = 11) -> Optional[dict]:
    """Compara dois modelos nos MESMOS itens. `a[suite][item_id] = 0/1`.

    Devolve diferença do composto (a − b), IC de 90% por bootstrap pareado e o placar de vitórias
    por item (itens em que só A acertou, só B acertou). Usa só itens que ambos responderam.
    """
    comuns: Dict[str, List[str]] = {}
    for s in pesos:
        ids = sorted(set(a.get(s, {})) & set(b.get(s, {})))
        if ids:
            comuns[s] = ids
    if not comuns:
        return None
    A = {s: [a[s][i] for i in ids] for s, ids in comuns.items()}
    B = {s: [b[s][i] for i in ids] for s, ids in comuns.items()}
    sa, sb = composto(A, pesos), composto(B, pesos)
    rng = random.Random(seed)
    difs = []
    for _ in range(reps):
        ca, cb = {}, {}
        for s, ids in comuns.items():
            idx = [rng.randrange(len(ids)) for _ in ids]
            ca[s] = [A[s][i] for i in idx]
            cb[s] = [B[s][i] for i in idx]
        difs.append(composto(ca, pesos) - composto(cb, pesos))
    difs.sort()
    so_a = sum(1 for s in comuns for x, y in zip(A[s], B[s]) if x and not y)
    so_b = sum(1 for s in comuns for x, y in zip(A[s], B[s]) if y and not x)
    return {
        "a": sa, "b": sb, "dif": round(sa - sb, 1), "ic": (round(difs[int(0.05 * reps)], 1), round(difs[int(0.95 * reps) - 1], 1)),
        "so_a": so_a, "so_b": so_b, "itens": sum(len(v) for v in comuns.values()),
        "suites": {s: len(v) for s, v in comuns.items()},
        "cobertura": round(cobertura(A, pesos), 2),
    }


def veredito_pareado(cmp: dict, margem_pratica: float = 3.0) -> str:
    """'superior' | 'inferior' | 'empate'. Exige IC fora de zero E diferença maior que a margem prática."""
    lo, hi = cmp["ic"]
    if lo > 0 and cmp["dif"] >= margem_pratica:
        return "superior"
    if hi < 0 and cmp["dif"] <= -margem_pratica:
        return "inferior"
    return "empate"


def mediana(xs: Sequence[float]) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 1)
