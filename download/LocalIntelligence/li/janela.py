"""Abre o painel numa janela própria de aplicativo (sem abas nem barra de endereço), usando o Edge ou o Chrome que já
existem no computador (modo --app). Sem nenhum dos dois, quem chama volta ao navegador padrão. Não instala nada."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from . import config


def _navegadores() -> List[str]:
    achar: List[str] = []
    if sys.platform == "win32":
        for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                achar += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif sys.platform == "darwin":
        achar += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:
        achar += [shutil.which(n) or "" for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser")]
    return [p for p in achar if p and os.path.isfile(p)]


def disponivel() -> Optional[str]:
    if os.environ.get("LI_JANELA") == "0" or not config.carregar().get("janela_app", True):
        return None
    achados = _navegadores()
    return achados[0] if achados else None


def abrir(url: str, ao_fechar: Optional[Callable[[], None]] = None) -> bool:
    """Abre a janela do app. `ao_fechar` roda quando a janela é fechada (se o navegador ficou aberto por mais de alguns
    segundos: se ele só repassa o pedido a uma janela já existente e sai na hora, não encerramos nada)."""
    exe = disponivel()
    if not exe:
        return False
    perfil = Path(config.GRAVAVEL) / "janela"        # perfil só do app: janela separada, sem misturar com o navegador da pessoa
    try:
        perfil.mkdir(parents=True, exist_ok=True)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={perfil}", "--no-first-run", "--no-default-browser-check",
                                 "--window-size=1360,880"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError:
        return False
    inicio = time.time()

    def esperar():
        proc.wait()
        if ao_fechar and time.time() - inicio > 8:
            ao_fechar()
    threading.Thread(target=esperar, daemon=True).start()
    return True
