#!/usr/bin/env python3
"""Monta o que vai para o download, a partir de download/LocalIntelligence (a fonte do app).

    python empacotar/montar.py            # gera dist/zip/LocalAISearch (macOS/Linux) e dist/windows/LocalAISearch

No Windows o CI ainda põe em app/python o Python embutido oficial (python.org): os atalhos chamam esse pythonw.exe,
assinado pela Python Software Foundation, então não há executável desconhecido para o SmartScreen bloquear.

Quem baixa vê só o necessário: um atalho para abrir, um LEIA-ME e a pasta app/. Ficam de fora os testes, os .bat de
desenvolvimento, o .gitignore e qualquer estado local (estado/, relatorios/, __pycache__)."""
import shutil
import stat
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FONTE = RAIZ / "download" / "LocalIntelligence"
AQUI = Path(__file__).resolve().parent
DIST = RAIZ / "dist"
FORA = {"tests", "estado", "relatorios", "__pycache__", ".gitignore", ".pytest_cache"}


def _ignorar(pasta, nomes):
    ig = {n for n in nomes if n in FORA or n.endswith((".pyc", ".bat", ".ps1"))}   # .bat/.ps1: atalhos de desenvolvimento
    if Path(pasta) == FONTE:
        ig |= {"README.md"}          # o README de quem baixa é o LEIA-ME.txt
    return ig


def _versao() -> str:
    """Commit e data do download, para o app saber se há versão nova (compara com o release app-latest)."""
    import datetime
    import os
    import subprocess
    commit = (os.environ.get("GITHUB_SHA") or "")[:7]
    if not commit:
        try:
            commit = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
        except OSError:
            commit = ""
    return f"{commit or 'dev'} {datetime.date.today().isoformat()} {_impressao()}\n"


def _impressao() -> str:
    """Impressão digital só do PROGRAMA (li/, web/, cli.py): muda quando o app muda, não quando só o catálogo diário muda."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted([FONTE / "cli.py", *(FONTE / "li").rglob("*.py"), *(FONTE / "web").rglob("*")]):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(FONTE).as_posix().encode()); h.update(p.read_bytes())
    return h.hexdigest()[:10]


def _app(destino: Path) -> None:
    shutil.copytree(FONTE, destino / "app", ignore=_ignorar)
    (destino / "app" / "VERSAO.txt").write_text(_versao(), encoding="utf-8")


def _executavel(p: Path) -> None:
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def montar() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    z = DIST / "zip" / "LocalAISearch"
    z.mkdir(parents=True)
    _app(z)
    shutil.copy(AQUI / "LEIA-ME.txt", z / "LEIA-ME.txt")
    for nome, alvo in (("Abrir Local AI 4 You (Mac).command", "abrir-mac.command"), ("Abrir Local AI 4 You (Linux).sh", "abrir-linux.sh")):
        p = z / nome
        p.write_text('#!/bin/bash\ncd "$(dirname "$0")/app" || exit 1\nexec bash "./%s"\n' % alvo, newline="\n")
        _executavel(p)
    for n in ("abrir-mac.command", "abrir-linux.sh"):
        _executavel(z / "app" / n)
    w = DIST / "windows" / "LocalAISearch"
    w.mkdir(parents=True)
    _app(w)
    for n in ("abrir-mac.command", "abrir-linux.sh"):
        (w / "app" / n).unlink()
    shutil.copy(AQUI / "windows" / "desinstalar.bat", w / "app" / "desinstalar.bat")
    shutil.copy(AQUI / "windows" / "instalar.bat", w / "Instalar Local AI 4 You.bat")
    shutil.copy(AQUI / "LEIA-ME.txt", w / "LEIA-ME.txt")
    print("Pronto:", z, "e", w)


if __name__ == "__main__":
    montar()
