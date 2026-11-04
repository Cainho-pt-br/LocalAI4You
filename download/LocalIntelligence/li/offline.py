"""Prontidão offline: o que você tem se a internet cair — e como garantir uma segunda cópia.

O Ollama só usa a rede para BAIXAR; gerar texto é 100% local. Então "estar preparado" significa:
(1) o runtime e os modelos certos já estão no disco e íntegros, (2) há uma segunda cópia fora do disco
principal, (3) cada função do dia a dia tem pelo menos um modelo local que a cobre.
"""
from __future__ import annotations

import hashlib
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from . import config, decide, ollama, papeis, parque
from .util import GB, agora_iso, dias_desde, fmt_gb, gravar_json

URL_INSTALADOR = "https://ollama.com/download/OllamaSetup.exe"


def _integridade_rapida(modelo: str, base: Path) -> dict:
    blobs = ollama.blobs_do_modelo(modelo, base)
    if not blobs:
        return {"ok": False, "motivo": "manifesto não encontrado em " + str(base), "blobs": 0, "bytes": 0}
    faltando = [b for b in blobs if not b["tamanho_ok"]]
    return {"ok": not faltando, "blobs": len(blobs), "bytes": sum(b["size"] for b in blobs),
            "motivo": None if not faltando else f"{len(faltando)} arquivo(s) ausente(s) ou com tamanho errado"}


def _estado_kit(destino: Optional[str], modelos: List[dict]) -> dict:
    if not destino:
        return {"configurado": False}
    base = Path(destino)
    if not base.exists():
        return {"configurado": True, "existe": False, "destino": destino}
    por_modelo = {}
    for m in modelos:
        man = ollama.ler_manifest(m["id"], base / "models") or ollama.ler_manifest(m["id"], base)
        raiz = base / "models" if (base / "models").exists() else base
        if not man:
            por_modelo[m["id"]] = "ausente"
            continue
        blobs = ollama.blobs_do_modelo(m["id"], raiz)
        por_modelo[m["id"]] = "em dia" if blobs and all(b["tamanho_ok"] for b in blobs) else "incompleto"
    instalador = any(base.glob("OllamaSetup*.exe"))
    return {"configurado": True, "existe": True, "destino": destino, "modelos": por_modelo, "instalador": instalador,
            "livre_gb": parque.espaco_livre_gb(base)}


def estado(oll: Optional[ollama.Ollama], com_broker: bool = False) -> dict:
    cfg = config.carregar()
    base = ollama.pasta_modelos()
    inst = decide._instalados(oll)
    mesa_t = decide.squad_salvo().get("titulares", {})
    sug = decide.titulares_sugeridos(decide.modelos_do_boss(oll), mesa_t) if inst else {}
    titulares = {pid: (mesa_t.get(pid) or sug.get(pid, {}).get("modelo")) for pid in sug}
    integ = {m["id"]: _integridade_rapida(m["id"], base) for m in inst}
    exe = ollama._exe()
    kit = _estado_kit(cfg.get("backup_modelos_dir"), inst)
    itens: List[dict] = []

    itens.append({"id": "runtime", "titulo": "Ollama instalado neste computador",
                  "status": "ok" if exe else "falta", "detalhe": exe or "Instale o Ollama.",
                  "acao": None if exe else "Baixe o instalador em ollama.com enquanto há internet."})
    ruins = [k for k, v in integ.items() if not v["ok"]]
    itens.append({"id": "integridade", "titulo": f"{len(inst)} modelo(s) íntegros no disco ({base})",
                  "status": "ok" if inst and not ruins else ("falta" if not inst else "atencao"),
                  "detalhe": "Verificação rápida (arquivos presentes com o tamanho do manifesto)." if not ruins else "Problemas: " + "; ".join(f"{k}: {integ[k]['motivo']}" for k in ruins),
                  "acao": None if not ruins else "Rode a verificação profunda ou baixe de novo (`ollama pull`) enquanto há internet."})
    cobertura = {}
    for p in papeis.PAPEIS:
        t = titulares.get(p["id"])
        cobertura[p["id"]] = {"modelo": t, "ok": bool(t and integ.get(t, {}).get("ok"))}
    sem = [papeis.POR_ID[k]["rotulo"] for k, v in cobertura.items() if not v["ok"] and k != "visao"]
    itens.append({"id": "cobertura", "titulo": "Cada função do dia a dia tem um modelo local",
                  "status": "ok" if not sem else "atencao",
                  "detalhe": "Todas as funções cobertas." if not sem else "Sem modelo medido para: " + ", ".join(sem),
                  "acao": None if not sem else "Meça os modelos instalados (aba Laboratório) ou baixe um para cada função em aberto."})
    if not kit.get("configurado"):
        itens.append({"id": "kit", "titulo": "Segunda cópia dos modelos titulares", "status": "falta",
                      "detalhe": "Nenhuma pasta de backup configurada.",
                      "acao": "Defina a pasta do kit (ex.: um HD externo) e exporte os titulares."})
    elif not kit.get("existe"):
        itens.append({"id": "kit", "titulo": "Segunda cópia dos modelos titulares", "status": "atencao",
                      "detalhe": f"A pasta {kit['destino']} não está acessível agora (HD desconectado?).", "acao": "Conecte o disco ou escolha outra pasta."})
    else:
        tit_ids = sorted({t for t in titulares.values() if t})
        defasados = [m for m in tit_ids if kit["modelos"].get(m) != "em dia"]
        itens.append({"id": "kit", "titulo": "Segunda cópia dos modelos titulares",
                      "status": "ok" if not defasados else "atencao",
                      "detalhe": f"Kit em {kit['destino']} · {kit['livre_gb']} GB livres." + ("" if not defasados else " Fora de dia: " + ", ".join(defasados)),
                      "acao": None if not defasados else "Exporte de novo para atualizar o kit."})
        itens.append({"id": "instalador", "titulo": "Instalador do Ollama guardado no kit", "status": "ok" if kit.get("instalador") else "atencao",
                      "detalhe": "OllamaSetup.exe encontrado no kit." if kit.get("instalador") else "Sem instalador no kit: se o Windows for reinstalado sem internet, você não reinstala o Ollama.",
                      "acao": None if kit.get("instalador") else f"Baixe {URL_INSTALADOR} e coloque na pasta do kit."})
    livre = parque.espaco_livre_gb(base)
    itens.append({"id": "disco", "titulo": "Espaço livre para os modelos", "status": "ok" if (livre or 0) > 40 else "atencao",
                  "detalhe": f"{livre} GB livres no disco dos modelos.", "acao": None})
    snap_idade = None
    from . import scout
    s = scout.ultimo()
    if s:
        snap_idade = round(dias_desde(s["criado"]) or 0, 1)
    itens.append({"id": "radar", "titulo": "O radar funciona sem internet (com dados salvos)",
                  "status": "ok" if s else "atencao",
                  "detalhe": f"Último radar há {snap_idade} dias; o painel abre e mostra isso mesmo offline." if s else "Sem varredura salva.",
                  "acao": None if s else "Faça uma varredura enquanto há internet."})
    itens.append({"id": "cliente", "titulo": "Aplicativo de conversa que roda offline", "status": "info",
                  "detalhe": "O painel não consegue verificar isso. Open WebUI, LM Studio e Bionic conversam com o Ollama local sem internet — teste uma vez com o Wi-Fi desligado.",
                  "acao": None})
    nota = {"ok": 0, "info": 0, "atencao": 1, "falta": 2}
    risco = sum(nota[i["status"]] for i in itens)
    return {"itens": itens, "cobertura": cobertura, "integridade": integ, "kit": kit,
            "nivel": "pronto" if risco == 0 else "parcial" if risco <= 3 else "vulneravel",
            "resumo": ("Preparado: se a internet cair hoje, você segue trabalhando com modelos locais." if risco == 0
                       else f"{sum(1 for i in itens if i['status'] in ('atencao','falta'))} ponto(s) para resolver antes de precisar."),
            "pasta_modelos": str(base)}


def verificar_profundo(modelo: str, ao_progredir: Optional[Callable[[dict], None]] = None,
                       cancelar: Optional[threading.Event] = None) -> dict:
    """Recalcula o SHA-256 de cada arquivo do modelo e compara com o nome do blob (que é o próprio hash)."""
    blobs = ollama.blobs_do_modelo(modelo)
    total = sum(b["size"] for b in blobs)
    lido, ruins = 0, []
    t0 = time.time()
    for b in blobs:
        if cancelar and cancelar.is_set():
            return {"ok": False, "cancelado": True}
        h = hashlib.sha256()
        try:
            with open(b["path"], "rb") as f:
                while True:
                    bloco = f.read(8 << 20)
                    if not bloco:
                        break
                    h.update(bloco)
                    lido += len(bloco)
                    if ao_progredir:
                        ao_progredir({"msg": f"Verificando {modelo}: {100 * lido // max(total, 1)}%", "pct": 100 * lido // max(total, 1),
                                      "mb_s": round(lido / max(time.time() - t0, 0.01) / 1e6)})
        except OSError as e:
            ruins.append({"digest": b["digest"], "erro": str(e)})
            continue
        if "sha256:" + h.hexdigest() != b["digest"]:
            ruins.append({"digest": b["digest"], "erro": "hash diferente"})
    return {"ok": not ruins, "arquivos": len(blobs), "ruins": ruins, "bytes": total}


def exportar_kit(destino: str, modelos: List[str], ao_progredir: Optional[Callable[[dict], None]] = None,
                 cancelar: Optional[threading.Event] = None) -> dict:
    """Copia manifestos e arquivos (blobs) dos modelos para `destino/models`, mais um guia de restauração.

    Para restaurar: apontar OLLAMA_MODELS para essa pasta (modo portátil) ou copiar de volta para a pasta do Ollama.
    """
    dest = Path(destino).expanduser()
    origem = ollama.pasta_modelos()
    if dest.resolve() == origem.resolve() or origem.resolve() in dest.resolve().parents:
        raise ValueError("O destino não pode ficar dentro da pasta de modelos do Ollama.")
    raiz = dest / "models"
    raiz.mkdir(parents=True, exist_ok=True)
    plano: List[tuple] = []
    for m in modelos:
        man = ollama.caminho_manifest(m, origem)
        if not man.exists():
            raise ValueError(f"Manifesto de {m} não encontrado em {origem}.")
        plano.append((m, man))
    total = sum(b["size"] for m, _ in plano for b in ollama.blobs_do_modelo(m, origem))
    livre = parque.espaco_livre_gb(dest)
    if livre is not None and livre * GB < total * 1.02:
        raise ValueError(f"Espaço insuficiente em {dest}: precisa de {fmt_gb(total)}, há {livre} GB livres.")
    copiado, t0, copiados = 0, time.time(), []
    for m, man in plano:
        for b in ollama.blobs_do_modelo(m, origem):
            if cancelar and cancelar.is_set():
                return {"ok": False, "cancelado": True, "modelos": copiados}
            alvo = raiz / "blobs" / Path(b["path"]).name
            alvo.parent.mkdir(parents=True, exist_ok=True)
            if not (alvo.exists() and alvo.stat().st_size == b["size"]):
                tmp = alvo.with_suffix(".parte")
                shutil.copyfile(b["path"], tmp)
                tmp.replace(alvo)
            copiado += b["size"]
            if ao_progredir:
                ao_progredir({"msg": f"Copiando {m}: {100 * copiado // max(total, 1)}%", "pct": 100 * copiado // max(total, 1),
                              "mb_s": round(copiado / max(time.time() - t0, 0.01) / 1e6)})
        rel = man.relative_to(origem)
        (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(man, raiz / rel)
        copiados.append(m)
    kit = {"criado": agora_iso(), "modelos": copiados, "bytes": total, "origem": str(origem)}
    gravar_json(dest / "kit.json", kit)
    (dest / "RESTAURAR.md").write_text(_guia_restauracao(copiados), encoding="utf-8")
    (dest / "usar-sem-instalar.bat").write_text(
        "@echo off\r\nrem Usa os modelos deste kit sem copiar nada: aponta o Ollama para a pasta models ao lado.\r\n"
        "set OLLAMA_MODELS=%~dp0models\r\nset OLLAMA_FLASH_ATTENTION=1\r\nset OLLAMA_KV_CACHE_TYPE=q8_0\r\n"
        "echo Iniciando o Ollama com os modelos do kit...\r\nollama serve\r\n", encoding="utf-8")
    return {"ok": True, "modelos": copiados, "bytes": total, "destino": str(dest)}


def _guia_restauracao(modelos: List[str]) -> str:
    lista = "\n".join(f"- `{m}`" for m in modelos)
    return f"""# Kit offline de modelos locais

Gerado pelo Local Intelligence em {agora_iso()}. Modelos neste kit:

{lista}

## Restaurar sem internet

1. Instale o Ollama (guarde aqui o `OllamaSetup.exe` — baixe em {URL_INSTALADOR} enquanto houver internet).
2. **Opção A — usar direto do kit:** dê dois cliques em `usar-sem-instalar.bat` (deixa o Ollama lendo `models\\` desta pasta).
3. **Opção B — copiar para o disco:** copie o conteúdo de `models\\` para a pasta de modelos do Ollama
   (por padrão `%USERPROFILE%\\.ollama\\models`, ou a definida em `OLLAMA_MODELS`) e reinicie o Ollama.
4. Confira com `ollama list`. Teste: `ollama run <modelo> "olá"`.

Os arquivos são verificáveis: o nome de cada arquivo em `models\\blobs` é o próprio SHA-256 do conteúdo.
"""
