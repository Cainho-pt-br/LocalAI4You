"""O cérebro da decisão: transforma radar + medições + hardware em "o que fazer agora".

Três níveis de evidência, sempre rotulados na tela (nunca misturados num número só):
  MEDIDO    — rodou aqui, no protocolo v2, com intervalo de confiança.
  ESTIMADO  — conta de memória/velocidade a partir de arquivos reais (tamanho exato, config.json).
  PRIORIDADE— heurística de "vale testar?" (recência, porte, confiança, popularidade). NÃO é nota de qualidade.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from . import PROTOCOLO, aposentados, config, fit, papeis, parque, resultados, scout
from .bench import sonda, stats
from .ollama import Ollama, ErroOllama
from .util import GB, dias_desde, fmt_gb, ler_json

LIMIAR_TESTAR = 55          # prioridade mínima para sugerir "baixe e teste"
RAPIDO_MAX_GB = 5.0         # "segundo plano" só vale para modelo pequeno


# ------------------------------------------------------------------ contexto

def squad_salvo() -> dict:
    return ler_json(config.SQUAD, {"titulares": {}, "historico": []}) or {"titulares": {}, "historico": []}


def vereditos() -> List[dict]:
    return ler_json(config.VEREDITOS, []) or []


def _instalados(oll: Optional[Ollama]) -> List[dict]:
    if not oll:
        return []
    try:
        if not oll.no_ar():
            return []
        return oll.instalados()
    except ErroOllama:
        return []


def _idade_texto(dias: Optional[float]) -> str:
    if dias is None:
        return "data desconhecida"
    if dias < 1:
        return "hoje"
    if dias < 60:
        return f"há {int(dias)} dias"
    if dias < 700:
        return f"há {int(dias / 30)} meses"
    return f"há {dias / 365:.1f} anos".replace(".", ",")


# ------------------------------------------------------------------ encaixe e velocidade por máquina

def ctx_para(maq: dict, papel: dict) -> int:
    alvo = int(papel.get("ctx_alvo", 8192))
    if not (maq.get("gpu") or {}).get("vram_gb"):
        alvo = min(alvo, 8192 if (maq.get("ram_gb") or 0) >= 8 else 4096)
        if (maq.get("max_modelo_gb") or 99) <= 2:
            alvo = min(alvo, 4096)
    return alvo


def encaixe_candidato(c: dict, maq: dict, papel: dict, cfg: dict) -> Optional[dict]:
    """Escolhe a quantização que cabe na máquina e estima VRAM/RAM, contexto máximo e tokens/s."""
    variantes = [v for v in c.get("variantes", []) if v.get("bytes")]
    if not variantes:
        return None
    ctx = ctx_para(maq, papel)
    if c.get("ctx_max"):
        ctx = max(1024, min(ctx, int(c["ctx_max"])))   # o modelo não aceita mais que isso (moondream: 2k): não calcule KV de 8k que ele nunca usará
    v = fit.escolher_variante(variantes, maq, c["arch"], ctx, c["params_b"], cfg["kv_cache"], cfg["reserva_vram_gb"], c.get("ativos_b"))
    if not v:
        menor = min(variantes, key=lambda x: x["bytes"])
        enc = fit.avaliar_encaixe(menor["bytes"], c["arch"], maq, ctx, cfg["kv_cache"], cfg["reserva_vram_gb"])
        return {"cabe": False, "motivo": f"nem a menor quantização ({menor['quant']}, {fmt_gb(menor['bytes'])}) cabe: orçamento {enc['orcamento_gb']} GB", "variante": menor, "encaixe": enc}
    peso = fit.peso_ativo(v["bytes"], c["params_b"], c.get("ativos_b"))
    tps = fit.estimar_tps(peso, maq, bool(c.get("moe")))
    qual = fit.faixa_qualidade(v["bpw"])
    return {"cabe": True, "variante": v, "encaixe": v["encaixe"], "tps_est": tps, "qualidade": qual[0], "qualidade_obs": qual[1]}


def fator_velocidade(maq: dict, tps: Optional[Tuple[float, float]]) -> float:
    """Fator multiplicador de fluidez: penaliza modelos lentos e bonifica arquiteturas velozes (ex.: MoE) na GPU e CPU."""
    if not tps:
        return 1.0
    mid = (tps[0] + tps[1]) / 2
    cpu = not (maq.get("gpu") or {}).get("vram_gb")
    if cpu:
        return 0.35 if mid < 1.5 else 0.6 if mid < 3 else 0.85 if mid < 6 else 1.0 if mid < 12 else 1.1
    return 0.7 if mid < 15 else 0.96 if mid < 35 else 1.04 if mid < 65 else 1.12


# ------------------------------------------------------------------ prioridade de teste (heurística transparente)

def _familia_versao(nome: str) -> Optional[Tuple[str, float]]:
    """'qwen3.5:9b' → ('qwen', 3.5) ; 'gemma4' → ('gemma', 4.0) ; 'Qwen3.8-27B' → ('qwen', 3.8)."""
    n = nome.lower().split("/")[-1].split(":")[0]
    m = re.match(r"^([a-z]+(?:-[a-z]+)*?)-?(\d+(?:\.\d+)?)", n)
    if not m or m.group(1) in ("gpt",):
        return None
    return m.group(1), float(m.group(2))


_RE_EFETIVO = re.compile(r"(?:^|[\s:_-])e(\d+(?:\.\d+)?)b(?:$|[\s:_-])", re.I)


def porte_efetivo(params: float, ativos: Optional[float], nome: str = "") -> float:
    """Num MoE a "inteligência" fica entre o total e os ativos: média geométrica com 25% de folga, nunca acima do total
    (35B-A3B ≈ 13B denso; 24B-A2B ≈ 9B). Modelos "E4B" contam perto do E (o arquivo traz embeddings por camada).
    Mesma regra de web/calc.js → porteEfetivo."""
    if ativos:
        return min(params, 1.25 * math.sqrt(params * ativos))
    e = _RE_EFETIVO.search(nome or "")
    return min(params, 1.4 * float(e.group(1))) if e else params


def prioridade_base(c: dict, papel: dict, instalados: Optional[List[dict]] = None) -> dict:
    """A parte da prioridade que NÃO depende da máquina: {escala, resto, razoes}."""
    razoes: List[str] = []
    pts = 0.0
    params, ativos = c["params_b"], c.get("ativos_b")
    eff = porte_efetivo(params, ativos, c.get("nome", ""))
    escala = 30 * min(max(math.log(max(eff, 0.5)) / math.log(32), 0.0), 1.0)
    cap = f"{params:g}B" + (f" (MoE eficiente: {ativos:g}B ativos/token)" if ativos else "")
    razoes.append(f"Porte {cap}")

    dias = c.get("dias")
    rec = 30 if dias is not None and dias <= 45 else 24 if dias is not None and dias <= 120 else 16 if dias is not None and dias <= 240 else 8 if dias is not None and dias <= 400 else 2
    pts += rec
    razoes.append("Lançado " + _idade_texto(dias) + (" (data aproximada)" if c.get("data_aproximada") else ""))

    conf = {"ollama-oficial": 10, "laboratorio": 10, "comunidade": 0}.get(c.get("confianca"), 5)
    pts += conf
    if c.get("confianca") == "comunidade":
        razoes.append("Ajuste de comunidade: risco de perder qualidade geral (esquecimento catastrófico)")

    pop = c.get("baixas") or c.get("pulls") or 0
    pts += 14 if pop >= 10_000_000 else 11 if pop >= 1_000_000 else 8 if pop >= 100_000 else 5 if pop >= 10_000 else 1
    if pop >= 100_000:
        razoes.append(f"Muito adotado ({pop / 1e6:.1f} mi downloads)".replace(".", ",") if pop >= 1e6 else f"Adotado ({pop // 1000} mil downloads)")
    elif pop < 10_000:
        razoes.append("Pouco adotado ainda — menos gente validou na prática")

    caps = c.get("caps") or []
    exige = papel.get("exige", [])
    bonus = 0
    if "tools" in exige and "tools" in caps:
        bonus += 5
        razoes.append("Declara suporte a ferramentas")
    if papel["id"] == "raciocinio" and "thinking" in caps:
        bonus += 5
        razoes.append("Tem modo de raciocínio (thinking)")
    if papel["id"] == "codigo" and re.search(r"coder|code|devstral|codestral", c["nome"], re.I):
        bonus += 8
        razoes.append("Especializado em código")
    pts += bonus

    vc = _familia_versao(c.get("familia") or c["nome"])
    for m in instalados or []:
        vi = _familia_versao(m["id"])
        if vc and vi and vc[0] == vi[0] and vc[1] > vi[1]:
            pts += 8
            razoes.append(f"Geração mais nova da família que você já usa ({m['id'].split(':')[0]} → {c.get('familia') or c['nome']})")
            break
    if c.get("licenca_restrita"):
        razoes.append(f"Licença restrita ({c.get('licenca')}): confira antes de uso comercial")
    if re.search(r"(?i)preview|experimental|-exp|flash-next|-next\b|alpha|beta", c["nome"] + " " + c.get("descricao", "")):
        pts -= 10
        razoes.append("Marcado como prévia/experimental")

    if papel["id"] == "rapido" and params > 9:
        pts -= 15
    return {"escala": escala, "resto": pts, "razoes": razoes}


def prioridade(c: dict, papel: dict, enc: Optional[dict], instalados: List[dict], maq: dict) -> dict:
    base = prioridade_base(c, papel, instalados)
    razoes: List[str] = list(base["razoes"])
    escala = base["escala"]
    bpw = (enc or {}).get("variante", {}).get("bpw", 4.5) if enc else 4.5
    if bpw < 3.0:
        escala *= 0.7
    elif bpw < 3.5:
        escala *= 0.85
    pts = escala + base["resto"]
    if enc and enc.get("cabe"):
        pts *= fator_velocidade(maq, enc.get("tps_est"))
        if enc["encaixe"]["nivel"] == "justo":
            pts *= 0.8
            razoes.append(f"Cabe por pouco: contexto máximo estimado {enc['encaixe']['ctx_max'] // 1024}k, sem folga para o resto")
    if papel["id"] == "rapido" and 3.0 <= (c.get("params_b") or 0) <= 5.0:
        pts += 8
        razoes.append("Porte ideal (3B–5B): inteligência sólida em segundo plano")
    return {"pontos": round(max(0, min(100, pts))), "razoes": razoes}


# ------------------------------------------------------------------ instalados com nota

def modelos_do_boss(oll: Optional[Ollama], boss: Optional[dict] = None) -> List[dict]:
    """Instalados + medições + sondas + estimativa de contexto máximo por quantização de cache KV."""
    rows = resultados.carregar()
    if boss is None:
        try:
            boss = parque.maquina_local(parque.carregar_parque(False))
        except Exception:
            boss = None
    cfg = config.carregar()
    res_vram = float(cfg.get("reserva_vram_gb", 1.3))
    out = []
    for m in _instalados(oll):
        r = resultados.resumo(m["id"], m["digest"], "base", rows)
        rt = resultados.resumo(m["id"], m["digest"], "think", rows)
        s = sonda.da_sonda(m["id"], m["digest"])
        ctx_por_kv: Dict[str, dict] = {}
        tps_est = None
        if boss:
            arch = m.get("arch") or {}
            degraus = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]
            teto_nat = int(m.get("ctx_max") or arch.get("ctx_max") or 1048576)
            vram_total_maq = parque.memoria_modelo(boss)[0]
            overhead_sys_cuda = round(res_vram + 0.85, 2)
            for kvt in ("f16", "q8_0", "q4_0"):
                enc = fit.avaliar_encaixe(m["bytes"], arch, boss, 16384, kvt, res_vram)
                orc_gb = enc["orcamento_gb"]
                por_ctx = {}
                for c in degraus:
                    tot_b = fit.vram_total_bytes(m["bytes"], arch, c, kvt)
                    tot_gb = round(tot_b / GB, 2)
                    vram_gpu_est = round(tot_gb + overhead_sys_cuda, 2)
                    por_ctx[str(c)] = {
                        "total_gb": tot_gb,
                        "vram_gpu_est_gb": vram_gpu_est,
                        "folga_gb": round(orc_gb - tot_gb, 2),
                        "folga_gpu_real_gb": round(max(0.0, vram_total_maq - vram_gpu_est), 2),
                        "cabe": tot_gb <= orc_gb,
                        "confortavel": tot_gb <= orc_gb * 0.92,
                        "nativo": c <= teto_nat,
                    }
                ctx_por_kv[kvt] = {
                    "ctx_max": enc["ctx_max"],
                    "usado_16k_gb": enc["usado_ctx_alvo_gb"],
                    "folga_16k_gb": enc["folga_gb"],
                    "orcamento_gb": orc_gb,
                    "por_ctx": por_ctx,
                }
            params_num = (arch.get("params") or 0) / 1e9 if arch.get("params") else None
            ativos_b = fit.ativos_de_nome(m["id"])
            peso_at = fit.peso_ativo(m["bytes"], params_num, ativos_b)
            tps_est = fit.estimar_tps(peso_at, boss, bool(arch.get("moe") or ativos_b))
        item_m = {**m, "medido": r, "medido_think": rt, "sonda": s, "ctx_por_kv": ctx_por_kv, "tps_est": tps_est}
        vram_tot = parque.memoria_modelo(boss)[0]
        item_m["indice_pratico"] = indice_pratico(item_m, None, vram_tot)
        out.append(item_m)
    return out


def _nota(m: dict, papel_id: str) -> Optional[float]:
    r = (m.get("medido") or {}).get("papeis", {}).get(papel_id)
    return r.get("nota") if r else None


def _media_geral(m: dict) -> Optional[float]:
    papeis_med = (m.get("medido") or {}).get("papeis") or {}
    caps = m.get("caps") or []
    vals = []
    for p in papeis.PAPEIS:
        if p.get("sem_nota"):
            continue
        if p["id"] == "visao" and "vision" not in caps:
            continue
        v = (papeis_med.get(p["id"]) or {}).get("nota")
        if v is not None:
            vals.append(float(v))
    return round(sum(vals) / len(vals), 1) if vals else None


def _ctx_gpu_efetivo(m: dict) -> int:
    s = m.get("sonda") or {}
    if s.get("ctx_max_gpu"):
        return int(s["ctx_max_gpu"])
    q8 = (m.get("ctx_por_kv") or {}).get("q8_0") or {}
    if q8.get("ctx_max"):
        return int(q8["ctx_max"])
    return int(m.get("ctx_max") or 32768)


def indice_pratico(m: dict, papel_id: Optional[str] = None, vram_total_gb: float = 16.0) -> Optional[dict]:
    """Índice multicritério (0–100) combinando Conhecimento (58%), Velocidade (22%), Eficiência de Tamanho (10%) e Contexto GPU (10%)."""
    nota = _nota(m, papel_id) if papel_id else _media_geral(m)
    if nota is None:
        return None
    med = m.get("medido") or {}
    tps = med.get("tps_mediana")
    if not tps and m.get("tps_est"):
        tps = (m["tps_est"][0] + m["tps_est"][1]) / 2.0
    tps_val = float(tps or 25.0)
    # 10 tok/s -> 22, 30 tok/s -> 54, 53 tok/s -> 72, 83 tok/s -> 89, 96+ tok/s -> 96–100
    s_vel = min(100.0, max(10.0, 22.0 * math.log2(max(tps_val, 5.0) / 5.0) + 1.0))
    # Eficiência de tamanho: modelos mais enxutos deixam mais VRAM livre e carregam mais rápido
    peso_gb = (m.get("bytes") or 0) / GB
    frac_peso = peso_gb / max(vram_total_gb, 8.0)
    s_tam = min(100.0, max(20.0, 110.0 - 55.0 * frac_peso))
    # Contexto na GPU: 4k -> 20, 16k -> 46, 32k -> 60, 64k -> 73, 128k -> 86, 256k+ -> 100
    ctx_gpu = max(4096, _ctx_gpu_efetivo(m))
    s_ctx = min(100.0, max(20.0, 20.0 + 13.33 * math.log2(ctx_gpu / 4096.0)))
    if papel_id == "rapido":
        total = 0.50 * nota + 0.30 * s_vel + 0.12 * s_tam + 0.08 * s_ctx
    else:
        total = 0.64 * nota + 0.18 * s_vel + 0.09 * s_tam + 0.09 * s_ctx
    return {
        "total": round(total, 1),
        "conhecimento": round(nota, 1),
        "velocidade": round(s_vel, 0),
        "tamanho": round(s_tam, 0),
        "contexto": round(s_ctx, 0),
        "tps": round(tps_val, 1),
        "peso_gb": round(peso_gb, 1),
        "ctx_gpu": ctx_gpu,
    }


def _atende(m: dict, papel: dict) -> bool:
    caps = m.get("caps") or []
    return all(e in caps for e in papel.get("exige", []))


def titulares_sugeridos(instalados: List[dict], atuais: Dict[str, str]) -> Dict[str, dict]:
    """Melhor instalado por papel. Em empate técnico, desempata por índice prático (velocidade + tamanho + contexto) se a vantagem for clara."""
    res: Dict[str, dict] = {}
    for p in papeis.PAPEIS:
        if p.get("sem_nota"):
            cands = [m for m in instalados if _atende(m, p)]
            res[p["id"]] = {"modelo": cands[0]["id"] if cands else None, "nota": None, "motivo": "só indica quem tem a capacidade"}
            continue
        elegiveis = [m for m in instalados if _atende(m, p) and _nota(m, p["id"]) is not None]
        if p["id"] == "rapido":
            elegiveis = [m for m in elegiveis if m["bytes"] <= RAPIDO_MAX_GB * GB]
            if elegiveis and any((m.get("medido") or {}).get("tps_mediana") for m in elegiveis):
                elegiveis = [m for m in elegiveis if ((m.get("medido") or {}).get("tps_mediana") or 0) >= 40] or elegiveis
        if not elegiveis:
            if p["id"] == "visao":
                cands = [m for m in instalados if _atende(m, p)]
                res[p["id"]] = {"modelo": cands[0]["id"] if cands else None, "nota": None,
                                "motivo": "tem visão (rode a medição para ter nota)" if cands else "nenhum instalado tem visão"}
            else:
                res[p["id"]] = {"modelo": None, "nota": None, "motivo": "nenhum instalado e medido atende"}
            continue
        melhor = max(elegiveis, key=lambda m: (_nota(m, p["id"]), (indice_pratico(m, p["id"]) or {}).get("total", 0)))
        atual_id = atuais.get(p["id"])
        atual = next((m for m in elegiveis if m["id"] == atual_id), None)
        escolhido, motivo = melhor, "melhor nota medida"
        # Verifica se algum outro modelo empatado tecnicamente com o líder é muito mais rápido/eficiente (ex.: Gemma 26B vs Qwen 27B em raciocínio)
        for cand in elegiveis:
            if cand["id"] == melhor["id"]:
                continue
            cmp_c = resultados.comparar((melhor["id"], melhor["digest"]), (cand["id"], cand["digest"]), p["id"])
            if cmp_c and stats.veredito_pareado(cmp_c) == "empate":
                tps_m = (melhor.get("medido") or {}).get("tps_mediana") or 0
                tps_c = (cand.get("medido") or {}).get("tps_mediana") or 0
                ip_m = (indice_pratico(melhor, p["id"]) or {}).get("total", 0)
                ip_c = (indice_pratico(cand, p["id"]) or {}).get("total", 0)
                if tps_m > 0 and tps_c >= tps_m * 1.5 and ip_c > ip_m + 2.0 and atual_id != melhor["id"]:
                    escolhido = cand
                    motivo = f"empate técnico em conhecimento com {melhor['id']}, mas {round(tps_c / tps_m, 1)}× mais rápido ({round(tps_c)} vs {round(tps_m)} tok/s)"
                    break
        if atual and atual["id"] != escolhido["id"]:
            cmp = resultados.comparar((escolhido["id"], escolhido["digest"]), (atual["id"], atual["digest"]), p["id"])
            if cmp and stats.veredito_pareado(cmp) == "empate":
                tps_e = (escolhido.get("medido") or {}).get("tps_mediana") or 0
                tps_a = (atual.get("medido") or {}).get("tps_mediana") or 0
                if tps_a > 0 and tps_e >= tps_a * 1.8:
                    motivo = f"empate em nota com {atual['id']}, mas {round(tps_e / tps_a, 1)}× mais rápido ({round(tps_e)} vs {round(tps_a)} tok/s)"
                else:
                    escolhido, motivo = atual, f"empate técnico com {escolhido['id']} — mantido o atual"
        ip_esc = indice_pratico(escolhido, p["id"])
        res[p["id"]] = {"modelo": escolhido["id"], "nota": _nota(escolhido, p["id"]), "motivo": motivo,
                        "indice_pratico": ip_esc["total"] if ip_esc else None,
                        "ic": ((escolhido.get("medido") or {}).get("papeis", {}).get(p["id"]) or {}).get("ic")}
    return res


def titulares_atuais(inst: List[dict]) -> Tuple[Dict[str, str], Dict[str, dict]]:
    """(titular de cada função, sugestão por nota). O titular salvo só vale se o modelo ainda está instalado."""
    salvo = squad_salvo()
    ids = {m["id"] for m in inst}
    escolhidos = {pid: mid for pid, mid in salvo.get("titulares", {}).items() if mid in ids}
    sug = titulares_sugeridos(inst, escolhidos)
    return {pid: (escolhidos.get(pid) or sug[pid]["modelo"]) for pid in sug}, sug


_RANK_CACHE: Dict[tuple, dict] = {}


def ranking_por_papel(inst: List[dict], titulares: Dict[str, str]) -> Dict[str, List[dict]]:
    """Todos os instalados medidos, por função, do melhor ao pior — cada um com o veredito PAREADO contra o titular."""
    try:
        st = config.RESULTADOS.stat()
        chave = (st.st_mtime_ns, st.st_size, tuple(sorted(titulares.items())), tuple(sorted(m["id"] + m["digest"] for m in inst)))
    except OSError:
        return {}
    if chave in _RANK_CACHE:
        return _RANK_CACHE[chave]
    rows = resultados.carregar()
    por_id = {m["id"]: m for m in inst}
    out: Dict[str, List[dict]] = {}
    for p in papeis.PAPEIS:
        if p.get("sem_nota"):
            continue
        tit = por_id.get(titulares.get(p["id"]) or "")
        linhas = []
        for m in inst:
            r = ((m.get("medido") or {}).get("papeis") or {}).get(p["id"])
            if not r or r.get("nota") is None:
                continue
            vs = None
            if tit and tit["id"] != m["id"]:
                c = resultados.comparar((m["id"], m["digest"]), (tit["id"], tit["digest"]), p["id"], reps=500, rows=rows)
                vs = {"veredito": stats.veredito_pareado(c), "dif": c["dif"], "ic": c["ic"]} if c else None
            ip = indice_pratico(m, p["id"])
            linhas.append({"modelo": m["id"], "nota": r["nota"], "ic": r.get("ic"), "atende": _atende(m, p), "titular": bool(tit and tit["id"] == m["id"]),
                           "tps": (m.get("medido") or {}).get("tps_mediana"), "bytes": m["bytes"], "ctx_gpu": _ctx_gpu_efetivo(m),
                           "indice_pratico": ip["total"] if ip else None, "vs_titular": vs})
        out[p["id"]] = sorted(linhas, key=lambda x: (-x["nota"], -(x.get("indice_pratico") or 0)))
    _RANK_CACHE.clear()
    _RANK_CACHE[chave] = out
    return out


def dispensaveis(instalados: List[dict], ranking: Dict[str, List[dict]]) -> List[dict]:
    """Instalados que dá para substituir/apagar sem perder capacidade prática — avalia conhecimento, velocidade, tamanho e contexto."""
    if not instalados or any(not (m.get("medido") or {}).get("n_itens") for m in instalados):
        return []
    out = []
    por_id = {m["id"]: m for m in instalados}
    for m in instalados:
        piores: List[str] = []
        dominados: List[str] = []
        substitutos_id: Dict[str, int] = {}
        apagavel = True
        for pid, linhas in ranking.items():
            x = next((l for l in linhas if l["modelo"] == m["id"]), None)
            if not x or not x["atende"]:
                continue
            if pid == "rapido" and m["bytes"] > RAPIDO_MAX_GB * GB and not x["titular"]:
                continue
            nome = papeis.POR_ID[pid]["rotulo"]
            if x["titular"]:
                apagavel = False
                break
            vs = x.get("vs_titular")
            tit_linha = next((l for l in linhas if l.get("titular")), None)
            if vs and vs["veredito"] == "inferior":
                piores.append(nome)
                if tit_linha:
                    substitutos_id[tit_linha["modelo"]] = substitutos_id.get(tit_linha["modelo"], 0) + 1
                continue
            # Se empata tecnicamente com o titular, mas o titular é mais rápido ou menor/igual
            if vs and vs["veredito"] == "empate" and tit_linha:
                tps_x = x.get("tps") or 0
                tps_t = tit_linha.get("tps") or 0
                if (tit_linha["bytes"] <= x["bytes"] * 1.05 and tps_t >= tps_x) or (tps_x > 0 and tps_t >= tps_x * 1.35):
                    razao_vel = f"{round(tps_t / tps_x, 1)}× mais rápido ({round(tps_t)} vs {round(tps_x)} tok/s)" if (tps_x > 0 and tps_t >= tps_x * 1.35) else "menor e mais rápido"
                    dominados.append(f"em {nome} empata em nota com {tit_linha['modelo']}, que é {razao_vel}")
                    substitutos_id[tit_linha["modelo"]] = substitutos_id.get(tit_linha["modelo"], 0) + 1
                    continue
            dom = next((o for o in linhas if o["modelo"] != m["id"] and o["atende"]
                        and (o["nota"] >= x["nota"] - 3 or (o.get("titular") and vs and vs["veredito"] == "empate"))
                        and o["bytes"] <= x["bytes"] * 1.05
                        and (o.get("tps") or 0) >= (x.get("tps") or 0)
                        and not (o.get("vs_titular") or {}).get("veredito") == "inferior"), None)
            if dom:
                tps_x = x.get("tps") or 0
                tps_d = dom.get("tps") or 0
                det_dom = f"{round(tps_d / tps_x, 1)}× mais rápido" if (tps_x > 0 and tps_d >= tps_x * 1.35) else "menor e mais rápido"
                dominados.append(f"em {nome} é coberto por {dom['modelo']} ({det_dom})")
                substitutos_id[dom["modelo"]] = substitutos_id.get(dom["modelo"], 0) + 1
                continue
            apagavel = False
            break
        if apagavel and (piores or dominados):
            sub_principal = max(substitutos_id.items(), key=lambda kv: kv[1])[0] if substitutos_id else None
            sub_m = por_id.get(sub_principal) if sub_principal else None
            resumo_curto = ""
            if sub_m:
                tps_m = (m.get("medido") or {}).get("tps_mediana") or 0
                tps_s = (sub_m.get("medido") or {}).get("tps_mediana") or 0
                ctx_m = _ctx_gpu_efetivo(m) // 1024
                ctx_s = _ctx_gpu_efetivo(sub_m) // 1024
                ganhos = []
                if tps_m > 0 and tps_s >= tps_m * 1.25:
                    ganhos.append(f"{round(tps_s / tps_m, 1)}× mais rápido ({round(tps_s)} vs {round(tps_m)} tok/s)")
                if sub_m["bytes"] < m["bytes"] * 0.95:
                    ganhos.append(f"menor ({fmt_gb(sub_m['bytes'])} vs {fmt_gb(m['bytes'])})")
                if ctx_s > ctx_m:
                    ganhos.append(f"mais contexto GPU ({ctx_s}k vs {ctx_m}k)")
                resumo_curto = f"Substituído com vantagem por {sub_principal}" + (f": {', '.join(ganhos)}" if ganhos else "")
            partes = ([resumo_curto] if resumo_curto else []) + ([f"pior que o modelo atual em {len(piores)} uso(s)"] if piores else []) + sorted(set(dominados))[:2]
            out.append({
                "modelo": m["id"],
                "bytes": m["bytes"],
                "liberaria": fmt_gb(m["bytes"]),
                "tipo": "inferior",
                "substituto": sub_principal,
                "herdeiros": {},
                "motivo": " · ".join(partes),
            })
    ja = {d["modelo"] for d in out}
    for m in instalados:
        if m["id"] in ja:
            continue
        herdeiros: Dict[str, dict] = {}
        ok = True
        for pid, linhas in ranking.items():
            x = next((l for l in linhas if l["modelo"] == m["id"]), None)
            if not x or not x["atende"]:
                continue
            if pid == "rapido" and m["bytes"] > RAPIDO_MAX_GB * GB and not x["titular"]:
                continue
            if x["titular"]:
                h = _herdeiro(linhas, m, pid)
                if not h:
                    ok = False
                    break
                herdeiros[pid] = h
            else:
                vs = x.get("vs_titular")
                if vs and vs["veredito"] == "superior":
                    ok = False
                    break
        if ok and herdeiros:
            quem = "; ".join(f"em {papeis.POR_ID[pid]['rotulo']} quem assume é {h['modelo']} (empate técnico, {round(100 * (1 - h['bytes'] / m['bytes']))}% menor no disco)"
                             for pid, h in herdeiros.items())
            out.append({"modelo": m["id"], "bytes": m["bytes"], "liberaria": fmt_gb(m["bytes"]), "tipo": "custo",
                        "herdeiros": {pid: h["modelo"] for pid, h in herdeiros.items()},
                        "motivo": f"não vence com folga em nenhuma função e ocupa {fmt_gb(m['bytes'])}: {quem}"})
    return sorted(out, key=lambda x: -x["bytes"])


CUSTO_MIN_REDUCAO = 0.70


def _herdeiro(linhas: List[dict], m: dict, pid: str) -> Optional[dict]:
    """Quem assume uma função se `m` (o titular) sair: outro instalado ≥30% menor que NÃO é pior que ele (empate ou melhor)."""
    teto = m["bytes"] * CUSTO_MIN_REDUCAO
    if pid == "rapido":
        teto = min(teto, RAPIDO_MAX_GB * GB)
    pos = [o for o in linhas if o["modelo"] != m["id"] and o["atende"] and o["bytes"] <= teto
           and (o.get("vs_titular") or {}).get("veredito") in ("empate", "superior")]
    return max(pos, key=lambda o: o["nota"]) if pos else None


# ------------------------------------------------------------------ candidatos por máquina

def _instalado_como(c: dict, instalados: List[dict]) -> Optional[str]:
    pulls = {v["pull"] for v in c.get("variantes", [])}
    for m in instalados:
        if m["id"] in pulls or m["id"].replace("hf.co/", "") in {p.replace("hf.co/", "") for p in pulls}:
            return m["id"]
    return None


def candidatos_para(maq: dict, instalados: List[dict], snap: Optional[dict], papel_id: Optional[str] = None,
                    incluir_comunidade: bool = False, incluir_antigos: bool = False, limite: int = 12) -> List[dict]:
    cfg = config.carregar()
    if not snap:
        return []
    papeis_alvo = [papeis.POR_ID[papel_id]] if papel_id else [p for p in papeis.PAPEIS]
    vistos: Dict[str, dict] = {}
    for c in snap["candidatos"]:
        if c.get("confianca") == "comunidade" and not incluir_comunidade:
            continue
        if not incluir_antigos and (c.get("dias") or 0) > 270:
            continue
        if c.get("sem_gguf"):
            continue
        if c["origem"] == "hf" and (c.get("baixas") or 0) < 4000:
            continue
        if "decision" in (c.get("caps") or []):   # modelo de decisão: não conversa e não roda no Ollama (mesma regra de web/calc.js)
            continue
        for p in papeis_alvo:
            if c.get("especializado") and not (p["id"] == "visao" and c["especializado"] == "ocr"):
                continue
            if p["id"] not in c["papeis"]:
                continue
            if any(e not in (c.get("caps") or []) and c["origem"] == "ollama" for e in p.get("exige", [])):
                continue
            enc = encaixe_candidato(c, maq, p, cfg)
            if not enc or not enc.get("cabe"):
                continue
            # Categorias de porte por hardware: em máquinas com GPU dedicada potente (VRAM >= 8 GB, ex.: PC principal),
            # o papel 'rapido' tem como padrão de referência modelos na faixa de 3B–5B (ex.: Qwen 3.5 4B, 3.4 GB, 83 tok/s).
            # Modelos menores que 2.5B sofrem degradação severa em raciocínio/regras e não são desafiantes reais nesta GPU;
            # modelos ultra-leves (sub-2.5B) são direcionados para as outras máquinas do parque (notebook, Raspberry Pi).
            vram_maq = (maq.get("gpu") or {}).get("vram_gb", 0)
            if p["id"] == "rapido" and vram_maq >= 8:
                params = c.get("params_b") or 0
                peso_var = (enc.get("variante") or {}).get("bytes", 0)
                if params < 2.5 or (peso_var and peso_var < 1.8 * GB):
                    continue
            pri = prioridade(c, p, enc, instalados, maq)
            atual = vistos.get(c["id"])
            if atual is None or pri["pontos"] > atual["prioridade"]["pontos"]:
                vistos[c["id"]] = {"id": c["id"], "nome": c["nome"], "origem": c["origem"], "familia": c.get("familia"),
                                   "descricao": c.get("descricao", ""), "params_b": c["params_b"], "ativos_b": c.get("ativos_b"),
                                   "caps": c.get("caps", []), "dias": c.get("dias"), "lancamento": c.get("lancamento"),
                                   "novo": c.get("novo"), "licenca": c.get("licenca"), "url": c.get("url"),
                                   "confianca": c.get("confianca"), "papel": p["id"], "papeis": c["papeis"],
                                   "encaixe": enc, "prioridade": pri, "instalado_como": _instalado_como(c, instalados),
                                   "ctx_modelo": c.get("ctx_max"), "data_aproximada": c.get("data_aproximada"),
                                   "repo": c.get("repo"), "repo_gguf": c.get("repo_gguf")}
    lista = sorted(vistos.values(), key=lambda x: -x["prioridade"]["pontos"])
    return lista[:limite]


# ------------------------------------------------------------------ a mesa de decisão

def _fmt_tps(t: Optional[Tuple[float, float]]) -> str:
    if not t:
        return "?"
    lo, hi = t
    return f"{lo:g}–{hi:g}".replace(".", ",")


def mesa_de_decisao(oll: Optional[Ollama], com_broker: bool = False) -> dict:
    pk = parque.carregar_parque(com_broker)
    boss = parque.maquina_local(pk)
    snap = scout.ultimo()
    inst = modelos_do_boss(oll, boss)
    salvo = squad_salvo()
    atuais, sug = titulares_atuais(inst)
    desafiantes: Dict[str, List[dict]] = {}
    if boss and snap:
        for p in papeis.PAPEIS:
            lst = [x for x in candidatos_para(boss, inst, snap, p["id"], limite=6) if not x["instalado_como"]]
            desafiantes[p["id"]] = lst[:3]
    vs = vereditos()
    ranking = ranking_por_papel(inst, atuais)
    acoes = _acoes(inst, atuais, sug, desafiantes, vs, snap, ranking)
    kv = None
    for m in inst:
        pts = (m.get("sonda") or {}).get("pontos") or []
        k = fit.inferir_kv_tipo(m.get("arch") or {}, pts)
        if k:
            kv = {**k, "modelo": m["id"]}
            break
    return {
        "protocolo": PROTOCOLO, "ollama_no_ar": bool(oll and oll.no_ar()),
        "boss": boss, "maquinas_parque": len(pk.get("maquinas") or []),
        "reserva_vram_gb": float(config.carregar().get("reserva_vram_gb", 1.3)),
        "overhead_cuda_gb": 0.85,
        "instalados": inst, "titulares_sugeridos": sug, "titulares": atuais,
        "dispensaveis": dispensaveis(inst, ranking), "desafiantes": desafiantes, "vereditos": vs[-12:],
        "acoes": acoes, "manchete": _manchete(acoes, inst), "radar": _resumo_radar(snap), "kv_medido": kv, "alerta": _alerta(), "ritmo": ritmo_familias(snap, inst),
        "ranking": ranking, "papeis": papeis.PAPEIS, "suites": papeis.SUITES, "historico": salvo.get("historico", [])[-20:],
        "aposentados": aposentados.listar(inst),
    }


def ritmo_familias(snap: Optional[dict], inst: List[dict]) -> List[dict]:
    if not snap:
        return []
    usadas = {m["id"].split(":")[0].lower() for m in inst}
    prefixos = set()
    for u in usadas:
        mm = re.match(r"^([a-z]+(?:-[a-z]+)*?)-?\d", u)
        prefixos.add(mm.group(1) if mm else u)
    out = []
    for pref in sorted(prefixos):
        versoes: Dict[str, str] = {}
        for c in snap["candidatos"]:
            fam = (c.get("familia") or "").lower()
            if c["origem"] != "ollama" or c.get("data_aproximada") or not c.get("lancamento"):
                continue
            if not re.fullmatch(rf"{re.escape(pref)}-?\d+(\.\d+)?|{re.escape(pref)}", fam):
                continue
            atual = versoes.get(fam)
            if atual is None or c["lancamento"] < atual:
                versoes[fam] = c["lancamento"]
        if not versoes:
            continue
        ordem = sorted(versoes.items(), key=lambda kv: kv[1])
        datas = [dias_desde(d) for _, d in ordem]
        intervalos = [round(datas[i] - datas[i + 1]) for i in range(len(datas) - 1)]
        recentes = intervalos[-2:]
        medio = round(sum(recentes) / len(recentes)) if recentes else None
        desde = round(datas[-1] or 0)
        out.append({"familia": pref, "versoes": [{"nome": n, "lancamento": d[:10], "dias": round(dias_desde(d) or 0)} for n, d in ordem[-5:]],
                    "intervalo_medio_dias": medio, "dias_desde_a_ultima": desde,
                    "proxima_em_dias": max(0, medio - desde) if medio else None})
    return out


def _alerta() -> Optional[dict]:
    a = ler_json(config.ESTADO / "alertas.json")
    if not a or (dias_desde(a.get("em")) or 99) > 14:
        return None
    return {**a, "idade_dias": round(dias_desde(a.get("em")) or 0, 1)}


def _resumo_radar(snap: Optional[dict]) -> dict:
    if not snap:
        return {"existe": False}
    n = scout.novidades(snap)
    return {"existe": True, "criado": snap["criado"], "total": snap["total"], "fontes": snap["fontes"],
            "idade_dias": round(dias_desde(snap["criado"]) or 0, 1), "novidades": n, "embutido": bool(snap.get("embutido"))}


def _acoes(inst, atuais, sug, desafiantes, vs, snap, ranking) -> List[dict]:
    acoes: List[dict] = []
    sem = [m["id"] for m in inst if not (m.get("medido") or {}).get("n_itens")]
    if sem:
        acoes.append({"tipo": "medir", "prioridade": 1, "titulo": f"Medir {len(sem)} modelo(s) ainda sem nota no protocolo {PROTOCOLO}",
                      "detalhe": ", ".join(sem), "botao": "Rodar benchmark", "dados": {"modelos": sem}})
    for v in vs[-8:]:
        if v.get("pendente"):
            acoes.append({"tipo": "decidir", "prioridade": 0, "titulo": v["titulo"], "detalhe": v["resumo"],
                          "botao": "Ver veredito", "dados": {"veredito": v["id"]}})
    top = None
    for pid, lst in desafiantes.items():
        for x in lst:
            if x["prioridade"]["pontos"] >= LIMIAR_TESTAR and (top is None or x["prioridade"]["pontos"] > top["prioridade"]["pontos"]):
                top = x
    if top:
        acoes.append({"tipo": "testar", "prioridade": 2, "titulo": f"Vale testar {top['nome']} ({papeis.POR_ID[top['papel']]['rotulo']})",
                      "detalhe": f"Prioridade {top['prioridade']['pontos']}/100 · cabe com {top['encaixe']['variante']['quant']} ({fmt_gb(top['encaixe']['variante']['bytes'])}) · baixar só para testar",
                      "botao": "Testar contra o modelo atual", "dados": {"candidato": top["id"], "papel": top["papel"]}})
    disp = dispensaveis(inst, ranking)
    if disp:
        tot = sum(d["bytes"] for d in disp)
        acoes.append({"tipo": "limpar", "prioridade": 3, "titulo": f"{len(disp)} modelo(s) instalado(s) podem sair (inferiores ou dominados)",
                      "detalhe": ", ".join(d["modelo"] for d in disp) + f" · liberaria {fmt_gb(tot)}", "botao": "Ver detalhes", "dados": {}})
    if not snap:
        acoes.append({"tipo": "radar", "prioridade": 1, "titulo": "O radar de modelos nunca rodou",
                      "detalhe": "Faça a primeira varredura para descobrir o que existe hoje.", "botao": "Varrer agora", "dados": {}})
    elif (dias_desde(snap["criado"]) or 0) > 7:
        acoes.append({"tipo": "radar", "prioridade": 2, "titulo": f"Radar desatualizado ({int(dias_desde(snap['criado']))} dias)",
                      "detalhe": "Novos modelos podem ter saído.", "botao": "Varrer agora", "dados": {}})
    return sorted(acoes, key=lambda a: a["prioridade"])


def _manchete(acoes: List[dict], inst: List[dict]) -> dict:
    if not inst:
        return {"nivel": "aviso", "texto": "O Ollama está desligado ou sem modelos. Abra o Ollama e baixe um modelo para começar (o Radar mostra quais cabem aqui)."}
    tipos = {a["tipo"] for a in acoes}
    if "decidir" in tipos:
        return {"nivel": "acao", "texto": "Você tem um teste concluído esperando decisão."}
    if "medir" in tipos:
        n = len(next(a for a in acoes if a["tipo"] == "medir")["dados"]["modelos"])
        return {"nivel": "acao", "texto": f"Falta medir {n} modelo(s): sem isso os seus modelos ainda não têm nota confiável."}
    if "radar" in tipos:
        return {"nivel": "acao", "texto": "O radar de modelos precisa de uma varredura para saber o que existe hoje."}
    if "testar" in tipos:
        return {"nivel": "info", "texto": "Seus modelos estão medidos — e há um modelo novo que vale o teste."}
    return {"nivel": "ok", "texto": "Tudo em dia: modelos medidos, radar recente e nenhum modelo novo que valha o download agora."}


# ------------------------------------------------------------------ recomendações do parque inteiro

CLASSES_MAQUINA = [
    (None, "forte", "GPU com folga: roda modelos de 20–30B quantizados e o dia a dia inteiro."),
    (1.6, "mínima", "Cabe só modelo de ~1 GB ou menos: serve para classificação, extração simples e validação de formato. "
                    "Para qualidade, delegue ao boss."),
    (4.5, "leve", "Cabe modelo de 2–4B em Q4: bom para triagem, resumo curto e JSON; lento para conversa longa."),
    (9.0, "média", "Cabe modelo de até ~8B em Q4, mas em CPU de 2 núcleos a velocidade é de 1–5 tok/s: use em lote, não em chat."),
]


def classe_da_maquina(maq: dict) -> dict:
    if (maq.get("gpu") or {}).get("vram_gb"):
        return {"classe": "forte", "nota": CLASSES_MAQUINA[0][2]}
    orc = fit.orcamento_bytes(maq) / GB
    sem_vetor = not ({"avx", "avx2", "avx512", "neon"} & set(maq.get("simd") or []))
    if sem_vetor and orc < 4.5:
        return {"classe": "mínima", "nota": CLASSES_MAQUINA[1][2]}
    for teto, nome, nota in CLASSES_MAQUINA[1:]:
        if orc < teto:
            return {"classe": nome, "nota": nota}
    return {"classe": "média", "nota": CLASSES_MAQUINA[3][2]}


def recomendacoes_parque(snap: Optional[dict], oll: Optional[Ollama], por_maquina: int = 3, com_broker: bool = False,
                         pk: Optional[dict] = None) -> List[dict]:
    pk = pk or parque.carregar_parque(com_broker)
    inst = _instalados(oll)
    out = []
    for maq in pk["maquinas"]:
        entrada: Dict[str, Any] = {"maquina": maq, "papeis": {}, **classe_da_maquina(maq)}
        if not snap:
            out.append(entrada)
            continue
        base = [p for p in papeis.PAPEIS if p["id"] in ("chat_pt", "codigo", "regras", "rapido", "agente", "raciocinio")]
        cpu = not (maq.get("gpu") or {}).get("vram_gb")
        for p in base:
            if cpu and p["id"] in ("raciocinio",):
                continue
            lst = candidatos_para(maq, inst if maq.get("local") else [], snap, p["id"], incluir_antigos=cpu, limite=6)
            if cpu:
                lst = [x for x in lst if x["encaixe"].get("tps_est") and sum(x["encaixe"]["tps_est"]) / 2 >= 0.8]
            entrada["papeis"][p["id"]] = lst[:por_maquina]
        entrada["kit"] = _kit(entrada["papeis"], cpu)
        out.append(entrada)
    return out


def _kit(por_papel: Dict[str, List[dict]], cpu: bool) -> List[dict]:
    def topo(pid, excluir):
        for x in por_papel.get(pid) or []:
            if x["id"] not in excluir:
                return x
        return None
    kit, vistos = [], set()
    pedidos = [("chat_pt", "generalista: conversa, regras e agentes")]
    if not cpu:
        pedidos.append(("codigo", "programação e agente de código"))
    pedidos.append(("rapido", "tarefas rápidas em segundo plano" if not cpu else "bem mais leve que o generalista, para lotes e triagem"))
    for pid, motivo in pedidos:
        x = topo(pid, vistos)
        if cpu and pid == "rapido" and kit:
            teto = 0.6 * kit[0]["candidato"]["encaixe"]["variante"]["bytes"]
            x = next((c for c in (por_papel.get("rapido") or []) + (por_papel.get("regras") or [])
                      if c["id"] not in vistos and c["encaixe"]["variante"]["bytes"] <= teto), None)
        if x:
            vistos.add(x["id"])
            kit.append({"candidato": x, "para": motivo})
    return kit
