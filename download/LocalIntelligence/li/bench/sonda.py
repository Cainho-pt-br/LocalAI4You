"""Sonda de memória e velocidade: mede (não estima) quanto o modelo ocupa e quão rápido roda por contexto.

É o dado que mais pesa na decisão "cabe na minha placa?". Salvo por digest do modelo, então uma
atualização da tag no Ollama invalida a medição sozinha.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .. import config
from .. import fit
from ..ollama import Cancelado, ErroOllama, Ollama
from ..util import GB, SEM_JANELA, agora_iso, gravar_json, ler_json

_TEXTO = ("O rato roeu a roupa do rei de Roma e a rainha, com raiva, resolveu escrever uma carta longa "
          "sobre economia, agricultura, música e história natural. ")


def degraus_sonda(m: dict, vram_gb: float = 16.0, ate_ctx: Optional[int] = None, cpu: bool = False, kv_tipo: str = "q8_0") -> List[int]:
    """Escolhe os degraus de contexto a sondar de acordo com o tamanho do modelo e a VRAM da GPU.
    Respeita o teto nativo do GGUF (pois o Ollama trava num_ctx no context_length nativo do modelo)."""
    teto_nativo = int(m.get("ctx_max") or (m.get("arch") or {}).get("ctx_max") or 262144)
    teto_modelo = min(teto_nativo, int(ate_ctx)) if ate_ctx else teto_nativo
    peso_gb = float(m.get("bytes") or 0) / GB
    if cpu:
        # Sem GPU o limite é a RAM: vale todo degrau que o encaixe (o MESMO cálculo do radar) diz que cabe em 90% da memória
        # do modelo, até 32k (64k se pedido). O prompt de enchimento é curto (ver `enchimento_max`), então contexto maior
        # custa memória, não minutos.
        cabe = fit.ctx_maximo(int(m.get("bytes") or 0), m.get("arch") or {}, int(vram_gb * 0.90 * fit.GIB), kv_tipo)
        teto_cpu = min(teto_modelo, ate_ctx or 32768, cabe)
        return [c for c in fit.CTX_DEGRAUS if 4096 <= c <= teto_cpu] or [4096]
    alvos = [4096, 16384, 32768]
    # Se o peso do modelo deixa margem na placa (ex.: <= 12.8 GB numa GPU de 16 GB), testa 64k
    if (ate_ctx and ate_ctx >= 65536) or (vram_gb > 0 and peso_gb <= vram_gb * 0.80):
        alvos.append(65536)
    # Se o modelo é intermediário/leve (ex.: <= 9.6 GB numa GPU de 16 GB), testa também 128k
    if (ate_ctx and ate_ctx >= 131072) or (vram_gb > 0 and peso_gb <= vram_gb * 0.62):
        alvos.append(131072)
    # Se o modelo suporta ou foi pedido até 256k e tem porte viável, testa também 256k
    if (ate_ctx and ate_ctx >= 262144) or (vram_gb > 0 and peso_gb <= vram_gb * 0.45):
        alvos.append(262144)
    # Se o modelo suporta ou foi pedido até 512k (524288)
    if (ate_ctx and ate_ctx >= 524288) or (vram_gb > 0 and peso_gb <= vram_gb * 0.32):
        alvos.append(524288)
    # Se o modelo suporta ou foi pedido até 1M (1048576)
    if (ate_ctx and ate_ctx >= 1048576) or (vram_gb > 0 and peso_gb <= vram_gb * 0.22):
        alvos.append(1048576)
    degraus = sorted({min(c, teto_modelo) for c in alvos if c <= teto_modelo or c == 4096})
    return degraus or [4096]


def _prompt_com_aprox_tokens(n_tokens: int) -> str:
    # ~1,6 tokens por palavra em português para a maioria dos tokenizadores; é só um enchimento
    palavras = max(int(n_tokens / 1.6), 8)
    base = _TEXTO.split()
    texto = " ".join((base * (palavras // len(base) + 1))[:palavras])
    return texto + "\n\nResuma o texto acima em uma frase."


def info_vram_fisica() -> Optional[dict]:
    """Lê a VRAM física real diretamente da GPU dedicada (nvidia-smi ou sysfs).
    Retorna total_mb, usada_mb, livre_mb em MiB exatamente como o Gerenciador de Tarefas do Windows."""
    try:
        if shutil.which("nvidia-smi"):
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
                text=True, timeout=3, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA
            ).strip().splitlines()[0]
            tot, usd, fre = [float(x.strip()) for x in out.split(",")]
            return {"total_mb": tot, "usada_mb": usd, "livre_mb": fre}
    except Exception:
        pass
    try:
        for p in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
            tot_b = int(p.read_text().strip())
            usd_p = p.parent / "mem_info_vram_used"
            usd_b = int(usd_p.read_text().strip()) if usd_p.exists() else 0
            return {"total_mb": tot_b / (1024 * 1024), "usada_mb": usd_b / (1024 * 1024),
                    "livre_mb": max(0, tot_b - usd_b) / (1024 * 1024)}
    except Exception:
        pass
    return None


def _linha_ps(oll: Ollama, modelo: str) -> Optional[dict]:
    for m in oll.ps():
        if m.get("name") == modelo or m.get("model") == modelo:
            return m
    return None


def sondar_modelo(oll: Ollama, modelo: str, digest: str, ctxs: List[int],
                  ao_progredir: Optional[Callable[..., None]] = None,
                  passo_inicial: int = 0, total_passos: Optional[int] = None,
                  cancelar: Optional[threading.Event] = None, enchimento_max: int = 8192, cpu: bool = False) -> Dict[str, dict]:
    """Mede, para cada contexto: VRAM usada real na GPU, se está 100% na GPU, tokens/s de geração e de leitura."""
    resultado: Dict[str, dict] = {}
    tot = max(1, total_passos or len(ctxs))

    def _prog(msg: str, feito: float):
        if not ao_progredir:
            return
        pct = round(100.0 * min(tot, feito) / tot, 1)
        try:
            ao_progredir(msg=msg, feitos=feito, total=tot, pct=pct)
        except TypeError:
            try:
                ao_progredir(msg)
            except Exception:
                pass

    if cancelar is not None:
        oll.cancelar = cancelar
    oll.descarregar(modelo)
    time.sleep(0.8)
    base_gpu = info_vram_fisica()
    base_usada_bytes = int(base_gpu["usada_mb"] * 1024 * 1024) if base_gpu else 0

    for i, ctx in enumerate(sorted(ctxs)):
        if cancelar is not None and cancelar.is_set():
            break
        idx = passo_inicial + i
        ctx_k = f"{ctx // 1024}k" if ctx >= 1024 else str(ctx)
        _prog(f"{modelo}: preparando contexto {ctx_k} ({ctx})", idx)

        oll.descarregar(modelo)
        time.sleep(0.6)
        try:  # aquecimento: a 1ª chamada após carregar inclui compilação de kernels CUDA e mente sobre tokens/s
            oll.chat(modelo, [{"role": "user", "content": "OK"}], ctx=ctx, max_tokens=4, think=False, keep_alive="2m", timeout=900)
            oll.chat(modelo, [{"role": "user", "content": "Conte de 1 a 40, separado por vírgulas."}], ctx=ctx,
                     max_tokens=96, think=False, keep_alive="2m", timeout=900)
        except Cancelado:
            break
        except ErroOllama as e:
            resultado[str(ctx)] = {"ok": False, "erro": str(e)[:200], "em": agora_iso()}
            break

        _prog(f"{modelo}: medindo geração e leitura em {ctx_k}…", idx + 0.5)
        enchimento = min(int(ctx * 0.55), enchimento_max) if ctx <= 16384 else enchimento_max  # contexto cheio não é preciso para medir alocação do KV cache no Ollama
        try:
            r = oll.chat(modelo, [{"role": "user", "content": _prompt_com_aprox_tokens(enchimento)}],
                         ctx=ctx, max_tokens=48, think=False, keep_alive="2m", timeout=900)
        except Cancelado:
            break
        except ErroOllama as e:
            resultado[str(ctx)] = {"ok": False, "erro": str(e)[:200], "em": agora_iso()}
            break

        linha = _linha_ps(oll, modelo) or {}
        ctx_rep = int(linha.get("context_length") or 0)
        if ctx_rep > 0 and ctx_rep < int(ctx * 0.9):
            # O Ollama travou o contexto no teto nativo do GGUF (ex.: pediu 512k mas o modelo só aceita 256k)
            resultado[str(ctx)] = {
                "ok": False, "clamped": True, "ctx_reportado": ctx_rep,
                "erro": f"Teto nativo do modelo atingido ({ctx_rep // 1024}k tokens)",
                "em": agora_iso(),
            }
            _prog(f"{modelo}: teto nativo {ctx_rep // 1024}k atingido", idx + 1.0)
            break

        tam, vram = int(linha.get("size", 0)), int(linha.get("size_vram", 0))
        ev, ed = int(r.get("eval_count", 0)), int(r.get("eval_duration", 0))
        pe, pd = int(r.get("prompt_eval_count", 0)), int(r.get("prompt_eval_duration", 0))
        tps_med = round(ev / (ed / 1e9), 1) if ev and ed else None
        leitura_med = round(pe / (pd / 1e9), 1) if pe and pd else None
        gpu_integral = True if cpu else bool(tam and vram >= tam)   # CPU: não há GPU a vazar; os degraus já respeitam a RAM

        # Medição física da GPU no hardware (idêntico ao Gerenciador de Tarefas do Windows)
        gpu_agora = info_vram_fisica()
        vram_gpu_real_b = int(gpu_agora["usada_mb"] * 1024 * 1024) if gpu_agora else None
        vram_gpu_livre_b = int(gpu_agora["livre_mb"] * 1024 * 1024) if gpu_agora else None
        vram_modelo_b = max(0, vram_gpu_real_b - base_usada_bytes) if vram_gpu_real_b is not None else None

        # Detecção de Shared GPU Memory (WDDM do Windows): quando a placa enche (< 680 MB livres),
        # ou o total físico atinge/passa o limite da placa (>= 15.90 GB ou >= 98.5% da VRAM), ou a velocidade despenca
        ram_wddm = False
        p4k = resultado.get("4096") or {}
        tps_4k = p4k.get("tps")
        leit_4k = p4k.get("leitura_tps")
        if gpu_integral and ctx > 4096:
            pouca_folga = vram_gpu_livre_b is not None and vram_gpu_livre_b < 680 * 1024 * 1024
            tot_limite_b = (gpu_agora["total_mb"] * 1024 * 1024 * 0.985) if (gpu_agora and gpu_agora.get("total_mb")) else (15.90 * 1e9)
            estourou_capacidade = bool(vram_gpu_real_b and vram_gpu_real_b >= tot_limite_b)
            saturacao_critica = bool(vram_gpu_real_b and vram_gpu_real_b >= (tot_limite_b * 0.98) and pouca_folga)
            queda_tps = bool(tps_4k and tps_med and tps_med < tps_4k * 0.56)
            queda_leit = bool(leit_4k and leitura_med and leitura_med < leit_4k * 0.30)
            despencou_abs = bool(tps_4k and tps_4k >= 25 and tps_med and tps_med <= 14)
            if estourou_capacidade or saturacao_critica or despencou_abs or (pouca_folga and (queda_tps or queda_leit)) or (queda_tps and queda_leit):
                gpu_integral = False
                ram_wddm = True

        resultado[str(ctx)] = {
            "ok": True, "total_bytes": tam, "vram_bytes": vram,
            "vram_gpu_real_bytes": vram_gpu_real_b,
            "vram_gpu_livre_bytes": vram_gpu_livre_b,
            "vram_sistema_bytes": base_usada_bytes,
            "vram_modelo_bytes": vram_modelo_b,
            "gpu_integral": gpu_integral,
            "ram_wddm": ram_wddm,
            "pct_gpu": round(100 * vram / tam, 1) if tam else None,
            "tps": tps_med,   # geração com ~55% do contexto preenchido
            "leitura_tps": leitura_med,
            "prompt_tokens": pe, "ctx_reportado": ctx_rep or linha.get("context_length"), "em": agora_iso(),
        }
        _prog(f"{modelo}: concluído contexto {ctx_k}", idx + 1.0)
        # Se neste contexto já vazou para a RAM do sistema, não força contextos maiores (evita travar a máquina em 64k/128k na RAM)
        if not gpu_integral and ctx >= 16384:
            break
    oll.cancelar = None   # o descarregar final precisa passar mesmo depois de um cancelamento
    oll.descarregar(modelo)
    return resultado


def carregar() -> dict:
    return ler_json(config.SONDAS, {}) or {}


def salvar_modelo(modelo: str, digest: str, dados: Dict[str, dict], kv_tipo: str = "q8_0") -> None:
    todas = carregar()
    atual = todas.get(modelo, {})
    if atual.get("digest") != digest:
        atual = {"digest": digest, "ctx": {}, "ctx_kv": {}}
    atual.setdefault("ctx", {})
    atual.setdefault("ctx_kv", {})
    atual["ctx_kv"].setdefault(kv_tipo, {})
    atual["ctx_kv"][kv_tipo].update(dados)
    if kv_tipo == "q8_0" or not atual["ctx"]:
        atual["ctx"].update(dados)
    atual["atualizado"] = agora_iso()
    todas[modelo] = atual
    gravar_json(config.SONDAS, todas)


def _resumir_mapa_ctx(mapa: dict, digest: Optional[str]) -> dict:
    pontos = []
    teto_clamped = None
    p4k = (mapa or {}).get("4096") or {}
    tps_4k = p4k.get("tps")
    leit_4k = p4k.get("leitura_tps")
    for c, v in (mapa or {}).items():
        ctx_num = int(c)
        ctx_rep = int(v.get("ctx_reportado") or 0)
        if v.get("clamped") or (ctx_rep > 0 and ctx_rep < int(ctx_num * 0.9)):
            teto_clamped = ctx_rep or teto_clamped
            continue
        if v.get("ok"):
            pt = {"ctx": ctx_num, **v}
            if pt.get("gpu_integral") and ctx_num > 4096:
                livre_b = pt.get("vram_gpu_livre_bytes")
                total_real_b = pt.get("vram_gpu_real_bytes")
                tps_m = pt.get("tps")
                leit_m = pt.get("leitura_tps")
                pouca_folga = livre_b is not None and livre_b < 680 * 1024 * 1024
                # Estouro de capacidade física na GPU (ex.: >= 15.90 GB em placa de 16 GB)
                estourou_capacidade = bool(total_real_b and total_real_b >= 15.90 * 1e9)
                saturacao_critica = bool(total_real_b and total_real_b >= 15.65 * 1e9 and pouca_folga)
                queda_tps = bool(tps_4k and tps_m and tps_m < tps_4k * 0.56)
                queda_leit = bool(leit_4k and leit_m and leit_m < leit_4k * 0.30)
                despencou_abs = bool(tps_4k and tps_4k >= 25 and tps_m and tps_m <= 14)
                if estourou_capacidade or saturacao_critica or despencou_abs or (pouca_folga and (queda_tps or queda_leit)) or (queda_tps and queda_leit):
                    pt["gpu_integral"] = False
                    pt["ram_wddm"] = True
            pontos.append(pt)
        elif v.get("erro"):
            # Se falhou na sonda sem ser clamped (ex.: timeout/OOM por estourar a VRAM em 128k/256k), registra o estouro
            pontos.append({
                "ctx": ctx_num, "ok": False, "gpu_integral": False,
                "estourou_ram": True, "erro": v.get("erro"), "em": v.get("em")
            })
    if not pontos:
        return {"pontos": [], "ctx_max_gpu": 0, "ctx_max_testado": 0, "tps_base": None, "digest": digest, "teto_nativo": teto_clamped}
    pontos.sort(key=lambda p: p["ctx"])
    gpu_ok = [p for p in pontos if p.get("gpu_integral")]
    return {"pontos": pontos, "ctx_max_gpu": max((p["ctx"] for p in gpu_ok), default=0),
            "ctx_max_testado": max((p["ctx"] for p in pontos), default=0),
            "tps_base": (gpu_ok[0] if gpu_ok else pontos[0]).get("tps"), "digest": digest, "teto_nativo": teto_clamped}


def da_sonda(modelo: str, digest: Optional[str] = None) -> Optional[dict]:
    """Resumo útil: maior contexto medido 100% na GPU e a velocidade nele, mais detalhamento por KV cache."""
    d = carregar().get(modelo)
    if not d or (digest and d.get("digest") != digest):
        return None
    base = _resumir_mapa_ctx(d.get("ctx") or {}, d.get("digest"))
    por_kv = {}
    ctx_kv_raw = d.get("ctx_kv") or {}
    if "q8_0" not in ctx_kv_raw and d.get("ctx"):
        por_kv["q8_0"] = base
    for kvt, mapa in ctx_kv_raw.items():
        por_kv[kvt] = _resumir_mapa_ctx(mapa, d.get("digest"))
    return {**base, "por_kv": por_kv}
