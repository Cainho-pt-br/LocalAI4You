"""Quanto tempo o benchmark leva NESTA máquina, e qual profundidade ela aguenta.

O mesmo protocolo (mesmos itens congelados, em prefixos: mínimo ⊂ rápido ⊂ padrão ⊂ profundo) roda em qualquer máquina; o que muda é
quantos itens vale pedir. Uma CPU de 4 GB lê e gera ~2 tok/s: o nível Padrão (~300 itens) levaria dias. A conta é ESTIMADA
(velocidade de `fit.estimar_tps`), e quando já há medição de latência por item o painel usa a medida (ver `lab.plano`).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import fit
from . import amostras, suites

ORDEM = ["minimo", "rapido", "padrao", "profundo"]
# "tokens equivalentes de geração" por item (prompt + resposta). Na GPU a leitura do prompt é quase de graça; na CPU ela pesa.
# Calibrado no Raspberry Pi 5 (qwen3.5 0.8B Q8: ~130 s por item a ~2 tok/s) e no boss (~3 s por item a ~35 tok/s).
TOKENS_POR_ITEM = {"gpu": 120, "cpu": 280}
# imagem pesa mais que um item de texto: leitor de imagem + prompt. Calibrado só na Pi (qwen3.5 0.8B: 38 s a ~4 tok/s; 2B: 119 s a ~1,3 tok/s → ~155);
# na GPU é chute (ainda não há medição de visão em GPU).
VISAO_TOKENS_POR_ITEM = {"gpu": 100, "cpu": 160}
BUDGET_RECOMENDADO_S = 90 * 60     # o que o painel sugere como padrão para o conjunto de modelos escolhido
LIMITE_DURO_S = 3 * 3600           # acima disso o servidor reduz o nível sozinho (a menos que o usuário force)


def itens_do_nivel(nivel: str) -> int:
    return sum(n for s, n in amostras.NIVEIS[nivel].items() if s in suites.ORDEM)


def itens_visao(nivel: str) -> int:
    """Imagens por modelo que declara visão (visao_fotos só conta se houver fotos cadastradas)."""
    return sum(len(amostras.itens_do_nivel(s, nivel)) for s in suites.SUITES_EXTRAS)


def _tps_medio(maq: dict, peso_bytes: int) -> Optional[float]:
    tps = fit.estimar_tps(int(peso_bytes), maq)
    return (max(tps[0], 0.1) * max(tps[1], 0.1)) ** 0.5 if tps else None   # média geométrica da faixa estimada


def seg_por_item(maq: dict, peso_bytes: int) -> float:
    gpu = bool((maq.get("gpu") or {}).get("vram_gb"))
    medio = _tps_medio(maq, peso_bytes)
    return TOKENS_POR_ITEM["gpu" if gpu else "cpu"] / medio if medio else 5.0


def seg_por_imagem(maq: dict, peso_bytes: int) -> float:
    gpu = bool((maq.get("gpu") or {}).get("vram_gb"))
    medio = _tps_medio(maq, peso_bytes)
    return VISAO_TOKENS_POR_ITEM["gpu" if gpu else "cpu"] / medio if medio else 30.0


def segundos(maq: dict, pesos: List[int], nivel: str, visao: Optional[List[bool]] = None) -> int:
    """`visao[i]` = o modelo i declara visão (então roda também as imagens do nível)."""
    total = sum(seg_por_item(maq, p) for p in pesos) * itens_do_nivel(nivel)
    if visao:
        total += sum(seg_por_imagem(maq, p) for p, v in zip(pesos, visao) if v) * itens_visao(nivel)
    return int(total)


def tabela(maq: dict, pesos: List[int], visao: Optional[List[bool]] = None) -> List[dict]:
    out = []
    for nv in ORDEM:
        seg = segundos(maq, pesos, nv, visao)
        out.append({"id": nv, "itens": itens_do_nivel(nv), "imagens": itens_visao(nv) if visao and any(visao) else 0,
                    "segundos": seg, "minutos": max(1, round(seg / 60))})
    return out


def recomendado(maq: dict, pesos: List[int], visao: Optional[List[bool]] = None) -> str:
    """O maior nível, até o Padrão, que cabe no orçamento de ~90 min; senão o mínimo."""
    melhor = "minimo"
    for nv in ORDEM[:3]:
        if segundos(maq, pesos, nv, visao) <= BUDGET_RECOMENDADO_S:
            melhor = nv
    return melhor


def limitar(maq: dict, pesos: List[int], pedido: str, visao: Optional[List[bool]] = None) -> str:
    """Se o nível pedido passa de 3 h, devolve o maior que cabe (ou o mínimo)."""
    if not pesos or segundos(maq, pesos, pedido, visao) <= LIMITE_DURO_S:
        return pedido
    for nv in reversed(ORDEM[:ORDEM.index(pedido)]):
        if segundos(maq, pesos, nv, visao) <= LIMITE_DURO_S:
            return nv
    return "minimo"


def resumo(maq: dict, pesos: List[int], visao: Optional[List[bool]] = None) -> Dict[str, object]:
    return {"maquina": maq.get("nome") or maq.get("id"), "sem_gpu": not (maq.get("gpu") or {}).get("vram_gb"),
            "niveis": tabela(maq, pesos, visao), "recomendado": recomendado(maq, pesos, visao)}
