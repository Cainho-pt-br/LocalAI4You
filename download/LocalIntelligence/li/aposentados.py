"""Modelos aposentados: o que saiu do disco e a nota que tinha.

A medição não some quando o modelo é apagado — `resultados.jsonl` guarda tudo, indexado pelo digest do arquivo. Aqui
juntamos dois fatos: (1) o registro que o painel grava ao aposentar (quando, quanto liberou, por quê, quem herdou as
funções) e (2) qualquer modelo medido que não está mais instalado (inclui os apagados fora do painel, pela linha de
comando ou pelo `ollama rm`, que não deixam registro: aparecem sem data de remoção).

Se o MESMO arquivo voltar (mesmo digest), a medição antiga volta a valer sem refazer nada.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import config, resultados
from .util import agora_iso, gravar_json, ler_json

_CACHE: Dict[str, object] = {}


def carregar() -> List[dict]:
    return ler_json(config.APOSENTADOS, []) or []


def registrar(modelo: str, digest: str, bytes_: int, motivo: str, titular_de: Optional[List[str]] = None,
              herdeiros: Optional[Dict[str, str]] = None) -> dict:
    reg = {"modelo": modelo, "digest": digest, "quando": agora_iso(), "bytes": int(bytes_), "motivo": motivo,
           "titular_de": list(titular_de or []), "herdeiros": dict(herdeiros or {})}
    lista = [r for r in carregar() if not (r.get("modelo") == modelo and r.get("digest") == digest)]
    lista.append(reg)
    gravar_json(config.APOSENTADOS, lista)
    _CACHE.clear()
    return reg


def _chave(inst: List[dict]) -> tuple:
    def mt(p):
        try:
            st = p.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return (0, 0)
    return (mt(config.RESULTADOS), mt(config.APOSENTADOS), tuple(sorted((m["id"], m["digest"]) for m in inst)))


def listar(inst: List[dict]) -> List[dict]:
    """Aposentados do mais recente para o mais antigo, cada um com as notas medidas (quando existem)."""
    chave = _chave(inst)
    if _CACHE.get("chave") == chave:
        return _CACHE["lista"]  # type: ignore[return-value]
    rows = resultados.carregar()
    instalados = {m["id"]: m["digest"] for m in inst}
    regs = {(r.get("modelo"), r.get("digest")): r for r in carregar()}
    vistos = set()
    out: List[dict] = []
    for it in sorted(resultados.modelos_medidos(rows), key=lambda x: x["ultima"], reverse=True):
        k = (it["modelo"], it["digest"])
        if k in vistos or it["modo"] != "base":
            continue
        if instalados.get(it["modelo"]) == it["digest"]:
            continue  # este arquivo está instalado: não é aposentado
        vistos.add(k)
        r = resultados.resumo(it["modelo"], it["digest"], "base", rows)
        reg = regs.get(k) or {}
        out.append({
            "modelo": it["modelo"], "digest": it["digest"], "quando": reg.get("quando"), "bytes": reg.get("bytes"),
            "motivo": reg.get("motivo"), "titular_de": reg.get("titular_de", []), "herdeiros": reg.get("herdeiros", {}),
            "ultima_medicao": it["ultima"], "n_itens": r["n_itens"] if r else 0, "tps": r["tps_mediana"] if r else None,
            "papeis": {pid: {"nota": v.get("nota"), "ic": v.get("ic")} for pid, v in (r["papeis"] if r else {}).items() if v.get("nota") is not None},
            # a tag foi atualizada no Ollama e o arquivo mudou: a medição é da versão antiga
            "versao_antiga": it["modelo"] in instalados, "registrado": bool(reg),
        })
    for k, reg in regs.items():  # aposentado sem medição guardada (nunca foi medido neste protocolo)
        if k in vistos or instalados.get(k[0]) == k[1]:
            continue
        vistos.add(k)
        out.append({"modelo": reg["modelo"], "digest": reg["digest"], "quando": reg.get("quando"), "bytes": reg.get("bytes"),
                    "motivo": reg.get("motivo"), "titular_de": reg.get("titular_de", []), "herdeiros": reg.get("herdeiros", {}),
                    "ultima_medicao": None, "n_itens": 0, "tps": None, "papeis": {}, "versao_antiga": False, "registrado": True})
    out.sort(key=lambda x: x.get("quando") or x.get("ultima_medicao") or "", reverse=True)
    _CACHE["chave"], _CACHE["lista"] = chave, out
    return out
