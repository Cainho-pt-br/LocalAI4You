"""Quanto de memória um modelo usa, se cabe numa máquina, e quão rápido deve rodar.

Tudo aqui é ESTIMATIVA — o painel rotula assim. A medição de verdade (sonda) vale mais e
sobrescreve a estimativa quando existe. As constantes de calibração estão no topo.
"""
from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from .util import GB, GIB

# bytes por elemento do cache de atenção
KV_BYTES = {"f16": 2.0, "q8_0": 1.0625, "q4_0": 0.5625}

# calibração (ver cerebro/fit-e-estimativas.md): overhead fixo do runtime CUDA + buffers de cálculo
OVERHEAD_FIXO_GB = 0.15
OVERHEAD_POR_CTX_GB = 0.000004    # buffers de cálculo crescem pouco com o contexto (calibrado em 5 modelos medidos)
ESTADO_LINEAR_GB = 0.10           # estado fixo das camadas de atenção linear (Gated DeltaNet etc.)

# eficiência da banda de memória na geração (calibrada nas medições da RTX 5060 Ti: 74–85% em modelos densos)
EFICIENCIA = {"gpu_denso": 0.78, "gpu_moe": 0.50, "cpu_avx512": 0.50, "cpu_avx2": 0.45, "cpu_avx": 0.40,
              "cpu_neon": 0.60, "cpu_sse": 0.25}   # CPU: ponto de partida (Pi 4 ≈ 4–5 tok/s num modelo de 0,7 GB); trocar por medição

MIN_BPW = 3.2   # abaixo disso o painel não recomenda (perda grande); prefira um modelo menor em Q4
CTX_DEGRAUS = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]


# ------------------------------------------------------------------ arquitetura

def arch_de_config_hf(cfg: dict) -> dict:
    """Converte o config.json do Hugging Face no mesmo formato de `ollama.extrair_arch`."""
    tc = cfg.get("text_config") or cfg
    camadas = tc.get("num_hidden_layers") or tc.get("n_layer") or tc.get("num_layers")
    heads = tc.get("num_attention_heads") or tc.get("n_head")
    kv = tc.get("num_key_value_heads") or tc.get("num_kv_heads") or heads
    hidden = tc.get("hidden_size") or tc.get("n_embd")
    hd = tc.get("head_dim") or (hidden // heads if hidden and heads else None)
    tipos = tc.get("layer_types")
    janela = tc.get("sliding_window")
    n_exp = tc.get("num_experts") or tc.get("n_routed_experts") or tc.get("num_local_experts")
    usados = tc.get("num_experts_per_tok") or tc.get("num_experts_per_token")
    return {
        "arquitetura": (cfg.get("model_type") or tc.get("model_type") or ""), "camadas": camadas, "kv_heads": kv,
        "key_len": hd, "val_len": hd, "intervalo_atencao_cheia": tc.get("full_attention_interval"),
        "janela": janela, "layer_types": tipos, "ctx_max": tc.get("max_position_embeddings"),
        # Gemma 4: camadas globais usam poucos cabeçalhos KV, K=V compartilhado e camadas que reaproveitam KV
        "kv_heads_global": tc.get("num_global_key_value_heads"), "head_dim_global": tc.get("global_head_dim"),
        "k_eq_v": bool(tc.get("attention_k_eq_v")), "kv_compartilhadas": tc.get("num_kv_shared_layers") or 0,
        "moe": bool(n_exp and n_exp > 1), "experts": n_exp, "experts_usados": usados,
        "tem_linear": bool(tipos and any("linear" in t or "ssm" in t or "mamba" in t for t in tipos)),
    }


def _camadas_por_tipo(arch: dict) -> Tuple[int, int, int]:
    """(cheias, janela_deslizante, lineares) — quantas camadas pagam KV cache e de que forma."""
    n = int(arch.get("camadas") or 0)
    tipos = arch.get("layer_types")
    if tipos:
        cheias = sum(1 for t in tipos if "full" in t)
        desliz = sum(1 for t in tipos if "sliding" in t or "local" in t)
        lineares = len(tipos) - cheias - desliz
        return cheias, desliz, max(lineares, 0)
    iv = arch.get("intervalo_atencao_cheia")
    if iv:  # Qwen3.5/3.8: a cada `iv` camadas uma é de atenção cheia, o resto é linear
        cheias = max(1, n // int(iv))
        return cheias, 0, n - cheias
    if arch.get("janela"):
        nome = (arch.get("arquitetura") or "").lower()
        frac = 1 / 6 if "gemma" in nome else 1 / 2  # gemma: 5 deslizantes p/ 1 cheia; gpt-oss: alterna
        cheias = max(1, round(n * frac))
        return cheias, n - cheias, 0
    return n, 0, 0


def kv_bytes(arch: dict, ctx: int, kv_tipo: str = "q8_0") -> int:
    if not arch or not arch.get("camadas") or not arch.get("kv_heads"):
        return 0
    cheias, desliz, lineares = _camadas_por_tipo(arch)
    b = KV_BYTES.get(kv_tipo, 1.0625)
    kl = arch.get("key_len") or 128
    vl = arch.get("val_len") or kl
    por_token = int(arch["kv_heads"]) * (kl + vl) * b
    if arch.get("kv_heads_global") and arch.get("head_dim_global"):
        por_token_cheia = int(arch["kv_heads_global"]) * int(arch["head_dim_global"]) * (1 if arch.get("k_eq_v") else 2) * b
    else:
        por_token_cheia = por_token
    desliz = max(0, desliz - int(arch.get("kv_compartilhadas") or 0))
    janela = int(arch.get("janela") or ctx)
    total = cheias * por_token_cheia * ctx + desliz * por_token * min(ctx, janela)
    if lineares:
        total += ESTADO_LINEAR_GB * GB
    return int(total)


def vram_total_bytes(peso_bytes: int, arch: dict, ctx: int, kv_tipo: str = "q8_0") -> int:
    return int(peso_bytes + kv_bytes(arch, ctx, kv_tipo) + (OVERHEAD_FIXO_GB + OVERHEAD_POR_CTX_GB * ctx) * GB)


# ------------------------------------------------------------------ quantização

_QUANT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:UD-)?(?:IQ\d_[A-Z]+|Q\d_K_[A-Z]+|Q\d_K|Q\d_\d|MXFP4(?:_MOE)?|NVFP4|BF16|F16|F32|Q\d))(?![A-Za-z0-9])")


def quant_de_nome(arquivo: str) -> Optional[str]:
    m = _QUANT_RE.search(arquivo.replace(".gguf", ""))
    return m.group(1).upper() if m else None


def bpw(bytes_arquivo: int, params_b: float) -> float:
    return (bytes_arquivo * 8) / (params_b * 1e9) if params_b else 0.0


def faixa_qualidade(b: float) -> Tuple[str, str]:
    """(rótulo curto, explicação) a partir de bits por peso. Qualitativo de propósito: não inventamos %."""
    if b >= 6.0:
        return "quase sem perda", "praticamente igual ao original; gasta memória à toa em máquina apertada"
    if b >= 4.5:
        return "excelente", "perda muito pequena; ótimo quando sobra memória"
    if b >= 3.9:
        return "ótima (padrão Q4)", "o ponto de equilíbrio mais usado: perda pequena com 1/4 do tamanho"
    if b >= 3.0:
        return "boa", "perda pequena; aceitável quando é o que cabe (comparar com um modelo menor em Q4)"
    if b >= 2.3:
        return "reduzida", "perda perceptível em lógica/código; só vale se nada melhor couber"
    return "degradada", "perda grande; prefira um modelo menor em Q4"


# ------------------------------------------------------------------ máquinas

RESERVA_PADRAO_GB = 1.3


def orcamento_bytes(maq: dict, reserva_vram_gb: float = 1.3) -> int:
    """Memória que um modelo pode ocupar na máquina (GPU se houver; senão RAM menos o que o SO precisa)."""
    gpu = maq.get("gpu")
    if gpu and gpu.get("vram_gb"):  # nvidia-smi informa MiB → o painel guarda GiB; arquivos de modelo são bytes
        return int(max(gpu["vram_gb"] - reserva_vram_gb, 0) * GIB)
    ram = float(maq.get("ram_gb") or 0)
    teto = maq.get("max_modelo_gb")
    reserva_so = float(maq.get("reserva_so_gb", 1.5))
    if abs(reserva_vram_gb - RESERVA_PADRAO_GB) > 1e-9:   # o usuário mexeu em "memória livre" no painel desta máquina: vale também sem GPU
        reserva_so = reserva_vram_gb
    livre = ram - reserva_so
    if teto:
        livre = min(livre, float(teto))
    return int(max(livre, 0) * GIB)


def ctx_maximo(peso: int, arch: dict, orcamento: int, kv_tipo: str, limite: Optional[int] = None) -> int:
    best = 0
    teto = min(limite or 10 ** 9, int(arch.get("ctx_max") or 1048576)) if arch else (limite or 32768)
    for c in CTX_DEGRAUS:
        if c > teto:
            break
        if vram_total_bytes(peso, arch or {}, c, kv_tipo) <= orcamento:
            best = c
    return best


def avaliar_encaixe(peso: int, arch: dict, maq: dict, ctx_alvo: int, kv_tipo: str = "q8_0",
                    reserva_vram_gb: float = 1.3) -> dict:
    """Veredito de memória: 'confortavel' (cabe no contexto alvo com 8% de folga), 'justo' (só em contexto
    menor) ou 'nao_cabe'. Devolve também o maior contexto que cabe."""
    orc = orcamento_bytes(maq, reserva_vram_gb)
    ctx_ok = ctx_maximo(peso, arch, orc, kv_tipo)
    usado = vram_total_bytes(peso, arch or {}, ctx_alvo, kv_tipo)
    if ctx_ok >= ctx_alvo and usado <= orc * 0.92:
        nivel = "confortavel"
    elif ctx_ok >= 4096:
        nivel = "justo"
    else:
        nivel = "nao_cabe"
    return {"nivel": nivel, "ctx_max": ctx_ok, "usado_ctx_alvo_gb": round(usado / GB, 2),
            "orcamento_gb": round(orc / GB, 2), "folga_gb": round((orc - usado) / GB, 2), "ctx_alvo": ctx_alvo}


def simd_da_maquina(maq: dict) -> str:
    s = set((maq.get("simd") or []))
    if "avx512" in s:
        return "cpu_avx512"
    if "avx2" in s:
        return "cpu_avx2"
    if "avx" in s:
        return "cpu_avx"
    if "neon" in s:
        return "cpu_neon"
    return "cpu_sse"


def estimar_tps(peso_ativo_bytes: int, maq: dict, moe: bool = False) -> Optional[Tuple[float, float]]:
    """Faixa (mín, máx) de tokens/s na geração: banda de memória ÷ bytes lidos por token × eficiência."""
    if peso_ativo_bytes <= 0:
        return None
    gpu = maq.get("gpu")
    if gpu and gpu.get("bw_gbs"):
        bw_lo = bw_hi = float(gpu["bw_gbs"])
        ef = EFICIENCIA["gpu_moe" if moe else "gpu_denso"]
    else:
        bw_lo = float(maq.get("bw_gbs_min") or maq.get("bw_gbs") or 0)
        bw_hi = float(maq.get("bw_gbs_max") or maq.get("bw_gbs") or bw_lo)
        if not bw_lo:
            return None
        ef = EFICIENCIA[simd_da_maquina(maq)] * (0.8 if moe else 1.0)
    lo = ef * 0.75 * bw_lo * 1e9 / peso_ativo_bytes
    hi = ef * 1.2 * bw_hi * 1e9 / peso_ativo_bytes
    return round(lo, 1), round(hi, 1)


def peso_ativo(peso_bytes: int, params_b: Optional[float], ativos_b: Optional[float]) -> int:
    if params_b and ativos_b and ativos_b < params_b:
        # embeddings e atenção não são "especialistas": ~12% do modelo sempre é lido
        return int(peso_bytes * min(1.0, ativos_b / params_b + 0.04))
    return peso_bytes


def ativos_de_nome(nome: str) -> Optional[float]:
    """'Qwen3-30B-A3B' → 3.0 ; 'gemma-4-26B-A4B' → 4.0."""
    m = re.search(r"(?i)[-_ .]a(\d+(?:\.\d+)?)b(?![a-z])", nome)
    return float(m.group(1)) if m else None


def escolher_variante(variantes: List[dict], maq: dict, arch: dict, ctx_alvo: int, params_b: float,
                      kv_tipo: str = "q8_0", reserva_vram_gb: float = 1.3,
                      ativos_b: Optional[float] = None) -> Optional[dict]:
    """Escolhe a quantização: a de maior qualidade que cabe confortável; senão a maior que cabe justo.

    GPU: sobe até ~6,6 bpw (acima disso é memória desperdiçada). CPU: sobe até ~5 bpw, porque a
    velocidade cai na proporção do tamanho e o gargalo é a banda de memória.
    """
    gpu = bool((maq.get("gpu") or {}).get("vram_gb"))
    teto_bpw = 6.7 if gpu else 5.0
    avaliadas = []
    for v in variantes:
        b = bpw(v["bytes"], params_b)
        enc = avaliar_encaixe(v["bytes"] + int(v.get("extra_bytes", 0)), arch, maq, ctx_alvo, kv_tipo, reserva_vram_gb)
        avaliadas.append({**v, "bpw": round(b, 2), "encaixe": enc})
    cabem = [a for a in avaliadas if a["encaixe"]["nivel"] != "nao_cabe"]
    conf = [a for a in cabem if a["encaixe"]["nivel"] == "confortavel"]
    # 1) melhor qualidade que cabe confortável dentro da faixa [3,2 ; teto]
    faixa = [a for a in conf if MIN_BPW <= a["bpw"] <= teto_bpw]
    if faixa:
        return max(faixa, key=lambda a: a["bpw"])
    # 2) o modelo só existe acima do teto (ex.: só BF16 de um modelo minúsculo): a menor variante confortável
    acima = [a for a in conf if a["bpw"] > teto_bpw]
    if acima and not any(a["bpw"] <= teto_bpw for a in avaliadas):
        return min(acima, key=lambda a: a["bpw"])
    # 3) cabe, mas só justo: a maior qualidade que cabe, sem cair abaixo do mínimo aceitável
    justas = [a for a in cabem if a["bpw"] >= MIN_BPW and a["bpw"] <= teto_bpw]
    return max(justas, key=lambda a: a["bpw"]) if justas else None


def potencia_de_dois_abaixo(n: int) -> int:
    return 2 ** int(math.log2(n)) if n > 0 else 0


def inferir_kv_tipo(arch: dict, pontos: List[dict]) -> Optional[dict]:
    """Descobre que tipo de cache de contexto o servidor Ollama está usando (f16 / q8_0 / q4_0) comparando o
    quanto a memória MEDIDA cresce entre dois contextos com o que cada tipo prevê. Responde, com dado, à dúvida
    "meu contexto está mesmo quantizado?" — a variável OLLAMA_KV_CACHE_TYPE só vale para o servidor que a recebeu."""
    ok = sorted([p for p in pontos if p.get("total_bytes")], key=lambda p: p["ctx"])
    if len(ok) < 2 or not arch or not arch.get("camadas"):
        return None
    a, b = ok[0], ok[-1]
    medido = b["total_bytes"] - a["total_bytes"]
    previsto = {t: kv_bytes(arch, b["ctx"], t) - kv_bytes(arch, a["ctx"], t) for t in KV_BYTES}
    if previsto["f16"] < 1.5 * GB or medido <= 0:
        return None  # crescimento pequeno demais para distinguir (modelo de atenção linear/janela)
    erro = {t: abs(medido - v) / medido for t, v in previsto.items()}
    melhor = min(erro, key=erro.get)
    if erro[melhor] > 0.15:
        return None  # nenhum tipo explica a medição: não chuta
    return {"tipo": melhor, "erro_rel": round(erro[melhor], 2), "medido_gb": round(medido / GB, 2),
            "previsto_gb": {t: round(v / GB, 2) for t, v in previsto.items()}}
