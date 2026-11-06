"""Caminhos e configuração. Tudo que muda por máquina fica em estado/ (fora do git)."""
from __future__ import annotations

import os
from pathlib import Path

from .util import gravar_json, ler_json

RAIZ = Path(__file__).resolve().parent.parent


def _pasta_gravavel() -> Path:
    """Onde ficam estado/ e relatorios/. Normalmente ao lado do app; se a pasta do app for só leitura (app da Microsoft
    Store, instalado em WindowsApps) ou LI_DADOS estiver definida, numa pasta do usuário."""
    if os.environ.get("LI_DADOS"):
        return Path(os.environ["LI_DADOS"])
    if os.access(RAIZ, os.W_OK) and "WindowsApps" not in RAIZ.parts:
        return RAIZ
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "LocalAISearch"


GRAVAVEL = _pasta_gravavel()
ESTADO = GRAVAVEL / "estado"
DADOS = RAIZ / "data"
AMOSTRAS = DADOS / "amostras"
CACHE = ESTADO / "cache"
SNAPSHOTS = ESTADO / "snapshots"
RESULTADOS = ESTADO / "resultados.jsonl"
SONDAS = ESTADO / "sondas.json"
SQUAD = ESTADO / "squad.json"
VEREDITOS = ESTADO / "vereditos.json"
APOSENTADOS = ESTADO / "aposentados.json"
CONFIG_ARQ = ESTADO / "config.json"
PROGRESSO = ESTADO / "progresso.json"
PARQUE_ARQ = RAIZ / "parque" / "parque.json"
# Catálogo que acompanha o download (atualizado todo dia pelo GitHub Actions): o Radar funciona antes da primeira varredura.
CATALOGO_INICIAL = RAIZ / "data" / "radar-inicial.json.gz"
HARDWARE_ARQ = DADOS / "hardware.json"
WEB = RAIZ / "web"
RELATORIOS = GRAVAVEL / "relatorios"

PADRAO = {
    # Ollama: OLLAMA_HOST do sistema pode ser 0.0.0.0 (escuta) — para CONECTAR usamos loopback.
    "ollama_url": None,
    "painel_porta": 8765,
    # Painel acessível pelo tailnet (publicado com `tailscale serve`): nomes de host aceitos além de 127.0.0.1 e quem pode entrar.
    # Acesso por esses hosts exige o token (X-LI-Token) OU um login do Tailscale desta lista. Vazio = só loopback (padrão).
    "maquina_id": "",              # id desta máquina em parque/parque.json (o instalador grava; vazio = detectar pelo hostname)
    "hosts_painel": [],
    "logins_permitidos": [],
    # Contexto usado nos testes. 8192 evita truncar os schemas do BFCL (o protocolo v1 usava 2048
    # e cortava prompts em silêncio). Se o modelo não ficar 100% na GPU, cai para 4096 e depois 2048.
    "ctx_bench": 8192,
    "ctx_fallback": [4096, 2048],
    "kv_cache": "q8_0",            # o que o painel liga ao subir o Ollama (OLLAMA_KV_CACHE_TYPE)
    "reserva_vram_gb": 1.3,        # Windows/dwm/navegador usam VRAM da placa de vídeo
    "nivel_padrao": "padrao",      # rapido | padrao | profundo
    "radar_dias_novo": 45,         # "novo" = lançado há menos de N dias
    "ollama_externo": False,       # True = o Ollama é um serviço do sistema (Pi: ollama.service); o painel NUNCA sobe um segundo (ele ganhava a corrida no boot, ficava na cgroup de 300 MB e sem os modelos)
    "tps_minimo": 0,               # benchmark pula o modelo que gera abaixo disto (tok/s medidos); 0 = sem corte. Pi: 4. "Forçar" no painel ignora
    "params_max_b": 130,          # o radar ignora modelos acima disto (parâmetros totais); a calculadora precisa dos grandes p/ GPUs de 24–96 GB
    "radar_validade_h": 12,        # cache das consultas ao HF/Ollama
    "labs_observados": [
        "Qwen", "google", "openai", "mistralai", "deepseek-ai", "microsoft", "meta-llama",
        "LiquidAI", "nvidia", "ibm-granite", "zai-org", "moonshotai", "HuggingFaceTB",
        "CohereLabs", "allenai", "tencent", "baidu", "ServiceNow-AI", "stepfun-ai", "XiaomiMiMo",
        "openbmb", "LGAI-EXAONE", "Cactus-Compute", "apple", "tiiuae", "swiss-ai", "arcee-ai", "ByteDance-Seed", "inclusionAI", "internlm",
    ],
    "quantizadores_confiaveis": ["unsloth", "bartowski", "lmstudio-community", "ggml-org", "mradermacher"],
    "broker_url": "",
    "backup_modelos_dir": "",       # pasta do kit offline (ex.: D:\\kit-offline) — vazio = não configurado
}


REMOTAS = ESTADO / "maquinas_remotas.json"   # {id: {"url": "https://x.ts.net:10000", "token": "..."}} — segredos: fora do git
TOKEN_ARQ = ESTADO / "token_painel.txt"


def token_painel() -> str:
    """Segredo desta máquina para quem a controla pelo tailnet. Criado na primeira vez; `python cli.py token` mostra."""
    import secrets
    try:
        t = TOKEN_ARQ.read_text("utf-8").strip()
        if len(t) >= 24:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(32)
    TOKEN_ARQ.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_ARQ.write_text(t, encoding="utf-8")
    try:
        os.chmod(TOKEN_ARQ, 0o600)
    except OSError:
        pass
    return t


def ollama_url() -> str:
    cfg = carregar()
    if cfg.get("ollama_url"):
        return cfg["ollama_url"].rstrip("/")
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return "http://127.0.0.1:11434"
    if "://" not in host:
        host = "http://" + host
    host = host.replace("0.0.0.0", "127.0.0.1").replace("[::]", "127.0.0.1")
    if host.count(":") < 2:  # sem porta
        host += ":11434"
    return host.rstrip("/")


def carregar() -> dict:
    cfg = dict(PADRAO)
    user = ler_json(CONFIG_ARQ, {}) or {}
    cfg.update({k: v for k, v in user.items() if k in PADRAO})
    return cfg


def salvar(parcial: dict) -> dict:
    cfg = carregar()
    for k, v in parcial.items():
        if k not in PADRAO:
            continue
        if isinstance(PADRAO[k], int) and not isinstance(PADRAO[k], bool):
            v = int(v)
        elif isinstance(PADRAO[k], float):
            v = float(v)
        elif isinstance(PADRAO[k], list):
            v = list(v)
        cfg[k] = v
    gravar_json(CONFIG_ARQ, {k: cfg[k] for k in PADRAO if cfg[k] != PADRAO[k]})
    return cfg


def garantir_pastas() -> None:
    for p in (ESTADO, CACHE, SNAPSHOTS, AMOSTRAS, RELATORIOS):
        p.mkdir(parents=True, exist_ok=True)
