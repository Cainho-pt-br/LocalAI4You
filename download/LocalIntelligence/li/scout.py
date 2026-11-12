"""Radar de modelos: junta Ollama library + Hugging Face em candidatos comparáveis e guarda snapshots.

Um candidato = uma família num tamanho (ex.: "qwen3.8 27B"), com todas as variantes de quantização
baixáveis e o tamanho EXATO de cada uma. O encaixe por máquina é calculado em decide.py.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import config, fit
from .fontes import hf, ollama_lib
from .util import agora_iso, dias_desde, gravar_json, ler_json, mapa_paralelo

_TAG_TAMANHO = re.compile(r"^(e?\d+(?:\.\d+)?[bm](?:-a\d+(?:\.\d+)?b)?)(?:-|$)")   # "e2b"/"e4b" = parâmetros efetivos (Gemma 3n/4)
DIAS_FAMILIA_RECENTE = 120   # família do Ollama atualizada há até isto: sempre lida, qualquer que seja o número de downloads
_TAG_EXCLUIR = re.compile(r"(?i)(mlx|cloud|nvfp4|mxfp8|coreml|-gguf$|(^|-)(base|text|pretrain\w*)(-|$))")  # base/text = sem instrução


# ------------------------------------------------------------------ normalização de nomes

def chave_familia(s: str) -> str:
    """'Qwen3.8-27B' / 'qwen3.8' / 'qwen3.8:27b' → 'qwen38' (só letras e dígitos, sem tamanho)."""
    s = s.split("/")[-1].lower().split(":")[0]
    s = re.sub(r"[-_ ]\d+(?:\.\d+)?[bm](?:[-_ ]?a\d+(?:\.\d+)?b)?(?![a-z0-9]).*$", "", s)
    s = re.sub(r"-(it|instruct|chat|gguf)$", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def tamanho_de_nome_hf(nome: str) -> Optional[str]:
    m = re.search(r"(?i)(\d+(?:\.\d+)?[bm])(?:[-_ ]?(a\d+(?:\.\d+)?b))?(?![a-z0-9])", nome)
    if not m:
        return None
    return (m.group(1) + ("-" + m.group(2) if m.group(2) else "")).lower()


def papeis_provaveis(nome: str, caps: List[str], params_b: Optional[float], desc: str = "") -> List[str]:
    """Para que funções o modelo se candidata. Modelo de código puro não vira assistente de conversa;
    modelo geral (mesmo com visão) serve para conversa, regras e — se tiver ferramentas — código/agente."""
    n = (nome + " " + desc).lower()
    so_codigo = bool(re.search(r"coder|codestral|devstral|starcoder|codegemma|code\b|-code-|swe-|sqlcoder", n))
    # "VL"/"vision" no nome = modelo de visão primeiro (Qwen3-VL, LFM2.5-VL, MiniCPM-V…): não entra como assistente de texto,
    # mesmo que converse. Modelos gerais com visão nativa (Qwen 3.5/3.8, Gemma 4) não têm isso no nome e seguem como gerais.
    so_visao = bool(re.search(r"(?i)(^|[-_ .])(vl|vlm|vision|llava|minicpm-v|internvl)([-_ .:]|$)", nome))
    papeis: List[str] = []
    if so_visao:
        return ["visao"]
    if so_codigo:
        papeis.append("codigo")
        if "tools" in caps:
            papeis.append("agente")
    else:
        papeis += ["chat_pt", "regras"]
        if "tools" in caps or re.search(r"agent|tool|function", n):
            papeis.append("agente")
            if (params_b or 0) >= 3:  # medido: qwen3.5:4b faz 77 em código (HumanEval) — modelos de 3–8B também servem a quem tem 8 GB de VRAM
                papeis.append("codigo")
        if "thinking" in caps or re.search(r"reason|think|\br1\b|magistral|math|logic|\bcot\b", n):
            papeis.append("raciocinio")
    if "vision" in caps or re.search(r"vision|-vl\b|visual|multimodal", n):
        papeis.append("visao")
    if params_b is not None and params_b <= 5.0 and not so_codigo:
        papeis.append("rapido")
    out: List[str] = []
    for p in papeis:
        if p not in out:
            out.append(p)
    return out


_ESPECIALIZADO = re.compile(
    r"(?i)(computer[- ]use|gui[- ]agent|desktop[- ]agent|web[- ]agent|browser[- ]automation|\bocr\b|ui-mate|embodied|\brobot|"
    r"medical|clinical|protein|biolog|chemistry|translat|(?<!van)guard(?:ian)?\b|\breward\b|\bjudge\b|decision model|retriev|\bembed|rerank|speech|\btts\b|\basr\b|"
    r"text-to-sql|\bsql\b|context-management|visual-text-compression|\bmedia\b|\bsports?\b|\btennis\b|\bfara\b|lensvlm|"
    r"autonomous[- ]driving|time[- ]series|forecast|geospatial|\blegal\b|\bfinance\b|\bfinancial\b)")
_LICENCAS_RESTRITAS = ("cc-by-nc", "other", "research", "non-commercial", "llama", "apple-amlr", "gemma")


def eh_especializado(nome: str, tags: List[str], descricao: str = "") -> Optional[str]:
    """Modelo feito para UMA tarefa estreita (OCR, agente de GUI, tradução…): não entra como assistente geral."""
    alvo = " ".join([nome, descricao] + list(tags or []))
    m = _ESPECIALIZADO.search(alvo)
    return m.group(1).lower() if m else None


def arch_generica(params_b: float) -> dict:
    """Quando não achamos o config.json: uma arquitetura densa típica (conservadora) para o KV cache."""
    camadas = int(24 + 1.6 * (params_b ** 0.9))
    return {"arquitetura": "generica", "camadas": camadas, "kv_heads": 8, "key_len": 128, "val_len": 128,
            "ctx_max": 32768, "generica": True}


# ------------------------------------------------------------------ Ollama

def _variantes_ollama(nome: str, descricao: str, caps_fam: List[str]) -> Dict[str, dict]:
    """Agrupa as tags da família por tamanho. Retorna {tamanho: {variantes:[...], ctx, entradas}}."""
    linhas = ollama_lib.tags(nome)
    por_digest: Dict[str, List[dict]] = {}
    for t in linhas:
        por_digest.setdefault(t.get("digest") or t["tag"], []).append(t)
    grupos: Dict[str, dict] = {}
    for t in linhas:
        tag = t["tag"]
        if _TAG_EXCLUIR.search(tag):
            continue
        m = _TAG_TAMANHO.match(tag)
        if tag == "latest" or not m:
            # 'latest' e apelidos ('cloud', 'instruct'...) duplicam outra tag pelo digest: usa a de tamanho
            irmas = [x for x in por_digest.get(t.get("digest") or "", []) if _TAG_TAMANHO.match(x["tag"])]
            if not irmas:
                continue
            continue
        tam = m.group(1).lower()
        resto = tag[len(tam):].strip("-")
        quant = fit.quant_de_nome(resto.replace("-", "_")) if resto else None
        g = grupos.setdefault(tam, {"variantes": [], "ctx": t.get("ctx"), "entradas": t.get("entradas", ["text"])})
        g["variantes"].append({
            "tag": tag, "pull": f"{nome}:{tag}", "quant": quant or "padrão", "bytes": t["bytes"],
            "padrao": quant is None and not resto, "digest": t.get("digest"),
        })
    return grupos


def _params_do_tamanho(tam: str) -> tuple:
    e = re.match(r"^e(\d+(?:\.\d+)?)b$", tam)   # Gemma 4 "E2B"/"E4B": parâmetros efetivos (o arquivo é maior: embeddings por camada)
    if e:
        return float(e.group(1)), None
    m = re.match(r"^(\d+(?:\.\d+)?)([bm])(?:-a(\d+(?:\.\d+)?)b)?$", tam)
    if not m:
        return None, None
    p = float(m.group(1)) * (1 if m.group(2) == "b" else 0.001)
    return p, (float(m.group(3)) if m.group(3) else None)


def candidatos_ollama(forcar: bool, limite_familias: int, prog: Callable[[str], None]) -> List[dict]:
    cfg = config.carregar()
    teto_b = float(cfg.get("params_max_b", 130))
    novos = ollama_lib.listar("newest", forcar)
    pops = ollama_lib.listar("popular", forcar)
    familias: Dict[str, dict] = {}
    for origem, lista in (("novo", novos), ("popular", pops)):
        for f in lista:
            d = familias.setdefault(f["nome"], {**f, "origens": []})
            d["origens"].append(origem)
    selecionadas = []
    for nome, f in familias.items():
        caps = f["caps"]
        if "embedding" in caps and "tools" not in caps:
            continue
        if re.search(r"(?i)embed|rerank|bge-|nomic|minilm|snowflake-arctic-embed|clip|whisper|flux", nome):
            continue
        tams = [t for t in f["tamanhos"] if _params_do_tamanho(t)[0]]
        if tams and min(_params_do_tamanho(t)[0] for t in tams) > teto_b:
            continue  # grande demais até para uma estação com 96 GB: nem a calculadora usa
        idade = dias_desde(f.get("atualizado"))
        recente = idade is not None and idade < 540
        if not (recente or f["pulls"] >= 1_000_000):
            continue
        selecionadas.append(f)
    # Todas as famílias ATUALIZADAS há pouco entram, mesmo com poucos downloads (família nova tem poucos): a página "newest" do Ollama devolve a biblioteca
    # inteira, então "novo" não distinguia nada e o corte por downloads derrubava 41 de 50 famílias recentes (lfm2.5, nemotron-3-nano, granite4.2, lfm3…).
    # Medido em 2026-10-29. O resto do orçamento vai para as mais populares.
    def _idade(f: dict) -> Optional[float]:
        return dias_desde(f.get("atualizado"))
    recentes = sorted((f for f in selecionadas if (_idade(f) or 1e9) <= DIAS_FAMILIA_RECENTE), key=lambda f: _idade(f) or 0)
    demais = sorted((f for f in selecionadas if (_idade(f) or 1e9) > DIAS_FAMILIA_RECENTE), key=lambda f: -f["pulls"])
    selecionadas = (recentes + demais)[:max(limite_familias, len(recentes) + 60)]
    prog(f"Ollama: lendo variantes de {len(selecionadas)} famílias…")
    resultados = mapa_paralelo(lambda f: (f, _variantes_ollama(f["nome"], f["descricao"], f["caps"])), selecionadas, workers=6)
    cands: List[dict] = []
    for r in resultados:
        if not r:
            continue
        f, grupos = r
        for tam, g in grupos.items():
            params, ativos = _params_do_tamanho(tam)
            if not params or params > teto_b or not g["variantes"]:
                continue
            vs = sorted(g["variantes"], key=lambda v: v["bytes"])
            cands.append({
                "id": f"ollama:{f['nome']}:{tam}", "origem": "ollama", "familia": f["nome"], "tamanho": tam,
                "nome": f"{f['nome']} {tam.upper()}", "descricao": f["descricao"], "caps": f["caps"],  # `caps_declaradas` corrige por tamanho
                "params_b": params, "ativos_b": ativos, "moe": bool(ativos), "ctx_max": g.get("ctx"),
                "entradas": g.get("entradas", ["text"]), "pulls": f["pulls"], "atualizado": f.get("atualizado"),
                "lancamento": f.get("atualizado"), "data_aproximada": True, "variantes": vs,
                "confianca": "ollama-oficial", "tags_lista": f["origens"],
                "url": f"https://ollama.com/library/{f['nome']}",
            })
    # tamanho nominal da tag ("4b") != parâmetros reais (4,7B): o manifesto do registry tem o número certo
    def params_reais(c: dict) -> None:
        padrao = next((v for v in c["variantes"] if v.get("padrao")), None) or (c["variantes"][0] if c["variantes"] else None)
        if not padrao:
            return
        m = ollama_lib.manifest(c["familia"], padrao["tag"])
        if m:
            p = ollama_lib.parse_params_b(m.get("params"))
            if p:
                c["params_nominal_b"], c["params_b"] = c["params_b"], round(p, 2)
            if m.get("quant") and padrao.get("quant") == "padrão":
                padrao["quant"] = m["quant"]
    mapa_paralelo(params_reais, cands, workers=6)

    # '30b' e '30b-a3b' são a mesma coisa publicada com dois apelidos (mesmo digest): fica o nome mais específico
    por_digest: Dict[tuple, dict] = {}
    for c in cands:
        dgs = [v.get("digest") for v in c["variantes"] if v.get("digest")]
        chave = (c["familia"], dgs[0]) if dgs else (c["id"], None)
        atual = por_digest.get(chave)
        if atual is None or len(c["tamanho"]) > len(atual["tamanho"]):
            por_digest[chave] = c
    return list(por_digest.values())


# ------------------------------------------------------------------ Hugging Face

def _hf_itens(forcar: bool, prog: Callable[[str], None]) -> List[dict]:
    cfg = config.carregar()
    labs = cfg.get("labs_observados", [])
    prog(f"Hugging Face: lançamentos de {len(labs)} laboratórios…")
    listas = mapa_paralelo(lambda a: [{**x, "_lab": a} for x in (hf.listar_por_autor(a, 100, forcar) or []) + (hf.listar_por_autor_populares(a, 60, forcar) or [])], labs, workers=6)
    itens: List[dict] = []
    for l in listas:
        itens += l or []
    prog("Hugging Face: tendências e mais baixados…")
    # tendência de TEXTO e de imagem+texto separadas e fundas (o needle3 estava em 68º e o corte era 60): lançamento de laboratório fora da lista entra por aqui
    for lst in (hf.listar_tendencia(60, False, forcar), hf.listar_tendencia(60, True, forcar), hf.listar_populares_recentes(40, forcar),
                hf.listar_tendencia(300, False, forcar, "text-generation"), hf.listar_tendencia(200, False, forcar, "image-text-to-text")):
        itens += lst or []
    vistos, out = set(), []
    for it in itens:
        rid = it.get("id") or it.get("modelId")
        if not rid or rid in vistos:
            continue
        vistos.add(rid)
        it["id"] = rid
        out.append(it)
    return out


def _filtrar_hf(it: dict, dias_max: float) -> bool:
    nome = it["id"].split("/")[-1]
    if (it.get("pipeline_tag") or "") not in hf.PIPELINES_TEXTO:
        return False
    if hf.eh_derivado(nome) or hf.eh_base_sem_instrucao(nome):
        return False
    idade = dias_desde(it.get("createdAt"))
    # modelos PEQUENOS (≤ 3B) são os que cabem em Raspberry/notebook: valem mesmo com mais de 200 dias (LFM2.5-230M, Granite 4 350M, Falcon-H1 0.5B…)
    p_nome = _params_do_tamanho(tamanho_de_nome_hf(nome) or "")[0]
    limite = max(dias_max, 700) if p_nome is not None and p_nome <= 3.0 else dias_max
    if idade is None or idade > limite:
        return False
    return True


def candidatos_hf(forcar: bool, prog: Callable[[str], None], dias_max: float = 200, ja_ollama: Optional[Dict[str, dict]] = None) -> List[dict]:
    ja_ollama = ja_ollama or {}
    itens = [it for it in _hf_itens(forcar, prog) if _filtrar_hf(it, dias_max)]
    prog(f"Hugging Face: {len(itens)} lançamentos recentes de texto; lendo detalhes…")
    dets = mapa_paralelo(lambda it: hf.detalhe(it["id"], forcar), itens, workers=6)
    cands = []
    for it, det in zip(itens, dets):
        nome = it["id"].split("/")[-1]
        params = hf.parametros_b(det, nome)
        if not params:
            continue
        tam = tamanho_de_nome_hf(nome) or f"{round(params)}b"
        ativos = fit.ativos_de_nome(nome)
        comunidade = hf.eh_comunidade(nome) or it["id"].split("/")[0] not in config.carregar().get("labs_observados", [])
        cands.append({
            "id": f"hf:{it['id']}", "origem": "hf", "repo": it["id"], "familia": chave_familia(nome), "tamanho": tam,
            "nome": nome, "descricao": "", "caps": [], "params_b": params, "ativos_b": ativos, "moe": bool(ativos),
            "ctx_max": None, "baixas": it.get("downloads", 0), "curtidas": it.get("likes", 0),
            "tendencia": it.get("trendingScore"), "lancamento": it.get("createdAt"), "atualizado": det.get("lastModified") if det else None,
            "pipeline": it.get("pipeline_tag"), "licenca": hf.licenca(det), "tags_hf": (det or {}).get("tags", [])[:25],
            "confianca": "comunidade" if comunidade else "laboratorio", "entradas": ["text"],
            "url": f"https://huggingface.co/{it['id']}", "variantes": [],
        })
    return cands


def _anexar_gguf_hf(c: dict) -> None:
    """Para candidato do HF: acha o GGUF confiável e lista quantizações com tamanho real."""
    repo_gguf = c["repo"] if "gguf" in c["repo"].lower() else None
    meta = None
    if not repo_gguf:
        meta = hf.melhor_repo_gguf(c["repo"])
        repo_gguf = meta["id"] if meta else None
    if not repo_gguf:
        c["sem_gguf"] = True
        return
    arq = hf.arquivos_gguf(repo_gguf)
    c["repo_gguf"] = repo_gguf
    c["variantes"] = [{"tag": v["quant"], "pull": f"hf.co/{repo_gguf}:{v['quant']}", "quant": v["quant"],
                       "bytes": v["bytes"], "extra_bytes": int(arq.get("mmproj_bytes") or 0), "padrao": False} for v in arq["variantes"]]
    if arq.get("mmproj_bytes"):
        c["mmproj_bytes"] = arq["mmproj_bytes"]
        if "vision" not in c["caps"]:
            c["caps"] = c["caps"] + ["vision"]
    c["sem_gguf"] = not c["variantes"]


# ------------------------------------------------------------------ união

def _fundir_apelidos(cands: List[dict]) -> List[dict]:
    """'35b' e '35b-a3b' (ou '26b' e '26b-a4b') são o mesmo modelo no Ollama: junta variantes e mantém a MoE."""
    grupos: Dict[str, List[dict]] = {}
    for c in cands:
        grupos.setdefault(c.get("repo") or c["id"], []).append(c)
    out = []
    for g in grupos.values():
        if len(g) == 1:
            out.append(g[0])
            continue
        g.sort(key=lambda c: (-len(c["variantes"]), -len(c["tamanho"])))
        base = g[0]
        ativos = next((c["ativos_b"] for c in g if c.get("ativos_b")), None)
        vistos = {v["pull"] for v in base["variantes"]}
        for c in g[1:]:
            for v in c["variantes"]:
                if v["pull"] not in vistos:
                    base["variantes"].append(v)
                    vistos.add(v["pull"])
        base["variantes"].sort(key=lambda v: v["bytes"])
        if ativos:
            base["ativos_b"], base["moe"] = ativos, True
            if not re.search(r"-a\d", base["tamanho"]):
                base["tamanho"] = next(c["tamanho"] for c in g if c.get("ativos_b"))
                base["nome"] = f"{base['familia']} {base['tamanho'].upper()}"
                base["id"] = f"ollama:{base['familia']}:{base['tamanho']}"
        out.append(base)
    return out


def _casar(c_hf: dict, ollama_cands: List[dict]) -> Optional[dict]:
    if c_hf.get("confianca") != "laboratorio":
        return None  # variante comunitária (abliterated, merge…) nunca é "o mesmo modelo" do Ollama
    for o in ollama_cands:
        if chave_familia(o["familia"]) == c_hf["familia"] and o["tamanho"].split("-")[0] == c_hf["tamanho"].split("-")[0]:
            return o
    return None


def varrer(forcar: bool = False, limite_familias: int = 110, ao_progredir: Optional[Callable[[str], None]] = None,
           com_hf: bool = True) -> dict:
    prog = ao_progredir or (lambda s: None)
    config.garantir_pastas()
    fontes = {"ollama": True, "hf": True}
    try:
        cands_o = candidatos_ollama(forcar, limite_familias, prog)
    except Exception as e:
        fontes["ollama"] = f"erro: {e}"
        cands_o = []
    cands_h: List[dict] = []
    if com_hf:
        try:
            cands_h = candidatos_hf(forcar, prog)
        except Exception as e:
            fontes["hf"] = f"erro: {e}"
    else:
        fontes["hf"] = "pulado"

    # HF que já existe no Ollama vira metadado do candidato Ollama (data de lançamento real, repo, arquitetura)
    so_hf = []
    for h in cands_h:
        o = _casar(h, cands_o)
        if o:
            o["repo"] = h["repo"]
            if h.get("lancamento"):
                o["lancamento"], o["data_aproximada"] = h["lancamento"], False
            o["baixas"], o["curtidas"], o["licenca"] = h.get("baixas"), h.get("curtidas"), h.get("licenca")
            o["tags_hf"] = h.get("tags_hf")
        else:
            so_hf.append(h)
    # Ollama sem par no HF ainda: procura o repositório-base (data real, licença, config.json)
    def achar_base(o: dict) -> None:
        if o.get("repo") or o["params_b"] < 0.5:
            return
        it = hf.buscar_base(o["familia"], o["tamanho"], chave_familia, tamanho_de_nome_hf, config.carregar().get("labs_observados", []))
        if it:
            o["repo"] = it["id"]
            det = hf.detalhe(it["id"], forcar)
            if it.get("createdAt"):
                o["lancamento"], o["data_aproximada"] = it["createdAt"], False
            o["baixas"], o["curtidas"] = it.get("downloads"), it.get("likes")
            o["licenca"] = hf.licenca(det)
    prog(f"Hugging Face: casando {sum(1 for o in cands_o if not o.get('repo'))} famílias do Ollama com o repositório-base…")
    mapa_paralelo(achar_base, cands_o, workers=6)

    # Ollama só publica Q4/Q8 etc.; modelos grandes só cabem em quantização menor, que existe no HF (GGUF)
    def gguf_extra(o: dict) -> None:
        if not o.get("repo") or o["params_b"] < 12:
            return
        meta = hf.melhor_repo_gguf(o["repo"])
        if not meta:
            return
        arq = hf.arquivos_gguf(meta["id"])
        ja = {v["quant"].upper() for v in o["variantes"]}
        for v in arq["variantes"]:
            if v["quant"].upper() in ja:
                continue
            o["variantes"].append({"tag": v["quant"], "pull": f"hf.co/{meta['id']}:{v['quant']}", "quant": v["quant"],
                                   "bytes": v["bytes"], "padrao": False, "fonte": "hf", "repo_gguf": meta["id"],
                                   # o Ollama baixa o projetor de visão junto e pode carregá-lo na GPU: entra na conta (lado seguro)
                                   "extra_bytes": int(arq.get("mmproj_bytes") or 0) if "vision" in (o.get("caps") or []) else 0})
        o["variantes"].sort(key=lambda v: v["bytes"])
    prog("Hugging Face: buscando quantizações menores (GGUF) para os modelos grandes…")
    mapa_paralelo(gguf_extra, cands_o, workers=5)

    # só vale buscar GGUF dos HF-only que cabem em alguma configuração conhecida (≤ params_max_b parâmetros totais)
    teto_b = float(config.carregar().get("params_max_b", 130))
    prog(f"Hugging Face: procurando GGUF de {len(so_hf)} lançamentos que o Ollama ainda não tem…")
    mapa_paralelo(_anexar_gguf_hf, [h for h in so_hf if h["params_b"] <= teto_b], workers=5)

    todos = _fundir_apelidos(cands_o) + [h for h in so_hf if h["params_b"] <= teto_b]

    # arquitetura (para o KV cache): config.json do HF quando existir; senão genérica
    def anexar_arch(c: dict) -> None:
        repo = c.get("repo")
        cfg_json = hf.config_json(repo) if repo else None
        if cfg_json:
            c["arch"] = fit.arch_de_config_hf(cfg_json)
            if not c.get("ctx_max"):
                c["ctx_max"] = c["arch"].get("ctx_max")
            if c["arch"].get("moe") and not c.get("ativos_b"):
                ex = c["arch"].get("experts") or 1
                us = c["arch"].get("experts_usados") or 1
                c["ativos_b"] = round(c["params_b"] * (0.12 + 0.88 * us / ex), 1)
                c["moe"] = True
        else:
            c["arch"] = arch_generica(c["params_b"])
    mapa_paralelo(anexar_arch, todos, workers=6)
    for c in todos:
        # tamanho absurdo (< 1,2 bits por peso) é erro de leitura da página de tags, não um modelo: descarta a variante
        c["variantes"] = [v for v in c["variantes"] if fit.bpw(v["bytes"], c["params_b"]) >= 1.2]
        c.setdefault("arch", arch_generica(c["params_b"]))
        c["papeis"] = papeis_provaveis(c["nome"], c.get("caps", []), c["params_b"], c.get("descricao", ""))
        c["especializado"] = eh_especializado(c["nome"], c.get("tags_hf", []), c.get("descricao", ""))
        lic = (c.get("licenca") or "").lower()
        c["licenca_restrita"] = bool(lic) and any(k in lic for k in _LICENCAS_RESTRITAS) and lic not in ("gemma",)
        c["dias"] = None if not c.get("lancamento") else round(dias_desde(c["lancamento"]) or 0, 1)
        # data aproximada (só a de atualização no Ollama) não prova lançamento recente: só vira "novo" no diff entre varreduras
        c["novo"] = c["dias"] is not None and c["dias"] <= config.carregar().get("radar_dias_novo", 45) and not c.get("data_aproximada")

    snap = {"criado": agora_iso(), "fontes": fontes, "total": len(todos), "candidatos": todos}
    salvar_snapshot(snap)
    return snap


# ------------------------------------------------------------------ snapshots e novidades

def salvar_snapshot(snap: dict) -> Path:
    config.garantir_pastas()
    nome = datetime.now().strftime("%Y-%m-%d-%H%M") + ".json"
    mini = {"criado": snap["criado"], "fontes": snap["fontes"], "ids": {
        c["id"]: {"nome": c["nome"], "lancamento": c.get("lancamento"), "pulls": c.get("pulls"), "baixas": c.get("baixas")}
        for c in snap["candidatos"]}}
    p = config.SNAPSHOTS / nome
    gravar_json(p, mini, indent=0)
    gravar_json(config.SNAPSHOTS / "ultimo-completo.json", snap, indent=0)
    return p


def caps_declaradas(c: dict) -> List[str]:
    """No Ollama a lista de capacidades é da FAMÍLIA (gemma3 inteiro = 'vision'), mas só os tamanhos com entrada de imagem
    (gemma3:4b+) enxergam. A entrada declarada por tamanho (`entradas`) manda; 'audio' idem."""
    caps = list(c.get("caps") or [])
    # IBM Granite Switch: o Ollama o carrega como modelo de decisão (adaptadores LoRA escolhidos por token), não de conversa
    switch = bool(re.search(r"granite[-_ ]?switch", str(c.get("id") or c.get("repo") or ""), re.I))
    if "decision" not in caps and (switch or (c.get("origem") == "hf" and ({"decision-model", "decision"} & set(c.get("tags_hf") or []) or c.get("pipeline") == "feature-extraction"))):
        caps.append("decision")   # d1-omni & cia.: respondem perguntas tipadas sem gerar texto; NÃO são modelos de conversa
    if c.get("origem") != "ollama" or not c.get("entradas"):
        return caps
    ent = set(c["entradas"])
    for cap, entrada in (("vision", "image"), ("audio", "audio")):
        if cap in caps and entrada not in ent:
            caps.remove(cap)
        elif cap not in caps and entrada in ent:
            caps.append(cap)
    return caps


def ultimo() -> Optional[dict]:
    snap = ler_json(config.SNAPSHOTS / "ultimo-completo.json") or catalogo_inicial()
    for c in (snap or {}).get("candidatos", []):
        c["caps"] = caps_declaradas(c)
    return snap


def catalogo_inicial() -> Optional[dict]:
    """O catálogo que veio no ZIP (snapshot completo, gzip). Vale só até a primeira varredura feita nesta máquina.
    As idades são recalculadas para hoje: o arquivo pode ter semanas quando a pessoa baixa o app."""
    import gzip
    import json
    try:
        with gzip.open(config.CATALOGO_INICIAL, "rt", encoding="utf-8") as f:
            snap = json.load(f)
    except (OSError, ValueError):
        return None
    if not snap or not snap.get("candidatos"):
        return None
    snap["embutido"] = True
    dias_novo = config.carregar().get("radar_dias_novo", 45)
    for c in snap["candidatos"]:
        if c.get("lancamento"):
            c["dias"] = round(dias_desde(c["lancamento"]) or 0, 1)
            c["novo"] = c["dias"] <= dias_novo and not c.get("data_aproximada")
    return snap


def gravar_catalogo_inicial(snap: dict, destino: Optional[Path] = None) -> Path:
    """Grava o snapshot completo comprimido para acompanhar o download (usado pelo script do catálogo público)."""
    import gzip
    import json
    destino = destino or config.CATALOGO_INICIAL
    tmp = destino.with_suffix(".tmp")
    with gzip.GzipFile(tmp, "wb", mtime=0) as f:     # mtime fixo: o arquivo só muda quando o conteúdo muda
        f.write(json.dumps(snap, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    tmp.replace(destino)
    return destino


def snapshots_anteriores() -> List[Path]:
    return sorted(p for p in config.SNAPSHOTS.glob("20*.json"))


def novidades(snap: dict, desde_snapshots: int = 1) -> dict:
    """O que apareceu desde a varredura anterior + lançamentos dentro da janela de 'novo'."""
    arqs = snapshots_anteriores()
    # o último arquivo é o próprio snap recém-salvo; compara com o anterior a ele
    anterior = ler_json(arqs[-1 - desde_snapshots]) if len(arqs) > desde_snapshots else None
    ids_ant = set((anterior or {}).get("ids", {}).keys())
    # "apareceu" só conta como novidade se também é recente (ou de data desconhecida): ampliar o escopo da varredura
    # faz modelos antigos "aparecerem" na lista sem terem sido lançados agora
    apareceram = [c["id"] for c in snap["candidatos"]
                  if anterior and c["id"] not in ids_ant and (c.get("dias") is None or c["dias"] <= 180)]
    recentes = [c["id"] for c in snap["candidatos"] if c.get("novo")]
    return {
        "desde": (anterior or {}).get("criado"), "primeira_varredura": anterior is None,
        "apareceram": apareceram, "lancamentos_recentes": recentes,
    }
