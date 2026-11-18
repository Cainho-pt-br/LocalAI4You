"""Uma versão do app por vez.

O painel escuta numa porta fixa (8765). Se uma versão ANTIGA ficou aberta (outra instalação, o ZIP antigo, um processo
esquecido), a versão nova não conseguia abrir a porta e mostrava a antiga sem avisar: logo antigo, dados antigos.

Ao abrir, olhamos quem está na porta:
  • ninguém                     → seguimos normalmente;
  • esta mesma versão           → só abrimos a janela dela (não sobe um segundo painel);
  • uma versão mais nova        → também só abrimos a janela dela (um atalho antigo não derruba a versão nova);
  • uma versão antiga/diferente → pedimos para ela fechar (/api/encerrar); se não fechar, no Windows encerramos o
                                  processo, mas só se a linha de comando dele for a do painel; se ainda assim a porta
                                  não liberar, usamos a próxima porta livre e avisamos na tela.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from typing import Any, Dict, Optional

TENTATIVAS_PORTA = 20


def porta_livre(porta: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":       # no Windows, SO_EXCLUSIVEADDRUSE evita "ganhar" uma porta que outro processo já escuta
            s.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
        else:                     # como o servidor (allow_reuse_address): uma porta recém-fechada em TIME_WAIT conta como livre
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", porta))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pedir(porta: int, caminho: str, corpo: Optional[dict] = None, timeout: float = 3.0) -> Optional[dict]:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=dados, method="POST" if dados is not None else "GET",
                                 headers={"Host": f"127.0.0.1:{porta}", "X-LI": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except Exception:
        return None


def quem_esta(porta: int) -> Optional[dict]:
    """O /api/saude de quem ocupa a porta, se for um painel do Local AI 4 You; None se não responder como um."""
    s = _pedir(porta, "/api/saude")
    return s if isinstance(s, dict) and "versao_painel" in s else None


def _chave(build: Optional[dict]) -> tuple:
    """Ordem das versões: pela data do pacote (AAAA-MM-DD), depois pelo commit. Sem VERSAO.txt (cópia de desenvolvimento
    ou versão muito antiga) = a mais velha possível."""
    b = build or {}
    return (str(b.get("data") or ""), str(b.get("commit") or ""))


def mesma_versao(a: Optional[dict], b: Optional[dict]) -> bool:
    a, b = a or {}, b or {}
    if a.get("impressao") and b.get("impressao"):
        return a["impressao"] == b["impressao"]
    return False


def mais_nova(outra: Optional[dict], minha: Optional[dict]) -> bool:
    return bool((outra or {}).get("data")) and _chave(outra) > _chave(minha)


def _esperar_porta(porta: int, segundos: float) -> bool:
    fim = time.time() + segundos
    while time.time() < fim:
        if porta_livre(porta):
            return True
        time.sleep(0.25)
    return porta_livre(porta)


def _pid_na_porta(porta: int) -> Optional[int]:
    if os.name != "nt":
        return None
    try:
        saida = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=8,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for linha in saida.splitlines():
        partes = linha.split()
        if len(partes) >= 5 and partes[1].endswith(f":{porta}") and partes[3].upper() in ("LISTENING", "ESCUTANDO"):
            try:
                return int(partes[4])
            except ValueError:
                continue
    return None


def _linha_de_comando(pid: int) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                              capture_output=True, text=True, timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def e_o_painel(linha: str) -> bool:
    """Só encerramos à força um processo que seja claramente este painel (python … cli … painel)."""
    l = linha.lower()
    return "python" in l and re.search(r"\bcli(\.py)?\b", l) is not None and " painel" in l


def _forcar_fechar(porta: int) -> bool:
    pid = _pid_na_porta(porta)
    if not pid or pid == os.getpid() or not e_o_painel(_linha_de_comando(pid)):
        return False
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return _esperar_porta(porta, 4)


def _resumo(saude: Optional[dict]) -> Dict[str, Any]:
    if not saude:
        return {"versao": None}
    b = saude.get("build") or {}
    return {"versao": saude.get("versao_painel"), "commit": b.get("commit"), "data": b.get("data"), "loja": b.get("loja"), "pasta": saude.get("pasta_app")}


def preparar(porta: int, meu_build: Optional[dict]) -> Dict[str, Any]:
    """Decide em que porta este painel vai rodar. Devolve {"acao", "porta", "outra"}:
    livre | mesma | mais_nova (não sobe servidor: só abre a janela) | substituida | outra_porta."""
    if porta_livre(porta):
        return {"acao": "livre", "porta": porta}
    s = quem_esta(porta)
    if s and mesma_versao((s.get("build") or {}), meu_build):
        return {"acao": "mesma", "porta": porta, "outra": _resumo(s)}
    if s and mais_nova(s.get("build"), meu_build):
        return {"acao": "mais_nova", "porta": porta, "outra": _resumo(s)}
    if s:
        _pedir(porta, "/api/encerrar", {})
        if _esperar_porta(porta, 6):
            return {"acao": "substituida", "porta": porta, "outra": _resumo(s)}
    if _forcar_fechar(porta):
        return {"acao": "substituida", "porta": porta, "outra": _resumo(s)}
    for p in range(porta + 1, porta + 1 + TENTATIVAS_PORTA):
        if porta_livre(p):
            return {"acao": "outra_porta", "porta": p, "porta_ocupada": porta, "outra": _resumo(s)}
    return {"acao": "sem_porta", "porta": porta, "outra": _resumo(s)}
