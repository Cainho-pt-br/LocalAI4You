"""Cliente mínimo do Ollama (somente stdlib) + utilitários do repositório local de modelos."""
from __future__ import annotations

import http.client
import json
import os
import socket
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import config
from .util import SEM_JANELA, UA


class ErroOllama(Exception):
    pass


class Cancelado(ErroOllama):
    """O usuário cancelou a tarefa enquanto uma requisição estava em andamento (a conexão foi derrubada)."""


def _exe() -> Optional[str]:
    exe = shutil.which("ollama")
    if exe:
        return exe
    for c in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"),
    ):
        if c.exists():
            return str(c)
    return None


class Ollama:
    def __init__(self, url: Optional[str] = None):
        self.url = (url or config.ollama_url()).rstrip("/")
        self.cancelar: Optional[threading.Event] = None   # se definido, o chat() é derrubado na hora quando o evento dispara

    # ---------------------------------------------------------- baixo nível
    def _req(self, caminho: str, payload: Optional[dict] = None, timeout: float = 600, metodo: Optional[str] = None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url + caminho, data=data, method=metodo,
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        return urllib.request.urlopen(req, timeout=timeout)

    def _json(self, caminho: str, payload: Optional[dict] = None, timeout: float = 600, metodo: Optional[str] = None) -> Any:
        try:
            with self._req(caminho, payload, timeout, metodo) as r:
                corpo = r.read().decode("utf-8")
                return json.loads(corpo) if corpo.strip() else {}
        except urllib.error.HTTPError as e:
            detalhe = ""
            try:
                detalhe = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                pass
            raise ErroOllama(f"HTTP {e.code} em {caminho}: {detalhe}".strip()) from e
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise ErroOllama(f"Ollama inacessível em {self.url}: {e}") from e

    def _json_interrompivel(self, caminho: str, payload: dict, timeout: float) -> Any:
        """POST que pode ser abortado: a requisição roda numa thread e, se `self.cancelar` disparar, o socket é fechado
        (o Ollama aborta a leitura do prompt/geração quando o cliente desconecta). Sem isso um prompt de 8k na CPU
        continuava por minutos depois do 'cancelar'."""
        u = urllib.parse.urlsplit(self.url)
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        saida: Dict[str, Any] = {}

        def corre():
            try:
                conn.request("POST", caminho, corpo, {"Content-Type": "application/json", "User-Agent": UA})
                r = conn.getresponse()
                saida["status"], saida["dados"] = r.status, r.read()
            except Exception as e:  # repassado abaixo
                saida["erro"] = e

        t = threading.Thread(target=corre, daemon=True)
        t.start()
        while t.is_alive():
            t.join(0.4)
            if self.cancelar is not None and self.cancelar.is_set():
                try:
                    if conn.sock:
                        conn.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
                raise Cancelado("cancelado pelo usuário")
        conn.close()
        if "erro" in saida:
            raise ErroOllama(f"Ollama inacessível em {self.url}: {saida['erro']}") from saida["erro"]
        if saida["status"] >= 400:
            detalhe = ""
            try:
                detalhe = json.loads(saida["dados"].decode("utf-8")).get("error", "")
            except Exception:
                pass
            raise ErroOllama(f"HTTP {saida['status']} em {caminho}: {detalhe}".strip())
        txt = saida["dados"].decode("utf-8")
        return json.loads(txt) if txt.strip() else {}

    # ---------------------------------------------------------- servidor
    def no_ar(self, timeout: float = 2.0) -> bool:
        try:
            self._json("/api/version", timeout=timeout)
            return True
        except ErroOllama:
            return False

    def versao(self) -> Optional[str]:
        try:
            return self._json("/api/version", timeout=3).get("version")
        except ErroOllama:
            return None

    def iniciar_servidor(self, esperar_s: float = 25, kv_tipo: Optional[str] = None) -> bool:
        """Sobe `ollama serve` com flash attention e KV cache quantizado (como o painel antigo fazia)."""
        if self.no_ar():
            return True
        if config.carregar().get("ollama_externo"):   # o serviço do sistema sobe sozinho: só espera
            t0 = time.time()
            while time.time() - t0 < esperar_s:
                if self.no_ar(timeout=0.6):
                    return True
                time.sleep(1)
            return False
        exe = _exe()
        if not exe:
            raise ErroOllama("Executável do Ollama não encontrado (instale em https://ollama.com).")
        env = dict(os.environ)
        # O servidor que ESTE painel sobe escuta só em loopback, mesmo que o ambiente diga 0.0.0.0 (Ollama sem login exposto na rede).
        porta = self.url.rsplit(":", 1)[-1]
        env["OLLAMA_HOST"] = f"127.0.0.1:{porta if porta.isdigit() else 11434}"
        env["OLLAMA_FLASH_ATTENTION"] = "1"
        env["OLLAMA_KV_CACHE_TYPE"] = kv_tipo or config.carregar().get("kv_cache", "q8_0")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([exe, "serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, creationflags=flags)
        t0 = time.time()
        while time.time() - t0 < esperar_s:
            if self.no_ar():
                return True
            time.sleep(0.5)
        return False

    def reiniciar_com_kv(self, kv_tipo: str, esperar_s: float = 25) -> bool:
        """Reinicia o processo local `ollama serve` aplicando `OLLAMA_KV_CACHE_TYPE=kv_tipo`."""
        if kv_tipo not in ("f16", "q8_0", "q4_0"):
            raise ErroOllama(f"Tipo de KV cache inválido: {kv_tipo}")
        config.salvar({"kv_cache": kv_tipo})
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA)
        else:
            subprocess.run(["pkill", "-f", "ollama serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while time.time() - t0 < 8:
            if not self.no_ar(timeout=0.6):
                break
            time.sleep(0.3)
        return self.iniciar_servidor(esperar_s=esperar_s, kv_tipo=kv_tipo)

    # ---------------------------------------------------------- consultas
    def tags(self) -> List[dict]:
        return self._json("/api/tags", timeout=15).get("models", [])

    def ps(self) -> List[dict]:
        return self._json("/api/ps", timeout=15).get("models", [])

    def show(self, modelo: str) -> dict:
        return self._json("/api/show", {"model": modelo}, timeout=30)

    def descarregar(self, modelo: str) -> None:
        try:
            self._json("/api/chat", {"model": modelo, "messages": [], "keep_alive": 0, "stream": False}, timeout=60)
        except ErroOllama:
            pass

    def chat(self, modelo: str, mensagens: List[dict], *, ctx: int = 8192, temperatura: float = 0.0,
             max_tokens: int = 512, think: Any = False, tools: Optional[list] = None,
             keep_alive: str = "10m", timeout: float = 900, num_gpu: Optional[int] = 99,
             formato: Any = None) -> dict:
        opcoes = {"num_ctx": ctx, "temperature": temperatura, "num_predict": max_tokens}
        if num_gpu is not None:
            opcoes["num_gpu"] = num_gpu
        payload = {"model": modelo, "messages": mensagens, "stream": False, "think": think,
                   "keep_alive": keep_alive, "options": opcoes}
        if tools:
            payload["tools"] = tools
        if formato:
            payload["format"] = formato
        if self.cancelar is not None:
            return self._json_interrompivel("/api/chat", payload, timeout)
        return self._json("/api/chat", payload, timeout=timeout)

    def remover(self, modelo: str) -> None:
        self._json("/api/delete", {"model": modelo}, timeout=60, metodo="DELETE")

    def criar_variante_ctx(self, base: str, alias: str, num_ctx: int) -> dict:
        """Cria um perfil/alias no Ollama com `num_ctx` fixo (evita que o usuário precise criar Modelfile na mão)."""
        ctx = max(1024, int(num_ctx))
        try:
            self._json("/api/create", {"model": alias, "from": base, "parameters": {"num_ctx": ctx}, "stream": False}, timeout=120)
        except ErroOllama:
            self._json("/api/create", {"model": alias, "modelfile": f"FROM {base}\nPARAMETER num_ctx {ctx}\n", "stream": False}, timeout=120)
        return {"ok": True, "base": base, "modelo": alias, "alias": alias, "ctx": ctx, "num_ctx": ctx}

    # ---------------------------------------------------------- download
    def baixar(self, modelo: str, ao_progredir: Optional[Callable[[dict], None]] = None,
               cancelar: Optional[threading.Event] = None, total_esperado: int = 0) -> None:
        """`ollama pull` via API, com progresso agregado de todas as camadas.

        As camadas aparecem uma a uma, então o total cresce durante o download: passando `total_esperado`
        (tamanho exato do registry) a barra sobe sem recuar; sem ele, ao menos nunca anda para trás.
        """
        camadas: Dict[str, Tuple[int, int]] = {}
        t0 = time.time()
        ultimo = 0.0
        try:
            with self._req("/api/pull", {"model": modelo, "stream": True}, timeout=7200) as r:
                for linha in r:
                    if cancelar is not None and cancelar.is_set():
                        raise ErroOllama("download cancelado")
                    linha = linha.strip()
                    if not linha:
                        continue
                    d = json.loads(linha.decode("utf-8"))
                    if d.get("error"):
                        raise ErroOllama(d["error"])
                    dg = d.get("digest")
                    if dg and d.get("total"):
                        camadas[dg] = (int(d.get("completed", 0)), int(d["total"]))
                    tot = max(sum(t for _, t in camadas.values()), total_esperado)
                    ok = sum(c for c, _ in camadas.values())
                    if ao_progredir:
                        dt = max(time.time() - t0, 0.001)
                        ultimo = max(ultimo, round(100 * ok / tot, 1) if tot else 0.0)
                        ao_progredir({
                            "status": d.get("status", ""), "completo": ok, "total": tot,
                            "pct": ultimo if d.get("status") != "success" else 100.0,
                            "mb_s": round(ok / dt / 1e6, 1),
                        })
                    if d.get("status") == "success":
                        return
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise ErroOllama(f"falha no download de {modelo}: {e}") from e

    # ---------------------------------------------------------- derivados
    def instalados(self) -> List[dict]:
        """Modelos instalados já com capacidades e arquitetura (via /api/show)."""
        out = []
        for m in self.tags():
            nome = m.get("name") or m.get("model")
            item = {
                "id": nome, "bytes": int(m.get("size", 0)), "digest": m.get("digest", ""),
                "modificado": m.get("modified_at"),
                "familia": (m.get("details") or {}).get("family"),
                "params": (m.get("details") or {}).get("parameter_size"),
                "quant": (m.get("details") or {}).get("quantization_level"),
                "caps": [], "arch": {},
            }
            try:
                s = self.show(nome)
                item["caps"] = s.get("capabilities") or []
                item["arch"] = extrair_arch(s.get("model_info") or {})
                item["ctx_max"] = item["arch"].get("ctx_max")
            except ErroOllama:
                pass
            out.append(item)
        return out


def extrair_arch(info: dict) -> dict:
    """Extrai de `model_info` o que o cálculo de KV cache precisa (chaves variam por arquitetura)."""
    arq = info.get("general.architecture", "")

    def g(sufixo, padrao=None):
        v = info.get(f"{arq}.{sufixo}")
        return padrao if v is None else v

    camadas = g("block_count")
    kv_heads = g("attention.head_count_kv")
    if isinstance(kv_heads, list):  # alguns modelos listam por camada
        kv_heads = max(kv_heads) if kv_heads else None
    heads = g("attention.head_count")
    emb = g("embedding_length")
    key_len = g("attention.key_length") or (emb // heads if emb and heads else None)
    val_len = g("attention.value_length") or key_len
    intervalo = g("full_attention_interval")
    janela = g("attention.sliding_window")
    return {
        "arquitetura": arq, "camadas": camadas, "kv_heads": kv_heads, "key_len": key_len, "val_len": val_len,
        "intervalo_atencao_cheia": intervalo, "janela": janela, "ctx_max": g("context_length"),
        "params": info.get("general.parameter_count"),
        "moe": bool(g("expert_count")), "experts": g("expert_count"), "experts_usados": g("expert_used_count"),
    }


# ------------------------------------------------------------------ repositório local

def pasta_modelos() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        return Path(env)
    return Path.home() / ".ollama" / "models"


def caminho_manifest(modelo: str, base: Optional[Path] = None) -> Path:
    """'qwen3.5:9b' → manifests/registry.ollama.ai/library/qwen3.5/9b ; 'hf.co/a/b:Q4' → manifests/hf.co/a/b/Q4."""
    base = base or pasta_modelos()
    nome, _, tag = modelo.partition(":")
    tag = tag or "latest"
    partes = nome.split("/")
    if len(partes) > 1 and (partes[0] in ("hf.co", "huggingface.co") or "." in partes[0]):
        reg, resto = partes[0], partes[1:]  # só é registro quando há namespace depois ("qwen3.5" sozinho não é)
    else:
        reg = "registry.ollama.ai"
        resto = (["library"] + partes) if len(partes) == 1 else partes
    return base / "manifests" / reg / Path(*resto) / tag


def ler_manifest(modelo: str, base: Optional[Path] = None) -> Optional[dict]:
    p = caminho_manifest(modelo, base)
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def blobs_do_modelo(modelo: str, base: Optional[Path] = None) -> List[dict]:
    """[{digest, size, path, existe, tamanho_ok}] — base do verificador e do export offline."""
    base = base or pasta_modelos()
    m = ler_manifest(modelo, base)
    if not m:
        return []
    out = []
    camadas = list(m.get("layers", []))
    if m.get("config"):
        camadas.append(m["config"])
    for c in camadas:
        dg = c.get("digest", "")
        p = base / "blobs" / dg.replace(":", "-")
        existe = p.exists()
        out.append({
            "digest": dg, "size": int(c.get("size", 0)), "path": str(p), "existe": existe,
            "tamanho_ok": existe and p.stat().st_size == int(c.get("size", 0)),
            "tipo": (c.get("mediaType") or "").split(".")[-1],
        })
    return out
