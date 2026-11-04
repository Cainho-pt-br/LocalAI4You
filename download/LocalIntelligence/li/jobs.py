"""Tarefas em segundo plano do painel (varredura, download, benchmark…), com progresso e cancelamento.

Tarefas "pesadas" (que usam GPU, disco ou rede por muito tempo) rodam uma de cada vez: duas ao mesmo
tempo falsificariam a medição de velocidade e a de VRAM.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional

from . import config
from .util import Progresso, agora_iso, ler_json, parse_iso

PESADAS = {"bench", "sonda", "desafio", "duelo", "atualizar", "download", "exportar", "verificar"}  # duelo e atualizar também baixam/medem: não podem correr junto
_FIM = (None, "concluido", "cancelado", "erro")


def externo() -> Optional[dict]:
    """Tarefa pesada de OUTRO processo (CLI rodando `bench`, por exemplo), lida de estado/progresso.json.

    A trava é por batimento: se o arquivo não for atualizado há 3 min, considera morta (CLI interrompida).
    Não usa os.kill(pid, 0): no Windows isso MATA o processo.
    """
    d = ler_json(config.PROGRESSO, None)
    if not d or d.get("fase") in _FIM or d.get("pid") == os.getpid():
        return None
    t = parse_iso(d.get("atualizado"))
    if not t or (time.time() - t.timestamp()) > 180:
        return None
    return d


def registrar(origem: str, tipo: str, titulo: str, **extra) -> Progresso:
    p = Progresso(config.PROGRESSO)
    p.d = {}
    p.set(origem=origem, pid=os.getpid(), tipo=tipo, titulo=titulo, **extra)
    return p


class Contexto:
    def __init__(self, job: "Job"):
        self.job = job
        self.cancelar = job.cancelar

    def prog(self, d: Dict[str, Any]) -> None:
        j = self.job
        if j.arquivo is not None:  # a fase final só é gravada quando a TAREFA inteira termina (ver corpo())
            fase = d.get("fase")
            j.arquivo.set(**{k: v for k, v in d.items() if k in ("msg", "pct", "feitos", "total", "eta_s", "modelo")},
                          fase="rodando" if fase in (None, "concluido", "cancelado") else fase)
        if "msg" in d:
            j.msg = d["msg"]
            if not j.log or j.log[-1] != d["msg"]:
                j.log.append(d["msg"])
                del j.log[:-60]
        for k in ("pct", "feitos", "total", "eta_s", "fase", "modelo"):
            if k in d:
                setattr(j, k if k != "pct" else "pct", d[k])
        if "pct" not in d and d.get("total"):
            j.pct = round(100 * d.get("feitos", 0) / d["total"], 1)


class Job:
    def __init__(self, tipo: str, titulo: str):
        self.id = uuid.uuid4().hex[:10]
        self.tipo, self.titulo = tipo, titulo
        self.estado = "rodando"
        self.msg = "iniciando…"
        self.pct: Optional[float] = None
        self.fase = self.modelo = None
        self.feitos = self.total = self.eta_s = None
        self.criado = agora_iso()
        self.fim: Optional[str] = None
        self.resultado: Any = None
        self.erro: Optional[str] = None
        self.log: List[str] = []
        self.cancelar = threading.Event()
        self.arquivo: Optional[Progresso] = None

    def dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "tipo", "titulo", "estado", "msg", "pct", "fase", "modelo", "feitos", "total",
                                              "eta_s", "criado", "fim", "erro")} | {"log": self.log[-12:], "resultado": self.resultado}


class Gerente:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def pesado_em_andamento(self) -> Optional[Job]:
        for j in self.jobs.values():
            if j.estado == "rodando" and j.tipo in PESADAS:
                return j
        return None

    def bloqueio(self) -> Optional[str]:
        j = self.pesado_em_andamento()
        if j:
            return j.titulo
        e = externo()
        return f"{e.get('titulo', 'tarefa')} (rodando no terminal)" if e else None

    def iniciar(self, tipo: str, titulo: str, fn: Callable[[Contexto], Any]) -> Job:
        with self._lock:
            if tipo in PESADAS:
                ocupado = self.bloqueio()
                if ocupado:
                    raise RuntimeError(f"Já há uma tarefa pesada em andamento: {ocupado}. Espere terminar ou cancele.")
            job = Job(tipo, titulo)
            if tipo in PESADAS:
                job.arquivo = registrar("painel", tipo, titulo, fase="rodando", msg="iniciando…")
            self.jobs[job.id] = job
            for velho in sorted(self.jobs.values(), key=lambda j: j.criado)[:-30]:
                if velho.estado != "rodando":
                    self.jobs.pop(velho.id, None)

        def corpo():
            try:
                job.resultado = fn(Contexto(job))
                job.estado = "cancelado" if job.cancelar.is_set() else "concluido"
            except Exception as e:  # nunca derruba o servidor
                job.estado = "cancelado" if job.cancelar.is_set() else "erro"
                job.erro = f"{type(e).__name__}: {e}"
                job.msg = job.erro
                job.log.append("ERRO: " + traceback.format_exc(limit=3).strip().splitlines()[-1])
            finally:
                job.fim = agora_iso()
                if job.arquivo is not None:
                    job.arquivo.set(fase={"concluido": "concluido", "cancelado": "cancelado"}.get(job.estado, "erro"), msg=job.msg)
        threading.Thread(target=corpo, daemon=True, name=f"job-{tipo}").start()
        return job

    def cancelar(self, jid: str) -> bool:
        j = self.jobs.get(jid)
        if j and j.estado == "rodando":
            j.cancelar.set()
            j.msg = "cancelando…"
            return True
        return False

    def lista(self) -> List[dict]:
        return [j.dict() for j in sorted(self.jobs.values(), key=lambda j: j.criado, reverse=True)]

    def lista_com_externa(self) -> dict:
        return {"jobs": self.lista(), "externa": externo()}
