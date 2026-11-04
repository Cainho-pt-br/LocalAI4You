"""Biblioteca oficial do Ollama (ollama.com/library) + registry (tamanho exato por tag).

Não existe API JSON pública para listar a biblioteca, então lemos o HTML. Se o layout mudar, o
parser devolve lista vazia e o painel avisa "fonte Ollama indisponível" — o resto continua.
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import List, Optional

from .. import config
from ..util import CacheDisco, ErroHTTP, http_json, http_texto, parse_contagem

BASE = "https://ollama.com"
REGISTRY = "https://registry.ollama.ai/v2/library"
_MESES = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _cache() -> CacheDisco:
    return CacheDisco(config.CACHE / "ollama")


def _validade_s() -> float:
    return float(config.carregar().get("radar_validade_h", 12)) * 3600


def _data(txt: Optional[str]) -> Optional[str]:
    """'Sep 29, 2026 11:34 PM UTC' → ISO."""
    if not txt:
        return None
    m = re.match(r"([A-Z][a-z]{2}) (\d+), (\d{4})(?: (\d+):(\d+) (AM|PM))?", txt)
    if not m:
        return None
    mes, dia, ano = _MESES.get(m.group(1), 1), int(m.group(2)), int(m.group(3))
    h = mi = 0
    if m.group(4):
        h, mi = int(m.group(4)) % 12, int(m.group(5))
        if m.group(6) == "PM":
            h += 12
    return datetime(ano, mes, dia, h, mi, tzinfo=timezone.utc).isoformat(timespec="minutes")


def _parse_listagem(pagina: str) -> List[dict]:
    out = []
    for blk in pagina.split('<li  class="flex items-baseline')[1:]:
        nome = re.search(r'href="/library/([^"]+)"', blk)
        if not nome:
            continue
        desc = re.search(r'text-md">(.*?)</p>', blk, re.S)
        caps, tamanhos = [], []
        for cor, txt in re.findall(r'rounded-md bg-([^ ]+) [^>]*>\s*([^<\s][^<]*?)\s*</span>', blk):
            txt = txt.strip()
            if "indigo" in cor:
                caps.append(txt)          # tools / thinking / vision / embedding
            elif "cyan" in cor:
                caps.append(txt)          # cloud
            else:
                tamanhos.append(txt.lower())  # 7b, 70b, 335m, 8x7b
        pulls = re.search(r'<span >([\d,\.]+[KMB]?)</span>\s*<span class="hidden sm:flex">&nbsp;Pulls', blk)
        ntags = re.search(r'<span >(\d+)</span>\s*<span class="hidden sm:flex">&nbsp;Tags', blk)
        upd = re.search(r'title="([A-Z][a-z]{2} \d+, \d{4}[^"]*)"', blk)
        out.append({
            "nome": nome.group(1),
            "descricao": _html.unescape(desc.group(1).strip()) if desc else "",
            "caps": caps, "tamanhos": tamanhos,
            "pulls": parse_contagem(pulls.group(1)) if pulls else 0,
            "n_tags": int(ntags.group(1)) if ntags else None,
            "atualizado": _data(upd.group(1) if upd else None),
        })
    return out


def listar(ordem: str = "newest", forcar: bool = False) -> List[dict]:
    chave = f"biblioteca-{ordem}"
    return _cache().get(chave, _validade_s(), lambda: _parse_listagem(http_texto(f"{BASE}/library?sort={ordem}", timeout=30)),
                        forcar=forcar)


def _para_gb(v: str, un: str) -> int:
    return int(float(v) * (1e9 if un == "GB" else 1e6))


def _parse_tags(pagina: str, nome: str) -> List[dict]:
    out, vistos = [], set()
    for blk in pagina.split(f'<a href="/library/{nome}:')[1:]:
        tag = blk.split('"', 1)[0]
        if not tag or tag in vistos or len(tag) > 60:
            continue
        corpo = re.sub(r"<[^>]+>", " ", blk[:1600])
        corpo = re.sub(r"\s+", " ", _html.unescape(corpo))
        sz = re.search(r"([\d.]+)\s*(GB|MB)(?:\s*-\s*([\d.]+)\s*(GB|MB))?", corpo)
        if not sz:
            continue
        vistos.add(tag)
        ctx = re.search(r"(\d+)\s*([KM])\s*context window", corpo)
        ent = re.search(r"((?:Text|Image|Audio|Video)(?:, (?:Text|Image|Audio|Video))*) input", corpo)
        b1 = _para_gb(sz.group(1), sz.group(2))
        b2 = _para_gb(sz.group(3), sz.group(4)) if sz.group(3) else b1
        out.append({
            "tag": tag, "bytes": max(b1, b2), "bytes_min": min(b1, b2),
            "ctx": int(ctx.group(1)) * (1024 if ctx.group(2) == "K" else 1024 * 1024) if ctx else None,
            "entradas": [x.strip().lower() for x in ent.group(1).split(",")] if ent else ["text"],
            "digest": (re.search(r"\b([0-9a-f]{12})\b", corpo) or [None, None])[1],
        })
    return out


def tags(nome: str, forcar: bool = False) -> List[dict]:
    """Variantes de um modelo (tag, tamanho em bytes, contexto, entradas)."""
    return _cache().get(f"tags-{nome}", _validade_s() * 2,
                        lambda: _parse_tags(http_texto(f"{BASE}/library/{nome}/tags", timeout=30), nome), forcar=forcar)


def manifest(nome: str, tag: str) -> Optional[dict]:
    """Tamanho exato (soma das camadas) e metadados do GGUF (parâmetros e quantização), sem baixar nada."""
    def buscar():
        h = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
        m = http_json(f"{REGISTRY}/{nome}/manifests/{tag}", headers=h, timeout=20, tentativas=2)
        cfg = {}
        try:
            cfg = http_json(f"{REGISTRY}/{nome}/blobs/{m['config']['digest']}", timeout=20, tentativas=2)
        except Exception:
            pass
        camadas = {}
        for c in m.get("layers", []):
            tipo = c["mediaType"].split(".")[-1]
            camadas[tipo] = camadas.get(tipo, 0) + int(c["size"])
        return {"bytes_total": sum(camadas.values()), "camadas": camadas,
                "params": cfg.get("model_type"), "quant": cfg.get("file_type"), "familia": cfg.get("model_family")}
    try:
        return _cache().get(f"manifest-{nome}-{tag}", 7 * 86400, buscar)
    except (ErroHTTP, Exception):
        return None


def preflight(pull: str) -> dict:
    """Confere, SEM baixar, se `ollama pull <pull>` vai achar o modelo e quanto vai baixar de verdade.

    Biblioteca do Ollama e hf.co usam o mesmo protocolo de manifesto. Pega erro de nome de quantização (ex.: pedir
    `:IQ3_M` num repositório que só tem `UD-IQ3_S`) antes de gastar disco e tempo.
    Devolve {ok, bytes_total, bytes_projetor, camadas} ou {ok: False, erro}.
    """
    pull = pull.strip()
    try:
        if pull.startswith("hf.co/"):
            repo, _, tag = pull[len("hf.co/"):].partition(":")
            url = f"https://huggingface.co/v2/{repo}/manifests/{tag or 'latest'}"
        else:
            nome, _, tag = pull.partition(":")
            url = f"{REGISTRY}/{nome}/manifests/{tag or 'latest'}"
        m = http_json(url, headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"}, timeout=20, tentativas=2)
    except ErroHTTP as e:
        return {"ok": False, "erro": f"o registro não conhece '{pull}' ({e})"}
    except Exception as e:
        return {"ok": False, "erro": f"não consegui consultar o registro: {e}", "sem_rede": True}
    camadas: Dict[str, int] = {}
    for c in m.get("layers", []):
        tipo = c.get("mediaType", "").split(".")[-1]
        camadas[tipo] = camadas.get(tipo, 0) + int(c.get("size", 0))
    return {"ok": bool(camadas.get("model")), "bytes_total": sum(camadas.values()), "bytes_projetor": camadas.get("projector", 0),
            "bytes_modelo": camadas.get("model", 0), "camadas": camadas}


def parse_params_b(txt: Optional[str]) -> Optional[float]:
    """'9.7B' → 9.7 ; '335M' → 0.335 ; '8x7b' → 56."""
    if not txt:
        return None
    t = txt.strip().lower()
    m = re.match(r"^(\d+)x(\d+(?:\.\d+)?)b$", t)
    if m:
        return float(m.group(1)) * float(m.group(2))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([bm])$", t)
    if m:
        v = float(m.group(1))
        return v if m.group(2) == "b" else v / 1000
    return None
