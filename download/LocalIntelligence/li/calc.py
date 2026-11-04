"""Calculadora de hardware: os dados que o navegador precisa para responder "o que roda na MINHA máquina?".

O motor de cálculo mora em `web/calc.js` (JavaScript, sem dependências) para a mesma conta rodar em dois lugares:
  • na aba Calculadora do painel (aqui, com os modelos do radar e as notas medidas no boss);
  • num arquivo HTML único e autônomo (`python cli.py calculadora`), que qualquer pessoa abre no navegador, offline, sem
    instalar nada — com o catálogo de modelos de uma varredura do radar embutido.

Este módulo só prepara os dados: lê o último snapshot do radar, anexa a parte da prioridade que não depende da máquina,
as notas medidas dos modelos instalados e o catálogo de hardware (`data/hardware.json`). As constantes de calibração vão
junto, vindas de `fit.py` — uma fonte única de verdade; `tests/test_calc.py` confere que o JS dá os mesmos números do Python.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from . import PROTOCOLO, __version__, config, decide, fit, papeis, parque, scout
from .ollama import Ollama
from .util import agora_iso, dias_desde, ler_json

# função extra só da calculadora: não existe no benchmark (não há nota medida para "contexto longo")
PAPEL_CONTEXTO = {
    "id": "contexto", "rotulo": "Documentos longos e muito contexto", "icone": "📚",
    "descricao": "Ler livros, contratos e repositórios inteiros; manter conversas muito longas sem perder o fio.",
    "ctx_alvo": 131072, "exige": [], "onde": "RAG, análise de documentos, agentes de longa duração",
    "nota": "O que importa aqui é o tamanho do contexto que CABE na memória e o peso do cache (KV): modelos de atenção linear/janela deslizante crescem pouco.",
}

_KEEP_ARCH = ("arquitetura", "camadas", "kv_heads", "key_len", "val_len", "janela", "ctx_max", "kv_heads_global", "head_dim_global",
              "k_eq_v", "kv_compartilhadas", "generica", "moe", "experts", "experts_usados")


def arch_compacta(arch: dict) -> dict:
    """Arquitetura enxuta para o JS: as camadas por tipo (cheia / janela / linear) já contadas, em vez da lista por camada."""
    if not arch:
        return {}
    cheias, desliz, lin = fit._camadas_por_tipo(arch)
    out = {k: arch[k] for k in _KEEP_ARCH if arch.get(k) is not None}
    out["camadas_tipo"] = [cheias, desliz, lin]
    return out


def constantes() -> dict:
    return {"KV_BYTES": fit.KV_BYTES, "OVERHEAD_FIXO_GB": fit.OVERHEAD_FIXO_GB, "OVERHEAD_POR_CTX_GB": fit.OVERHEAD_POR_CTX_GB,
            "ESTADO_LINEAR_GB": fit.ESTADO_LINEAR_GB, "EFICIENCIA": fit.EFICIENCIA, "MIN_BPW": fit.MIN_BPW, "CTX_DEGRAUS": fit.CTX_DEGRAUS,
            "RAPIDO_MAX_GB": decide.RAPIDO_MAX_GB}


def _variante(v: dict) -> dict:
    """Só o que o navegador usa; campos vazios ou deriváveis ficam de fora (as variantes são 2/3 do arquivo exportado)."""
    o = {"pull": v["pull"], "quant": v["quant"], "bytes": v["bytes"]}
    if v.get("tag") and v["tag"] != v["quant"]:
        o["tag"] = v["tag"]
    if v.get("extra_bytes"):
        o["extra_bytes"] = int(v["extra_bytes"])
    return o


def _candidato(c: dict, medidos: Dict[str, dict]) -> dict:
    dias = dias_desde(c.get("lancamento"))
    c2 = {**c, "dias": None if dias is None else round(dias, 1)}
    prio: Dict[str, dict] = {}
    for pid in c.get("papeis", []):
        b = decide.prioridade_base(c2, papeis.POR_ID[pid], [])
        prio[pid] = {"escala": round(b["escala"], 4), "resto": round(b["resto"], 4), "razoes": b["razoes"]}
    inst = medidos.get(c["id"])
    return {
        "id": c["id"], "nome": c["nome"], "familia": c.get("familia"), "origem": c["origem"], "params_b": c["params_b"],
        "ativos_b": c.get("ativos_b"), "moe": bool(c.get("moe")), "caps": c.get("caps", []), "dias": c2["dias"],
        "lancamento": (c.get("lancamento") or "")[:10] or None, "data_aproximada": bool(c.get("data_aproximada")),
        "licenca": c.get("licenca"), "licenca_restrita": bool(c.get("licenca_restrita")), "confianca": c.get("confianca"),
        "papeis": c.get("papeis", []), "especializado": c.get("especializado"), "descricao": (c.get("descricao") or "")[:200],
        "repo": c.get("repo"), "repo_gguf": c.get("repo_gguf"), "pop": c.get("baixas") or c.get("pulls") or 0, "ctx_max": c.get("ctx_max"),
        "arch": arch_compacta(c.get("arch") or {}),
        "variantes": [_variante(v) for v in c["variantes"]],
        "prio": prio, "medido": inst,
    }


def _medidos(snap: dict, oll: Optional[Ollama]) -> Dict[str, dict]:
    """Candidato → o que foi MEDIDO no boss (notas por função, tok/s), para os modelos instalados e medidos."""
    out: Dict[str, dict] = {}
    inst = decide.modelos_do_boss(oll) if oll else []
    for c in snap["candidatos"]:
        como = decide._instalado_como(c, inst)
        if not como:
            continue
        m = next(x for x in inst if x["id"] == como)
        r = m.get("medido")
        if not r or not r.get("n_itens"):
            continue
        out[c["id"]] = {"modelo": como, "n_itens": r["n_itens"], "tps": r.get("tps_mediana"),
                        "papeis": {pid: {"nota": v["nota"], "ic": v.get("ic")} for pid, v in r["papeis"].items() if v.get("nota") is not None}}
    return out


def hardware() -> dict:
    return ler_json(config.HARDWARE_ARQ, {"gpus": [], "unificadas": [], "memorias_ram": [], "cpus": [], "sistemas": []})


def dados(oll: Optional[Ollama] = None, incluir_parque: bool = True) -> dict:
    snap = scout.ultimo()
    if not snap:
        return {"vazio": True, "hardware": hardware(), "constantes": constantes(), "versao": __version__}
    medidos = _medidos(snap, oll)
    cands = [_candidato(c, medidos) for c in snap["candidatos"] if not c.get("sem_gguf") and c.get("variantes")]
    lista_papeis = [{k: p.get(k) for k in ("id", "rotulo", "icone", "descricao", "ctx_alvo", "exige", "onde", "nota", "sem_nota")} for p in papeis.PAPEIS]
    lista_papeis.append(PAPEL_CONTEXTO)
    d: Dict[str, Any] = {
        "versao": __version__, "protocolo": PROTOCOLO, "gerado": agora_iso(), "radar": snap["criado"], "constantes": constantes(),
        "kv_cache_ollama": config.carregar().get("kv_cache", "q8_0"), "reserva_vram_gb": config.carregar().get("reserva_vram_gb", 1.3), "hardware": hardware(), "papeis": lista_papeis, "candidatos": cands,
        "n_medidos": len(medidos),
    }
    if incluir_parque:
        pk = parque.carregar_parque(False)
        d["maquinas"] = pk["maquinas"]
        d["esta_maquina"] = next((m["id"] for m in pk["maquinas"] if m.get("local")), None)
    return d


# ------------------------------------------------------------------ arquivo HTML autônomo

_MODELO_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calculadora de hardware para IA local</title>
<style>
__CSS__
</style>
</head>
<body class="solo">
<main id="app"></main>
<script>window.LI_DADOS = __DADOS__;</script>
<script>
__BASE__
</script>
<script>
__CALC__
</script>
<script>
__UI__
</script>
<script>LI_CALC_UI.montar(document.getElementById('app'), window.LI_DADOS, { solo: true });</script>
</body>
</html>
"""


def _para_script(obj: Any) -> str:
    """JSON seguro para dentro de <script>: nunca fecha a tag nem quebra a linha."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # escapa TODO "<", ">" e "&": nenhum texto vindo do radar consegue abrir ou fechar tag, nem iniciar comentário HTML
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def html_autonomo(oll: Optional[Ollama] = None, incluir_parque: bool = False) -> str:
    d = dados(oll, incluir_parque=incluir_parque)
    if d.get("vazio"):
        raise RuntimeError("O radar ainda não rodou: faça uma varredura (python cli.py radar) antes de exportar a calculadora.")
    lido = lambda nome: (config.WEB / nome).read_text("utf-8")
    partes = {"CSS": lido("style.css"), "BASE": lido("base.js"), "CALC": lido("calc.js"), "UI": lido("calc-ui.js"), "DADOS": _para_script(d)}
    return re.sub(r"__(CSS|DADOS|BASE|CALC|UI)__", lambda m: partes[m.group(1)], _MODELO_HTML)  # uma passada só: o conteúdo inserido não é reprocessado
