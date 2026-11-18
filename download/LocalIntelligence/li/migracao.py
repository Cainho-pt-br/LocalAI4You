"""Traz os resultados de uma instalação anterior para a pasta de dados atual.

Por quê: o app instalado pelo ZIP guarda os dados ao lado dele (…\\Programs\\Local AI 4 You\\app\\estado), e o da Microsoft
Store, numa pasta própria (%LOCALAPPDATA%\\LocalAISearch\\estado). Quem trocava de um para o outro "perdia" as notas medidas,
os vereditos e os modelos aposentados. Aqui, na primeira vez que a pasta atual está sem resultados, copiamos do lugar antigo
(sem apagar nada lá e sem sobrescrever nada aqui)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from . import config
from .util import agora_iso

# o que vale levar: notas, velocidade/contexto medidos, vereditos, aposentados, histórico v1 e o último radar.
# config.json NÃO: numa instalação antiga ele pode apontar para o inventário de máquinas de outra pessoa (broker, parque).
ARQUIVOS = ("resultados.jsonl", "sondas.json", "squad.json", "vereditos.json", "aposentados.json", "historico_v1.json")
MARCA = "migrado.json"
# chaves de configuração que só fazem sentido na máquina de origem (parque, acesso remoto): nunca vêm de outra instalação
CONFIG_DA_ORIGEM = ("broker_url", "maquina_id", "hosts_painel", "logins_permitidos")


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


def limpar_config_importada() -> bool:
    """Versões anteriores desta migração copiavam o config.json da instalação antiga, e com ele o endereço do inventário
    de máquinas (parque) de quem fez aquela instalação. Tira essas chaves, uma vez, de quem importou desse jeito."""
    marca = config.ESTADO / MARCA
    try:
        m = json.loads(marca.read_text("utf-8"))
    except (OSError, ValueError):
        return False
    if "config.json" not in (m.get("arquivos") or []) or m.get("config_limpa"):
        return False
    try:
        cfg = json.loads(config.CONFIG_ARQ.read_text("utf-8"))
    except (OSError, ValueError):
        cfg = None
    if isinstance(cfg, dict):
        for k in CONFIG_DA_ORIGEM:
            cfg.pop(k, None)
        config.CONFIG_ARQ.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    m["config_limpa"] = agora_iso()
    marca.write_text(json.dumps(m, ensure_ascii=False, indent=2), "utf-8")
    return True


# ---------------------------------------------------------------- outras instalações (Windows)
def _programas() -> Optional[Path]:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Programs" if base else None


def instalacoes_antigas() -> List[dict]:
    """Outras cópias instaladas pelo ZIP neste computador (a atual não entra). O app da Microsoft Store mostra também a
    instalação do ZIP com o nome de hoje: duas cópias confundem (atalhos diferentes abrem versões diferentes)."""
    prog = _programas()
    if not prog:
        return []
    minha = config.RAIZ.resolve()
    achadas = []
    for nome in ("Local AI Search", "Local AI 4 You"):
        pasta = prog / nome
        app = pasta / "app"
        try:
            if not (app / "cli.py").exists() or minha == app.resolve() or minha.is_relative_to(pasta.resolve()):
                continue
        except OSError:
            continue
        versao = ""
        try:
            versao = (app / "VERSAO.txt").read_text("utf-8").split()[1]
        except (OSError, IndexError):
            pass
        achadas.append({"pasta": str(pasta), "nome": nome, "data": versao, "tem_dados": _tem_dados(app / "estado")})
    return achadas


def remover_instalacao(pasta: str) -> dict:
    """Remove uma instalação antiga do ZIP: guarda antes uma cópia da pasta estado/ dela (backups/), importa o que
    faltar e apaga a pasta e os atalhos que apontam para ela. Só aceita uma pasta da lista de instalacoes_antigas()."""
    validas = {a["pasta"]: a for a in instalacoes_antigas()}
    if pasta not in validas:
        raise ValueError("Essa pasta não é uma instalação antiga do Local AI 4 You.")
    alvo = Path(pasta)
    estado = alvo / "app" / "estado"
    copia = None
    if estado.is_dir():
        importar_dados_antigos(estado, forcar=True)
        copia = config.GRAVAVEL / "backups" / f"instalacao-antiga-{alvo.name.replace(' ', '-')}-{agora_iso()[:10]}"
        shutil.copytree(estado, copia, dirs_exist_ok=True, ignore=shutil.ignore_patterns("cache", "janela"))
    atalhos = _apagar_atalhos(alvo)
    shutil.rmtree(alvo, ignore_errors=True)
    return {"removida": not alvo.exists(), "copia_dos_dados": str(copia) if copia else None, "atalhos_removidos": atalhos}


def _apagar_atalhos(alvo: Path) -> int:
    """Atalhos (.lnk) da Área de Trabalho e do menu Iniciar cujo destino fica dentro da pasta removida."""
    if os.name != "nt":
        return 0
    script = (
        "$alvo='" + str(alvo).replace("'", "''") + "'; $w=New-Object -ComObject WScript.Shell; $n=0;"
        "$lugares=@([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'));"
        "foreach($l in $lugares){ Get-ChildItem -LiteralPath $l -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {"
        "  $t=$w.CreateShortcut($_.FullName).TargetPath; if($t -and $t.StartsWith($alvo, [StringComparison]::OrdinalIgnoreCase)){ Remove-Item -LiteralPath $_.FullName -Force; $n++ } } }"
        "foreach($nome in @('Local AI Search','Local AI 4 You')){ $d=Join-Path ([Environment]::GetFolderPath('Programs')) $nome;"
        "  if((Test-Path $d) -and -not (Get-ChildItem -LiteralPath $d -Force)){ Remove-Item -LiteralPath $d -Force } }"
        "Write-Output $n")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True, text=True,
                           timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return int((r.stdout or "0").strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0
