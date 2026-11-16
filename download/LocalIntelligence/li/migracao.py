"""Traz os resultados de uma instalação anterior para a pasta de dados atual.

Por quê: o app instalado pelo ZIP guarda os dados ao lado dele (…\\Programs\\Local AI 4 You\\app\\estado), e o da Microsoft
Store, numa pasta própria (%LOCALAPPDATA%\\LocalAISearch\\estado). Quem trocava de um para o outro "perdia" as notas medidas,
os vereditos e os modelos aposentados. Aqui, na primeira vez que a pasta atual está sem resultados, copiamos do lugar antigo
(sem apagar nada lá e sem sobrescrever nada aqui)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

from . import config
from .util import agora_iso

# o que vale levar: notas, velocidade/contexto medidos, vereditos, aposentados, histórico v1 e o último radar
ARQUIVOS = ("resultados.jsonl", "sondas.json", "squad.json", "vereditos.json", "aposentados.json", "historico_v1.json", "config.json")
MARCA = "migrado.json"


def _locais_antigos() -> List[Path]:
    """Onde instalações anteriores podem ter deixado a pasta estado/ (nomes de hoje e o antigo, "Local AI Search")."""
    achar: List[Path] = []
    extra = os.environ.get("LI_MIGRAR_DE")
    if extra:
        achar.append(Path(extra))
    base = os.environ.get("LOCALAPPDATA")
    if base:
        for nome in ("Local AI 4 You", "Local AI Search"):
            achar.append(Path(base) / "Programs" / nome / "app" / "estado")
        achar.append(Path(base) / "LocalAISearch" / "estado")
    achar.append(config.RAIZ / "estado")
    return achar


def _tem_dados(p: Path) -> bool:
    return p.is_dir() and any((p / a).exists() for a in ("resultados.jsonl", "vereditos.json", "aposentados.json", "squad.json"))


def _unir_linhas(origem: Path, destino: Path) -> int:
    """Junta dois arquivos de linhas (resultados.jsonl): as do destino ficam; as da origem que faltam entram antes."""
    velhas = [l for l in origem.read_text("utf-8", errors="replace").splitlines() if l.strip()]
    atuais = destino.read_text("utf-8", errors="replace").splitlines() if destino.exists() else []
    vistos = set(atuais)
    novas = [l for l in velhas if l not in vistos]
    if novas:
        destino.write_text("\n".join(novas + [l for l in atuais if l.strip()]) + "\n", "utf-8")
    return len(novas)


def importar_dados_antigos(origem: Optional[Path] = None, forcar: bool = False) -> Optional[dict]:
    """Copia os dados de uma instalação anterior, uma única vez. Devolve o resumo, ou None se não havia o que trazer."""
    destino = config.ESTADO
    marca = destino / MARCA
    if marca.exists() and not forcar:
        return None
    candidatos = [Path(origem)] if origem else _locais_antigos()
    fontes = []
    for c in candidatos:
        try:
            if _tem_dados(c) and c.resolve() != destino.resolve():
                fontes.append(c)
        except OSError:
            continue
    if not fontes:
        return None
    # a mais recente (pela data do arquivo de resultados) é a que a pessoa usou por último
    fonte = max(fontes, key=lambda p: max(((p / a).stat().st_mtime for a in ARQUIVOS if (p / a).exists()), default=0))
    destino.mkdir(parents=True, exist_ok=True)
    trazidos, unidos = [], 0
    for nome in ARQUIVOS:
        o, d = fonte / nome, destino / nome
        if not o.exists():
            continue
        if nome == "resultados.jsonl":
            unidos = _unir_linhas(o, d)
            trazidos.append(nome)
        elif not d.exists():
            shutil.copy2(o, d)
            trazidos.append(nome)
    snaps_o, snaps_d = fonte / "snapshots", destino / "snapshots"
    if snaps_o.is_dir() and not (snaps_d.exists() and any(snaps_d.iterdir())):
        shutil.copytree(snaps_o, snaps_d, dirs_exist_ok=True)
        trazidos.append("snapshots/")
    resumo = {"origem": str(fonte), "em": agora_iso(), "arquivos": trazidos, "resultados_novos": unidos}
    (destino / MARCA).write_text(json.dumps(resumo, ensure_ascii=False, indent=2), "utf-8")
    return resumo
