"""Explorador de quantizações: para UM modelo do radar, todas as formas de baixá-lo e onde ver cada uma.

O radar guarda, por modelo, as variantes que a biblioteca do Ollama publica (e poucos GGUF do Hugging Face dos modelos grandes).
Mas quem escolhe uma quantização quer ver TODAS: as do Ollama e as dos GGUF que a comunidade publica (unsloth, bartowski,
lmstudio-community…), cada uma com o tamanho real, o link da página e o comando exato. Aqui isso é buscado sob demanda (e
fica em cache), em vez de inflar a varredura inteira.

O cálculo "cabe na minha placa?" de cada variante é feito no navegador (web/calc.js), com o hardware que a pessoa escolher.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import quote

from . import config, scout
from .calc import arch_compacta
from .fontes import hf
from .util import mapa_paralelo


class ErroQuants(Exception):
    pass


def _candidato(cand_id: str) -> dict:
    snap = scout.ultimo()
    if not snap:
        raise ErroQuants("Radar sem dados: rode a varredura antes.")
    for c in snap["candidatos"]:
        if c["id"] == cand_id:
            return c
    raise ErroQuants(f"Candidato {cand_id} não está no último radar.")


def _base_hf(c: dict) -> Optional[str]:
    """O repositório 'de origem' no Hugging Face (de onde saem as quantizações)."""
    repo = c.get("repo")
    if repo and "gguf" in repo.lower():  # o repo achado já é um GGUF: o modelo-base está no cartão dele
        det = hf.detalhe(repo) or {}
        base = (det.get("cardData") or {}).get("base_model")
        if isinstance(base, list):
            base = base[0] if base else None
        return base if isinstance(base, str) and "/" in base else None
    return repo


def _repos_gguf(c: dict, limite: int = 6) -> List[dict]:
    cfg = config.carregar()
    confiaveis = {q.lower() for q in cfg.get("quantizadores_confiaveis", [])}
    base = _base_hf(c)
    achados = list(hf.repos_gguf_do_base(base)) if base else []
    ids = {a.get("id") for a in achados}
    for extra in (c.get("repo_gguf"), c.get("repo") if "gguf" in (c.get("repo") or "").lower() else None):
        if extra and extra not in ids:  # o que o radar já conhece entra mesmo que a busca por base_model não o devolva
            achados.append({"id": extra, "downloads": c.get("baixas") or 0})
            ids.add(extra)
    autor_base = (base or c.get("repo") or "/").split("/")[0].lower()
    ok = []
    for it in achados:
        rid = it.get("id", "")
        autor = rid.split("/")[0].lower()
        if "gguf" not in rid.lower() and "gguf" not in " ".join(it.get("tags", [])).lower():
            continue
        if autor in confiaveis or autor == autor_base or rid in (c.get("repo_gguf"), c.get("repo")):
            ok.append(it)
    ok.sort(key=lambda it: -int(it.get("downloads", 0) or 0))
    return ok[:limite]


def _links(c: dict, repos: List[dict]) -> Dict[str, Optional[str]]:
    nome = c.get("familia") if c["origem"] == "ollama" else None
    base = _base_hf(c) or c.get("repo")
    busca = quote(f"{c['nome']} gguf")
    return {
        "ollama": f"https://ollama.com/library/{nome}" if nome else None,
        "ollama_tags": f"https://ollama.com/library/{nome}/tags" if nome else None,
        "hf_base": f"https://huggingface.co/{base}" if base else None,
        "hf_quantizados": f"https://huggingface.co/models?other=base_model:quantized:{quote(base, safe='/')}&sort=downloads" if base else None,
        "hf_busca": f"https://huggingface.co/models?search={busca}&sort=downloads",
        "hf_gguf": [f"https://huggingface.co/{r['id']}" for r in repos[:3]],
    }


def explorar(cand_id: str, forcar: bool = False) -> dict:
    c = _candidato(cand_id)
    aviso = None
    fontes: List[dict] = []
    nativas = [v for v in c["variantes"] if v.get("fonte") != "hf" and not str(v.get("pull", "")).startswith("hf.co/")]
    if nativas:
        fontes.append({"id": "ollama", "tipo": "ollama", "nome": "Biblioteca do Ollama (oficial)",
                       "url": f"https://ollama.com/library/{c['familia']}/tags" if c["origem"] == "ollama" else None,
                       "confianca": "oficial", "baixas": c.get("pulls"),
                       "variantes": [{"quant": v["quant"], "bytes": v["bytes"], "extra_bytes": int(v.get("extra_bytes", 0)),
                                      "pull": v["pull"], "tag": v["tag"], "padrao": bool(v.get("padrao"))} for v in nativas]})
    try:
        repos = _repos_gguf(c)
    except Exception as e:  # sem internet / HF fora do ar: mostra o que o radar já tinha
        repos, aviso = [], f"Não consegui consultar o Hugging Face agora ({e}). Mostrando só o que o radar já conhecia."
    arqs = mapa_paralelo(lambda r: hf.arquivos_gguf(r["id"], forcar), repos, workers=4)
    for r, arq in zip(repos, arqs):
        if not arq or not arq.get("variantes"):
            continue
        autor = r["id"].split("/")[0]
        fontes.append({"id": r["id"], "tipo": "hf", "nome": r["id"], "autor": autor, "url": f"https://huggingface.co/{r['id']}",
                       "confianca": "laboratório" if autor.lower() == (_base_hf(c) or "/").split("/")[0].lower() else "quantizador conhecido",
                       "baixas": r.get("downloads"), "mmproj_bytes": int(arq.get("mmproj_bytes") or 0),
                       "variantes": [{"quant": v["quant"], "bytes": v["bytes"], "extra_bytes": int(arq.get("mmproj_bytes") or 0) if "vision" in (c.get("caps") or []) else 0,
                                      "pull": f"hf.co/{r['id']}:{v['quant']}", "tag": v["quant"], "arquivo": v["arquivo"], "partes": v["partes"], "padrao": False}
                                     for v in arq["variantes"]]})
    # quantizações que o radar já guardou do HF e que a busca não devolveu
    conhecidos = {v["pull"].lower() for f in fontes for v in f["variantes"]}
    soltas = [v for v in c["variantes"] if v["pull"].lower() not in conhecidos]
    if soltas:
        fontes.append({"id": "radar", "tipo": "hf", "nome": "Outras (já no radar)", "url": None, "confianca": "?", "baixas": None,
                       "variantes": [{"quant": v["quant"], "bytes": v["bytes"], "extra_bytes": int(v.get("extra_bytes", 0)), "pull": v["pull"], "tag": v["tag"], "padrao": False} for v in soltas]})
    return {"candidato": {"id": c["id"], "nome": c["nome"], "params_b": c["params_b"], "ativos_b": c.get("ativos_b"), "moe": bool(c.get("moe")),
                          "caps": c.get("caps", []), "ctx_max": c.get("ctx_max"), "arch": arch_compacta(c.get("arch") or {}),
                          "papeis": c.get("papeis", []), "licenca": c.get("licenca"), "descricao": c.get("descricao", "")},
            "links": _links(c, repos), "fontes": fontes, "aviso": aviso}
