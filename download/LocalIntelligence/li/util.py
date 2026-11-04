"""Utilitários: HTTP com cache em disco, JSON atômico, formatação, paralelismo."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

UA = "LocalIntelligence/3.0 (+uso pessoal; leitura somente)"

try:  # console do Windows em cp1252 quebra com acentos/emoji
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def dias_desde(s: Optional[str]) -> Optional[float]:
    d = parse_iso(s)
    if not d:
        return None
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400.0


# ---------------------------------------------------------------- arquivos

def ler_json(path: Path, padrao: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text("utf-8-sig"))
    except FileNotFoundError:
        return padrao
    except Exception:
        return padrao


def gravar_json(path: Path, dados: Any, indent: int = 2) -> None:
    """Escrita atômica: nunca deixa um JSON pela metade (o painel lê a qualquer hora)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=indent)
        for tentativa in range(12):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: leitor com o arquivo aberto
                if tentativa == 11:
                    raise
                time.sleep(0.15)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


_lock_jsonl = threading.Lock()


def anexar_jsonl(path: Path, linha: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_jsonl, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def ler_jsonl(path: Path) -> List[dict]:
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue  # linha truncada por queda de energia: ignora
    except FileNotFoundError:
        pass
    return out


def sha256_texto(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_arquivo(path: Path, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bloco)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- HTTP

class ErroHTTP(Exception):
    pass


def http_bytes(url: str, timeout: float = 25, headers: Optional[dict] = None, tentativas: int = 3) -> bytes:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    ultimo: Optional[Exception] = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 400, 401, 403):  # não adianta repetir
                raise ErroHTTP(f"HTTP {e.code} em {url}") from e
            ultimo = e
            if e.code == 429:  # limite de taxa: espera de verdade antes de tentar de novo
                time.sleep(4 * (i + 1))
        except Exception as e:  # timeout, DNS, reset
            ultimo = e
        time.sleep(0.6 * (i + 1))
    raise ErroHTTP(f"falha ao buscar {url}: {ultimo}")


def http_json(url: str, **kw) -> Any:
    return json.loads(http_bytes(url, **kw).decode("utf-8"))


def http_texto(url: str, **kw) -> str:
    return http_bytes(url, **kw).decode("utf-8", "replace")


class CacheDisco:
    """Cache simples (chave → JSON) com validade, para não martelar HF/Ollama.

    `obsoleto_ok=True` devolve o dado vencido se a rede falhar — é o que deixa o
    radar funcionar sem internet, com a ressalva de mostrar a idade do dado.
    """

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)

    def _arq(self, chave: str) -> Path:
        return self.pasta / (re.sub(r"[^A-Za-z0-9._-]+", "_", chave)[:80] + "-" + sha256_texto(chave)[:10] + ".json")

    def get(self, chave: str, validade_s: float, buscar: Callable[[], Any], obsoleto_ok: bool = True, forcar: bool = False):
        arq = self._arq(chave)
        dado = ler_json(arq)
        if dado and not forcar and time.time() - dado.get("_t", 0) < validade_s:
            return dado["v"]
        try:
            v = buscar()
            gravar_json(arq, {"_t": time.time(), "chave": chave, "v": v}, indent=0)
            return v
        except Exception:
            if dado and obsoleto_ok:
                return dado["v"]
            raise

    def idade_s(self, chave: str) -> Optional[float]:
        d = ler_json(self._arq(chave))
        return (time.time() - d.get("_t", 0)) if d else None


ERROS_PARALELO: list = []  # últimas exceções engolidas por mapa_paralelo (o radar mostra a contagem)


def mapa_paralelo(fn: Callable, itens: Iterable, workers: int = 6) -> list:
    """map com threads; exceções viram None, mas ficam registradas em ERROS_PARALELO (nunca somem em silêncio)."""
    def seguro(x):
        try:
            return fn(x)
        except Exception as e:
            ERROS_PARALELO.append(f"{getattr(fn, '__name__', 'fn')}: {type(e).__name__}: {e}"[:300])
            del ERROS_PARALELO[:-50]
            return None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(seguro, list(itens)))


# ---------------------------------------------------------------- formatação

GB = 1_000_000_000
GIB = 1024 ** 3


def gb(b: float, casas: int = 1) -> float:
    return round(b / GB, casas)


def fmt_gb(b: float) -> str:
    return f"{b / GB:.1f} GB".replace(".", ",")


def fmt_num(n: float, casas: int = 0) -> str:
    s = f"{n:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_contagem(s: Optional[str]) -> int:
    """'10.4K' → 10400, '120M' → 120_000_000, '8,625' → 8625."""
    if not s:
        return 0
    s = s.strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([KMB]?)$", s, re.I)
    if not m:
        return 0
    n = float(m.group(1))
    mult = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()]
    return int(n * mult)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class Progresso:
    """Estado de progresso pequeno e legível pelo painel (substitui o state.json de 700 KB)."""

    def __init__(self, arquivo: Path):
        self.arquivo = Path(arquivo)
        self.d: dict = {}
        self._l = threading.Lock()

    def set(self, **kw) -> None:
        with self._l:
            self.d.update(kw)
            self.d["atualizado"] = agora_iso()
            try:
                gravar_json(self.arquivo, self.d, indent=0)
            except Exception:
                pass

SEM_JANELA = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW: o painel roda sem console (pythonw); sem isto cada nvidia-smi pisca uma janela preta
