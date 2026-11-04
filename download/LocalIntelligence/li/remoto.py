"""Controle das outras máquinas do parque a partir deste painel.

Cada máquina roda o PRÓPRIO painel (Python + Ollama locais, escutando só em 127.0.0.1) e o publica no tailnet com
`tailscale serve`. Este painel não fala com o Ollama dos outros: ele repassa a API inteira (`/api/m/<id>/...`) ao painel da
máquina — assim benchmark, sonda, download, aposentar, offline etc. funcionam do mesmo jeito lá e cá, cada um medindo o
SEU hardware. Nada é aberto na internet; o Ollama de ninguém escuta na rede.

Segurança:
  • só repassa para máquinas REGISTRADAS (`estado/maquinas_remotas.json`) cujo id existe em parque.json — o id da requisição
    nunca vira host (evita SSRF) — e só para URLs https `*.ts.net`;
  • o painel remoto só aceita o host do tailnet se o pedido trouxer o token da máquina (ou um login do Tailscale permitido).
"""
from __future__ import annotations

import hmac
import json
import re
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from . import config
from .util import UA, ler_json, gravar_json, mapa_paralelo

PORTA_TAILNET = 10000     # porta https do `tailscale serve` de cada painel (443 já é do broker no Pi)
_ID_OK = re.compile(r"[a-z0-9][a-z0-9\-]{0,40}")


# ------------------------------------------------------------------ lado que RECEBE (painel remoto)

def _sem_porta(host: str) -> str:
    return (host or "").rsplit(":", 1)[0] if re.search(r":\d+$", host or "") else (host or "")


def acesso(host: str, token: Optional[str], login: Optional[str], porta_local: int) -> str:
    """'local' (loopback), 'remoto' (host do tailnet autorizado) ou 'negado'."""
    if host in (f"127.0.0.1:{porta_local}", f"localhost:{porta_local}"):
        return "local"
    cfg = config.carregar()
    hosts = {h.lower() for h in cfg.get("hosts_painel", [])}
    if (host or "").lower() not in hosts and _sem_porta((host or "").lower()) not in hosts:
        return "negado"
    if token and hmac.compare_digest(token, config.token_painel()):
        return "remoto"
    if login and login.lower() in {l.lower() for l in cfg.get("logins_permitidos", [])}:
        return "remoto"
    return "negado"


# ------------------------------------------------------------------ lado que ENVIA (painel controlador)

def carregar() -> Dict[str, dict]:
    return ler_json(config.REMOTAS, {}) or {}


def _url_ok(url: str) -> bool:
    try:
        u = urlparse(url)
        return u.scheme == "https" and (u.hostname or "").endswith(".ts.net") and not u.username
    except Exception:
        return False


def ids_do_parque() -> set:
    return {m["id"] for m in (ler_json(config.PARQUE_ARQ, {"maquinas": []}) or {}).get("maquinas", [])}


def registrar(mid: str, token: str, url: Optional[str] = None) -> dict:
    if not _ID_OK.fullmatch(mid or "") or mid not in ids_do_parque():
        raise ValueError(f"Máquina desconhecida: {str(mid)[:40]!r} (não está em parque/parque.json).")
    if not token or len(token) < 24:
        raise ValueError("Token inválido (use o de `python cli.py token` na outra máquina).")
    url = (url or f"https://{mid}.example.ts.net:{PORTA_TAILNET}").rstrip("/")
    if not _url_ok(url):
        raise ValueError("URL inválida: precisa ser https e terminar em .ts.net.")
    reg = carregar()
    reg[mid] = {"url": url, "token": token}
    gravar_json(config.REMOTAS, reg)
    return {"id": mid, "url": url}


def remover(mid: str) -> None:
    reg = carregar()
    reg.pop(mid, None)
    gravar_json(config.REMOTAS, reg)


def _pedido(mid: str, metodo: str, caminho: str, corpo: Optional[bytes], timeout: float) -> Tuple[int, bytes, str]:
    reg = carregar().get(mid)
    if not reg or not _url_ok(reg.get("url", "")):
        raise ValueError(f"Máquina '{str(mid)[:40]}' não está registrada.")
    req = urllib.request.Request(reg["url"] + caminho, data=corpo, method=metodo,
                                 headers={"User-Agent": UA, "X-LI": "1", "X-LI-Token": reg["token"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "application/json")


def repassar(mid: str, metodo: str, resto: str, query: str, corpo: Optional[bytes]) -> Tuple[int, bytes, str]:
    """`resto` = o que vem depois de /api/m/<id>/ (ex.: 'mesa', 'jobs/abc'). Só rotas /api/ do painel remoto."""
    if not re.fullmatch(r"[A-Za-z0-9_\-./%:]{1,200}", resto) or ".." in resto:
        raise ValueError("Rota inválida.")
    try:
        return _pedido(mid, metodo, "/api/" + resto + (("?" + query) if query else ""), corpo, 180)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 502, json.dumps({"erro": f"A máquina '{mid}' não respondeu ({getattr(e, 'reason', e)}). Ela está ligada, com o painel rodando?"}).encode(), "application/json"


def sondar(mid: str) -> dict:
    try:
        st, corpo, _ = _pedido(mid, "GET", "/api/saude", None, 4)
        d = json.loads(corpo.decode("utf-8")) if st == 200 else {}
        return {"online": st == 200, "status": st, "ollama": (d.get("ollama") or {}), "gpu": d.get("gpu"), "protocolo": d.get("protocolo"),
                "erro": None if st == 200 else f"HTTP {st}"}
    except Exception as e:
        return {"online": False, "erro": str(getattr(e, "reason", e))[:120]}


def lista() -> list:
    reg = carregar()
    nomes = {m["id"]: m.get("nome", m["id"]) for m in (ler_json(config.PARQUE_ARQ, {"maquinas": []}) or {}).get("maquinas", [])}
    estados = mapa_paralelo(sondar, list(reg), workers=5)
    return [{"id": mid, "nome": nomes.get(mid, mid), "url": reg[mid]["url"], **(st or {"online": False})} for mid, st in zip(reg, estados)]
