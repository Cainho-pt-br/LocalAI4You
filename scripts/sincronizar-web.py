"""Mantém o site igual ao painel local.

A interface tem UMA fonte: download/LocalIntelligence/web. O site (site/web) é uma cópia dela mais os arquivos que só
existem no modo público (public-mode.js). As diferenças de comportamento ficam no próprio código, atrás de
`window.LI_PUBLIC_MODE`.

    python scripts/sincronizar-web.py              # copia a fonte para site/web
    python scripts/sincronizar-web.py --verificar  # só confere (usado no CI); sai com erro se divergir
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTE = ROOT / "download" / "LocalIntelligence" / "web"
DESTINO = ROOT / "site" / "web"
SO_NO_SITE = {"public-mode.js"}


def divergencias() -> list[str]:
    fonte = {p.name for p in FONTE.iterdir() if p.is_file()}
    destino = {p.name for p in DESTINO.iterdir() if p.is_file()} - SO_NO_SITE
    out = [f"falta no site: {n}" for n in sorted(fonte - destino)]
    out += [f"sobrando no site (apague ou mova para a fonte): {n}" for n in sorted(destino - fonte)]
    out += [f"diferente: {n}" for n in sorted(fonte & destino) if (FONTE / n).read_bytes() != (DESTINO / n).read_bytes()]
    return out


def main() -> None:
    if "--verificar" in sys.argv:
        d = divergencias()
        if d:
            print("site/web diverge de download/LocalIntelligence/web:\n  " + "\n  ".join(d))
            print("Edite em download/LocalIntelligence/web e rode: python scripts/sincronizar-web.py")
            raise SystemExit(1)
        print("site/web está sincronizado.")
        return
    for p in FONTE.iterdir():
        if p.is_file():
            shutil.copy2(p, DESTINO / p.name)
    for p in DESTINO.iterdir():
        if p.is_file() and p.name not in SO_NO_SITE and not (FONTE / p.name).exists():
            p.unlink()
    print(f"site/web sincronizado a partir de {FONTE.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
