"""Perfil de hardware do parque: estático (parque.json) + inventário ao vivo do broker + detecção local universal.

O broker é só lido (GET). Se estiver fora do ar, o painel segue com o perfil estático ou auto-detectado e diz isso.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from .util import SEM_JANELA, http_json, ler_json

_CACHE_BROKER: Dict[str, Any] = {}


def _nvidia() -> Optional[dict]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"],
            text=True, timeout=6, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA).strip().splitlines()[0]
        nome, total, livre, drv = [p.strip() for p in out.split(",")]
        return {"nome": nome, "vram_gb": round(int(total) / 1024, 1), "vram_livre_gb": round(int(livre) / 1024, 1), "driver": drv}
    except Exception:
        return None


def _bw_catalogo(nome_gpu: str, padrao: int = 320) -> int:
    """Cruza o nome detectado da GPU com data/hardware.json para estimar a banda (GB/s)."""
    try:
        hw = ler_json(config.HARDWARE_ARQ, {}) or {}
        n = nome_gpu.lower()
        for item in (hw.get("gpus", []) + hw.get("unificadas", [])):
            inome = item.get("nome", "").lower()
            if inome and (inome in n or n in inome):
                return int(item.get("bw_gbs", padrao))
    except Exception:
        pass
    return padrao


def _gpu_alternativa() -> Optional[dict]:
    """Detecta GPUs AMD/Intel (Windows via winreg / Linux via sysfs) ou Apple Silicon (macOS) sem depender de nvidia-smi."""
    try:
        if platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"):
            ram = _ram_local_gb() or 16.0
            chip = _cpu_nome()
            frac = 0.67 if ram <= 36 else 0.75
            vram = round(ram * frac, 1)
            return {"nome": chip, "vram_gb": vram, "vram_livre_gb": round(max(vram - 2.0, 1.0), 1),
                    "driver": "Metal", "bw_gbs": _bw_catalogo(chip, 200), "unificada": True, "alternativa": True}
        if os.name == "nt":
            import winreg
            chave_cls = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            melhor = None
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave_cls) as base:
                for i in range(16):
                    try:
                        with winreg.OpenKey(base, f"{i:04d}") as sk:
                            nome = str(winreg.QueryValueEx(sk, "DriverDesc")[0]).strip()
                            if any(x in nome.lower() for x in ("basic", "virtual", "parsec", "remote")):
                                continue
                            vram_b = 0
                            for campo in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                                try:
                                    val, _ = winreg.QueryValueEx(sk, campo)
                                    vram_b = int.from_bytes(val, "little") if isinstance(val, bytes) else int(val)
                                    if vram_b > 0:
                                        break
                                except Exception:
                                    continue
                            if vram_b >= 3_500_000_000:
                                vram = round(vram_b / 1024 ** 3, 1)
                                drv = ""
                                try:
                                    drv = str(winreg.QueryValueEx(sk, "DriverVersion")[0])
                                except Exception:
                                    pass
                                cand = {"nome": nome, "vram_gb": vram, "vram_livre_gb": round(max(vram - 1.3, 1.0), 1),
                                        "driver": drv, "bw_gbs": _bw_catalogo(nome, 320), "alternativa": True}
                                if not melhor or cand["vram_gb"] > melhor["vram_gb"]:
                                    melhor = cand
                    except OSError:
                        continue
            if melhor:
                return melhor
        else:
            for p in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
                total_b = int(p.read_text().strip())
                if total_b >= 3_500_000_000:
                    usado_p = p.parent / "mem_info_vram_used"
                    usado_b = int(usado_p.read_text().strip()) if usado_p.exists() else 0
                    vram = round(total_b / 1024 ** 3, 1)
                    livre = round(max((total_b - usado_b) / 1024 ** 3, 0.5), 1)
                    return {"nome": "GPU dedicada (DRM)", "vram_gb": vram, "vram_livre_gb": livre,
                            "driver": "drm", "bw_gbs": 320, "alternativa": True}
    except Exception:
        pass
    return None


def _gpu_local() -> Optional[dict]:
    g = _nvidia()
    if g:
        g.setdefault("bw_gbs", _bw_catalogo(g["nome"], 448))
        return g
    return _gpu_alternativa()


def _simd_local() -> List[str]:
    simd: List[str] = []
    try:
        if os.name == "nt":
            k = ctypes.windll.kernel32.IsProcessorFeaturePresent
            if k(10):
                simd.append("sse")  # PF_XMMI64_INSTRUCTIONS_AVAILABLE
            if k(39):
                simd.append("avx")
            if k(40):
                simd.append("avx2")
            if k(41):
                simd.append("avx512")
        else:
            flags = Path("/proc/cpuinfo").read_text()
            for f in ("avx512f", "avx2", "avx", "sse4_2", "neon", "asimd"):
                if re.search(rf"\b{f}\b", flags):
                    simd.append({"avx512f": "avx512", "sse4_2": "sse", "asimd": "neon"}.get(f, f))
    except Exception:
        pass
    return sorted(set(simd), key=["sse", "neon", "avx", "avx2", "avx512"].index)


def _ram_local_gb() -> Optional[float]:
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            return round(ms.ullTotalPhys / 1024 ** 3, 1)
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3).strip()
            return round(int(out) / 1024 ** 3, 1)
        for ln in Path("/proc/meminfo").read_text().splitlines():
            if ln.startswith("MemTotal"):
                return round(int(ln.split()[1]) / 1024 ** 2, 1)
    except Exception:
        pass
    return None


def medir_banda_memoria_gbs(mb: int = 192, repeticoes: int = 4) -> Optional[float]:
    """Banda de cópia de memória medida (GB/s) — só stdlib. Subestima um pouco (cópia lê+escreve), mas
    é a mesma régua em qualquer máquina do parque: rode este arquivo nelas para trocar a estimativa por medida."""
    import time
    try:
        a = bytearray(mb * 1024 * 1024)
        melhor = 0.0
        for _ in range(repeticoes):
            t0 = time.perf_counter()
            b = bytes(a)  # lê mb e escreve mb
            dt = time.perf_counter() - t0
            melhor = max(melhor, (2 * mb / 1024) / dt)
            del b
        return round(melhor, 1)
    except Exception:
        return None


def _cpu_nome() -> str:
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return " ".join(winreg.QueryValueEx(k, "ProcessorNameString")[0].split())
        if platform.system() == "Darwin":
            return subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=3).strip()
        for ln in Path("/proc/cpuinfo").read_text().splitlines():
            if ln.lower().startswith(("model name", "hardware")):
                return ln.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


def detectar_local() -> dict:
    gpu = _gpu_local()
    return {
        "hostname": platform.node(),
        "so": f"{platform.system()} {platform.release()}",
        "cpu": _cpu_nome(),
        "nucleos": os.cpu_count(),
        "ram_gb": _ram_local_gb(),
        "gpu": gpu,
        "simd": _simd_local(),
        "arquitetura": platform.machine(),
    }


def _broker() -> Optional[List[dict]]:
    url = config.carregar().get("broker_url", "").rstrip("/")
    if not url:
        return None
    try:
        return http_json(url + "/api/agentes", timeout=4, tentativas=1)
    except Exception:
        return None


def carregar_parque(com_broker: bool = True) -> dict:
    """Devolve {maquinas:[...], fontes:{broker:bool, local:str}} com tudo mesclado.
    Se a máquina atual não estiver em parque.json, cria automaticamente um perfil local para funcionar em qualquer PC."""
    base = ler_json(config.PARQUE_ARQ, {"maquinas": []}) or {"maquinas": []}
    maquinas: Dict[str, dict] = {m["id"]: dict(m) for m in base.get("maquinas", [])}
    fontes: Dict[str, Any] = {"estatico": base.get("atualizado_em"), "broker": False, "local": None}

    # --- detecção local: marca qual máquina do parque é esta (ou sintetiza uma se não houver parque.json)
    loc = detectar_local()
    host = (loc.get("hostname") or "").lower()
    alvo = None
    for mid, m in maquinas.items():
        if mid == host or m.get("nome", "").lower() == host:
            alvo = mid
    forcado = config.carregar().get("maquina_id") or ""   # instaladores gravam o id: hostname do Windows nem sempre é o nome do parque
    if forcado in maquinas:
        alvo = forcado
    if alvo is None and loc.get("gpu") and "boss" in maquinas:
        alvo = "boss"  # usa o slot principal para a GPU local (NVIDIA, AMD, Intel ou Apple Silicon)
    if alvo:
        m = maquinas[alvo]
        m["local"] = True
        fontes["local"] = alvo
        if loc.get("gpu"):
            g = loc["gpu"]
            bw = g.get("bw_gbs") if g.get("alternativa") else ((m.get("gpu") or {}).get("bw_gbs") or g.get("bw_gbs", 448))
            m["gpu"] = {**(m.get("gpu") or {}), "nome": g["nome"], "vram_gb": g["vram_gb"],
                        "vram_livre_gb": g["vram_livre_gb"], "driver": g["driver"], "bw_gbs": bw}
            if g.get("unificada"):
                m["unificada"] = True
        if loc.get("ram_gb"):
            m["ram_gb"] = loc["ram_gb"]
        if loc.get("simd"):
            m["simd"] = loc["simd"]
        if loc.get("cpu"):
            m["cpu"] = loc["cpu"]
        m["online"] = True
        m["fonte"] = "local+estatico"
    elif not maquinas:
        mid = re.sub(r"[^a-z0-9\-]+", "-", host).strip("-") or "local"
        g = loc.get("gpu")
        ram = loc.get("ram_gb") or 16.0
        maquinas[mid] = {
            "id": mid, "nome": loc.get("hostname") or "Este computador",
            "papel": "Estação local (auto-detectada)", "so": loc.get("so", ""),
            "cpu": loc.get("cpu", ""), "nucleos": loc.get("nucleos") or 4, "ram_gb": ram,
            "gpu": {"nome": g["nome"], "vram_gb": g["vram_gb"], "vram_livre_gb": g.get("vram_livre_gb"),
                    "driver": g.get("driver", ""), "bw_gbs": g.get("bw_gbs", 320)} if g else None,
            "unificada": bool(g and g.get("unificada")),
            "bw_gbs_min": 35 if "avx2" in (loc.get("simd") or []) else 18,
            "bw_gbs_max": 60 if "avx2" in (loc.get("simd") or []) else 32,
            "simd": loc.get("simd") or ["avx2"], "arquitetura": loc.get("arquitetura", ""),
            "reserva_so_gb": 3.5 if ram >= 8 else 1.8, "runtime": "ollama",
            "local": True, "online": True, "fonte": "local",
        }
        fontes["local"] = mid

    # --- broker (somente leitura)
    if com_broker:
        agentes = _broker()
        if agentes is not None:
            fontes["broker"] = True
            for a in agentes:
                mid = a.get("hostname")
                m = maquinas.get(mid)
                if not m:
                    continue
                info = a.get("info") or {}
                m["online"] = bool(a.get("online")) or m.get("online", False)
                m["visto_ha_s"] = a.get("ha_segundos")
                m["disco_livre_gb"] = a.get("disco_livre_gb")
                m["discos"] = a.get("discos") or []
                if info.get("ram_total_mb") and not m.get("local"):
                    m["ram_gb"] = round(info["ram_total_mb"] / 1024, 1)
                if info.get("cpu"):
                    m["cpu_inventario"] = info["cpu"]
                if info.get("so"):
                    m["so"] = info["so"]
                m["tem_claude"] = info.get("tem_claude")
                m["fonte"] = (m.get("fonte") or "estatico") + "+broker"
    for m in maquinas.values():
        m.setdefault("online", False)
        m.setdefault("fonte", "estatico")
    ordem = ["boss", "aspire5", "raspberrypi", "celeron", "i3"]
    lista = sorted(maquinas.values(), key=lambda x: (-1 if x.get("local") and x["id"] not in ordem else (ordem.index(x["id"]) if x["id"] in ordem else 99)))
    return {"maquinas": lista, "fontes": fontes}


def memoria_modelo(maq: Optional[dict]) -> tuple:
    """(GiB que um modelo pode ocupar, sem_gpu): a VRAM se houver GPU; senão a RAM livre para modelo (respeita max_modelo_gb).
    NUNCA assume 16 GB: numa CPU de 4 GB isso levaria a sonda a testar contextos de 128k e matar a máquina."""
    from . import fit
    maq = maq or {}
    sem_gpu = not (maq.get("gpu") or {}).get("vram_gb")
    return round(fit.orcamento_bytes(maq, float(config.carregar().get("reserva_vram_gb", fit.RESERVA_PADRAO_GB))) / 1024 ** 3, 2) if maq else 4.0, sem_gpu


def maquina_local(pk: Optional[dict] = None) -> dict:
    """Devolve a máquina principal onde o painel roda (local, ou a primeira com GPU, ou a primeira da lista)."""
    pk = pk or carregar_parque(False)
    ms = pk.get("maquinas") or []
    return (next((m for m in ms if m.get("local")), None)
            or next((m for m in ms if (m.get("gpu") or {}).get("vram_gb")), None)
            or (ms[0] if ms else {"id": "local", "nome": "Este computador", "ram_gb": 16, "reserva_so_gb": 3.5, "simd": ["avx2"], "local": True}))


def maquina(mid: str, com_broker: bool = False) -> Optional[dict]:
    for m in carregar_parque(com_broker)["maquinas"]:
        if m["id"] == mid:
            return m
    return None


def espaco_livre_gb(path: Path) -> Optional[float]:
    try:
        p = Path(path)
        while not p.exists() and p.parent != p:
            p = p.parent
        return round(shutil.disk_usage(p).free / 1e9, 1)
    except Exception:
        return None


if __name__ == "__main__":
    # Rode em qualquer máquina do parque (só precisa de Python 3): imprime o que o painel precisa saber.
    import json
    d = detectar_local()
    d["banda_memoria_gbs_medida"] = medir_banda_memoria_gbs()
    print(json.dumps(d, ensure_ascii=False, indent=2))
