"""Hugging Face: lançamentos por laboratório, tendências, tamanhos reais de GGUF e config.json.

Só endpoints públicos de leitura. Tudo em cache; sem internet o radar devolve o último dado (com a idade).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import quote

from .. import config
from ..fit import quant_de_nome
from ..util import CacheDisco, http_json

API = "https://huggingface.co/api"
PIPELINES_TEXTO = {"text-generation", "image-text-to-text", "any-to-any", "conversational", "text2text-generation",
                   "video-text-to-text", "audio-text-to-text"}
# formatos/derivados que não são "o modelo" em si
_DERIVADOS = re.compile(
    r"(?i)(-gguf|-mlx|-awq|-gptq|-fp8|-nvfp4|-mxfp4|-int4|-int8|-bnb|-4bit|-8bit|-exl2|-exl3|-onnx|-eagle|-draft|"
    r"-assistant|dspark|-unquantized|-qat|w4a16|w8a8|w4a4|-ct$|-safetensors$|-lora|-adapter|-gguf-|-quantized|obliterat)")
_BASE = re.compile(r"(?i)(-base$|-base-|_base$|-pt$|-pretrain)")
_COMUNIDADE = re.compile(r"(?i)(abliterat|heretic|uncensor|unfiltered|merge|-rp-|roleplay|erp|-nsfw|jailbreak|dpo-v|sft-v)")


def _cache() -> CacheDisco:
    return CacheDisco(config.CACHE / "hf")


def _validade_s() -> float:
    return float(config.carregar().get("radar_validade_h", 12)) * 3600


def listar_por_autor(autor: str, limite: int = 25, forcar: bool = False) -> List[dict]:
    url = f"{API}/models?author={quote(autor)}&sort=createdAt&direction=-1&limit={limite}"
    return _cache().get(f"autor-{autor}-{limite}", _validade_s(), lambda: http_json(url, timeout=25), forcar=forcar)


def listar_por_autor_populares(autor: str, limite: int = 60, forcar: bool = False) -> List[dict]:
    """Os mais baixados do laboratório (não só os mais novos): é onde estão os modelos pequenos estabelecidos (LFM2.5-230M, Granite 4 350M…)."""
    url = f"{API}/models?author={quote(autor)}&sort=downloads&direction=-1&limit={limite}"
    return _cache().get(f"autor-pop-{autor}-{limite}", _validade_s(), lambda: http_json(url, timeout=25), forcar=forcar)


def listar_tendencia(limite: int = 60, so_gguf: bool = False, forcar: bool = False, pipeline: Optional[str] = None) -> List[dict]:
    """`pipeline`: só esse tipo (text-generation, image-text-to-text). Sem ele a lista mistura imagem/vídeo/áudio e quase não sobra texto."""
    extra = "&filter=gguf" if so_gguf else ""
    extra += f"&filter={pipeline}" if pipeline else ""
    url = f"{API}/models?sort=trendingScore&direction=-1&limit={limite}{extra}"
    return _cache().get(f"tendencia-{limite}-{so_gguf}-{pipeline or ''}", _validade_s(), lambda: http_json(url, timeout=40), forcar=forcar)


def listar_populares_recentes(limite: int = 40, forcar: bool = False) -> List[dict]:
    """Mais baixados da semana: pega o que a comunidade realmente adotou (não só o que está no hype)."""
    url = f"{API}/models?sort=downloads&direction=-1&limit={limite}&filter=text-generation"
    return _cache().get(f"baixados-{limite}", _validade_s(), lambda: http_json(url, timeout=25), forcar=forcar)


def detalhe(repo: str, forcar: bool = False) -> Optional[dict]:
    try:
        return _cache().get(f"detalhe-{repo}", _validade_s() * 2, lambda: http_json(f"{API}/models/{repo}", timeout=25),
                            forcar=forcar)
    except Exception:
        return None


def config_json(repo: str) -> Optional[dict]:
    try:
        return _cache().get(f"config-{repo}", 30 * 86400,
                            lambda: http_json(f"https://huggingface.co/{repo}/raw/main/config.json", timeout=25, tentativas=2))
    except Exception:
        return None


def arquivos_gguf(repo: str, forcar: bool = False) -> List[dict]:
    """[{quant, arquivo, bytes, partes}] somando shards; mmproj vai em `extra_bytes` do chamador."""
    def buscar():
        arvore = http_json(f"{API}/models/{repo}/tree/main", timeout=25)
        grupos: Dict[str, dict] = {}
        mmproj = 0
        for f in arvore:
            nome = f.get("path", "")
            if not nome.endswith(".gguf"):
                continue
            tam = int((f.get("lfs") or {}).get("size") or f.get("size") or 0)
            if "mmproj" in nome.lower():
                mmproj = max(mmproj, tam) if "bf16" in nome.lower() or not mmproj else mmproj
                continue
            if "imatrix" in nome.lower():
                continue
            chave = re.sub(r"-\d{5}-of-\d{5}", "", nome)
            g = grupos.setdefault(chave, {"arquivo": chave, "bytes": 0, "partes": 0, "primeiro": nome})
            g["bytes"] += tam
            g["partes"] += 1
        out = []
        for g in grupos.values():
            q = quant_de_nome(g["arquivo"])
            if q and g["bytes"] > 0:
                out.append({"quant": q, "arquivo": g["arquivo"], "bytes": g["bytes"], "partes": g["partes"]})
        out.sort(key=lambda x: x["bytes"])
        return {"variantes": out, "mmproj_bytes": mmproj}
    try:
        return _cache().get(f"gguf-{repo}", _validade_s() * 2, buscar, forcar=forcar)
    except Exception:
        return {"variantes": [], "mmproj_bytes": 0}


def repos_gguf_do_base(repo: str, limite: int = 25) -> List[dict]:
    url = f"{API}/models?filter={quote('base_model:quantized:' + repo, safe=':/')}&sort=downloads&direction=-1&limit={limite}"
    try:
        return _cache().get(f"quantizados-{repo}", _validade_s() * 2, lambda: http_json(url, timeout=25))
    except Exception:
        return []


def melhor_repo_gguf(repo: str) -> Optional[dict]:
    """O GGUF de quantizador confiável (ou do próprio laboratório) mais baixado para esse modelo base."""
    cfg = config.carregar()
    confiaveis = [q.lower() for q in cfg.get("quantizadores_confiaveis", [])]
    autor_base = repo.split("/")[0].lower()
    achados = repos_gguf_do_base(repo)
    boas = []
    for it in achados:
        rid = it.get("id", "")
        autor = rid.split("/")[0].lower()
        if "gguf" not in rid.lower() and "gguf" not in " ".join(it.get("tags", [])).lower():
            continue
        if autor in confiaveis or autor == autor_base:
            boas.append(it)
    boas.sort(key=lambda it: (-(1 if it["id"].split("/")[0].lower() == "unsloth" else 0) * 0, -int(it.get("downloads", 0))))
    return boas[0] if boas else None


# ------------------------------------------------------------------ classificação do que veio da lista

def eh_derivado(nome: str) -> bool:
    return bool(_DERIVADOS.search(nome))


def eh_base_sem_instrucao(nome: str) -> bool:
    return bool(_BASE.search(nome))


def eh_comunidade(nome: str) -> bool:
    return bool(_COMUNIDADE.search(nome))


def parametros_b(det: Optional[dict], nome: str) -> Optional[float]:
    if det:
        st = (det.get("safetensors") or {}).get("total")
        if st:
            return round(st / 1e9, 2)
        gg = (det.get("gguf") or {}).get("total")
        if gg:
            return round(gg / 1e9, 2)
    m = re.search(r"(?i)(?<![a-z0-9.])(\d+(?:\.\d+)?)b(?![a-z])", nome)
    return float(m.group(1)) if m else None


def licenca(det: Optional[dict]) -> Optional[str]:
    if not det:
        return None
    for t in det.get("tags", []):
        if t.startswith("license:"):
            return t.split(":", 1)[1]
    return (det.get("cardData") or {}).get("license")


def buscar_base(nome_ollama: str, tamanho: str, chave_fn, tam_fn, labs: List[str]) -> Optional[dict]:
    """Acha o repositório-base no HF de uma família do Ollama (ex.: 'qwen3.6' + '27b' → Qwen/Qwen3.6-27B).

    Serve para ter a data real de lançamento, a licença e o config.json (cálculo exato do KV cache).
    Só aceita repositórios de laboratório conhecido: variante comunitária nunca vira "o modelo".
    """
    alvo = tamanho.split("-")[0]
    termos = [f"{nome_ollama}-{alvo}"]
    com_hifen = re.sub(r"([a-z])(\d)", r"\1-\2", nome_ollama)  # gemma4 → gemma-4
    if com_hifen != nome_ollama:
        termos.append(f"{com_hifen}-{alvo}")
    achados = []
    for termo in termos:
        try:
            achados += _cache().get(f"busca-{termo}", _validade_s() * 4,
                                    lambda t=termo: http_json(f"{API}/models?search={quote(t)}&sort=downloads&direction=-1&limit=30", timeout=25))
        except Exception:
            continue
    chave = chave_fn(nome_ollama)
    labs_l = {l.lower() for l in labs}
    melhor = None
    for it in achados:
        rid = it.get("id", "")
        autor, _, nome = rid.partition("/")
        if autor.lower() not in labs_l and autor.lower() not in ("unsloth", "microsoft", "tiiuae", "allenai"):
            continue
        if eh_derivado(nome) or eh_base_sem_instrucao(nome) or eh_comunidade(nome):
            continue
        if chave_fn(nome) != chave:
            continue
        t = tam_fn(nome)
        if not t or t.split("-")[0] != alvo:
            continue
        if (it.get("pipeline_tag") or "") not in PIPELINES_TEXTO:
            continue
        # prefere o do laboratório dono da família (ex.: Qwen/Qwen3.6-27B) ao espelho de terceiros
        pont = it.get("downloads", 0) * (3 if autor.lower() != "unsloth" else 1)
        if melhor is None or pont > melhor[0]:
            melhor = (pont, it)
    return melhor[1] if melhor else None
