"""Atualiza o catálogo público a partir do mesmo radar usado pelo app local."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "download" / "LocalIntelligence"
sys.path.insert(0, str(APP))

from li import calc, scout  # noqa: E402


def main() -> None:
    snap = scout.varrer(forcar=True, ao_progredir=print, com_hf=True)
    falhas = {fonte: status for fonte, status in snap.get("fontes", {}).items() if status is not True}
    if falhas or not snap.get("candidatos"):
        raise SystemExit(f"Catálogo não atualizado; fontes com falha: {falhas or 'sem candidatos'}")

    dados = calc.dados(None, incluir_parque=False)
    if dados.get("vazio") or not dados.get("candidatos"):
        raise SystemExit("O radar não produziu um catálogo utilizável; mantendo o arquivo anterior.")
    dados.pop("maquinas", None)
    dados.pop("esta_maquina", None)
    dados["n_medidos"] = 0

    destino = ROOT / "site" / "dados.js"
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    for caractere, escape in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        texto = texto.replace(caractere, escape)
    temporario = destino.with_suffix(".js.tmp")
    temporario.write_text("window.LI_DADOS = " + texto + ";\n", encoding="utf-8")
    temporario.replace(destino)
    print(f"Catálogo atualizado: {len(dados['candidatos'])} candidatos; radar {dados['radar']}")

    # O mesmo snapshot vai no ZIP do app local: o Radar dele funciona antes da primeira varredura.
    inicial = scout.gravar_catalogo_inicial(snap)
    print(f"Catálogo inicial do app: {inicial.relative_to(ROOT)} ({inicial.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
