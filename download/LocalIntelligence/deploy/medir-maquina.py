#!/usr/bin/env python3
"""Mede o que importa para rodar modelo local nesta máquina. Arquivo único, só Python 3 (stdlib), qualquer SO.

    python3 medir-maquina.py            # imprime JSON
    python3 medir-maquina.py --texto    # resumo legível

O que sai: CPU, núcleos, RAM, instruções vetoriais (SSE/AVX/AVX2/AVX-512/NEON), GPU NVIDIA (se houver), memória
livre e a banda de cópia de memória medida (GB/s). A banda é o que limita tokens/s em CPU: com ela o painel troca a
estimativa por um número da própria máquina. Compare os valores com `parque/parque.json` e corrija se divergirem.

Serve para os agentes do parque (job `shell` na tag da máquina) e para rodar à mão. Não instala nada, não usa rede.
"""
import ctypes
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path


def ram_gb():
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("carga", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("livre", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong),
                            ("e", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 1024 ** 3, 2), round(m.livre / 1024 ** 3, 2)
        total = livre = None
        for ln in Path("/proc/meminfo").read_text().splitlines():
            if ln.startswith("MemTotal"):
                total = int(ln.split()[1]) / 1024 ** 2
            if ln.startswith("MemAvailable"):
                livre = int(ln.split()[1]) / 1024 ** 2
        return round(total, 2), round(livre, 2)
    except Exception:
        return None, None


def simd():
    achados = []
    try:
        if os.name == "nt":
            k = ctypes.windll.kernel32.IsProcessorFeaturePresent
            for pf, nome in ((10, "sse"), (39, "avx"), (40, "avx2"), (41, "avx512")):
                if k(pf):
                    achados.append(nome)
        else:
            flags = Path("/proc/cpuinfo").read_text()
            for f, nome in (("sse4_2", "sse"), ("neon", "neon"), ("asimd", "neon"), ("avx", "avx"), ("avx2", "avx2"), ("avx512f", "avx512")):
                if re.search(rf"\b{f}\b", flags) and nome not in achados:
                    achados.append(nome)
    except Exception:
        pass
    return achados


def cpu_nome():
    try:
        if os.name == "nt":
            import winreg  # o wmic foi removido do Windows 11 recente; o registro sempre tem o nome
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return " ".join(winreg.QueryValueEx(k, "ProcessorNameString")[0].split())
        else:
            for ln in Path("/proc/cpuinfo").read_text().splitlines():
                if ln.lower().startswith(("model name", "hardware", "model\t")):
                    return ln.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


def gpu():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                                      text=True, timeout=6, stderr=subprocess.DEVNULL).strip().splitlines()[0]
        n, t, l = [p.strip() for p in out.split(",")]
        return {"nome": n, "vram_gib": round(int(t) / 1024, 1), "livre_gib": round(int(l) / 1024, 1)}
    except Exception:
        return None


def banda_gbs(mb=256, reps=5):
    """Cópia de memória (lê+escreve), uma thread. Subestima o pico da máquina, mas é a mesma régua em todas."""
    try:
        a = bytearray(mb * 1024 * 1024)
        melhor = 0.0
        for _ in range(reps):
            t0 = time.perf_counter()
            b = bytes(a)
            dt = time.perf_counter() - t0
            melhor = max(melhor, (2 * mb / 1024) / dt)
            del b
        return round(melhor, 1)
    except MemoryError:
        return None


def main():
    total, livre = ram_gb()
    d = {"hostname": platform.node(), "so": f"{platform.system()} {platform.release()}", "arquitetura": platform.machine(),
         "cpu": cpu_nome(), "nucleos_logicos": os.cpu_count(), "ram_total_gb": total, "ram_livre_gb": livre, "simd": simd(),
         "gpu_nvidia": gpu(), "banda_copia_memoria_gbs": banda_gbs(), "python": sys.version.split()[0]}
    if "--texto" in sys.argv:
        print(f"{d['hostname']} · {d['so']} · {d['cpu']}\n  {d['nucleos_logicos']} threads · RAM {total} GB ({livre} livres) · "
              f"instruções: {', '.join(d['simd']) or '?'} · banda de cópia ~{d['banda_copia_memoria_gbs']} GB/s"
              + (f" · GPU {d['gpu_nvidia']['nome']} {d['gpu_nvidia']['vram_gib']} GiB" if d["gpu_nvidia"] else ""))
    else:
        print(json.dumps(d, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
