"""Aba "Medir": em vez de pedir ao Caio que escolha modelo, nível e modo às cegas, diz o que vale rodar AGORA e por quê.

Cada passo sugerido traz o motivo, o custo estimado em minutos (a latência média por item, medida nas rodadas anteriores
do próprio modelo) e os parâmetros prontos para o botão. O formulário manual continua existindo para quem quiser.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from . import decide, papeis, parque, resultados
from .bench import stats
from .bench import amostras, custo, sonda, suites
from .ollama import Ollama

# o que cada teste mede, em português simples (o painel mostra isso ao lado do botão)
SUITE_EXPLICA = {
    "mmlu_pt": "Prova de múltipla escolha (vestibular/ENEM e concursos) em português: o modelo sabe e entende?",
    "mmlu_pro": "Perguntas difíceis de conhecimento técnico e científico, em inglês, com 10 alternativas.",
    "capitu": "Instruções em português com restrições (tamanho, tom, formato): obedece ao que foi pedido?",
    "ifeval": "Seguir regras verificáveis à risca: sem vírgula, em maiúsculas, com N tópicos, JSON válido…",
    "bfcl_prompt": "Escolher a ferramenta certa e preencher os argumentos, com o esquema descrito no texto.",
    "bfcl_native": "O mesmo, usando o recurso nativo de ferramentas do Ollama (o que agentes de verdade usam).",
    "humaneval": "Escrever funções Python que passam em testes automáticos de verdade.",
    "gsm8k": "Problemas de matemática escolar em linguagem natural: raciocina até o resultado certo?",
    "visao": "Ler notas fiscais (OCR), comparar barras em gráficos e extrair JSON de painéis de sistema.",
}

MIN_PASSO_SONDA = 3.0   # minutos por modelo (4k/16k/32k de contexto), medido nas sondas anteriores


def _esperado(caps: List[str], nivel: str) -> int:
    return sum(n for s, n in amostras.NIVEIS[nivel].items() if s in suites.ORDEM and all(c in (caps or []) for c in suites.EXIGE.get(s, [])))


def _nivel_atingido(n_itens: int, caps: List[str]) -> Optional[str]:
    ordem = ["minimo", "rapido", "padrao", "profundo"]
    atingido = None
    for nv in ordem:
        if n_itens >= 0.97 * _esperado(caps, nv):
            atingido = nv
    return atingido


def _lat_media(rows: List[dict]) -> Dict[str, float]:
    """modelo → segundos médios por item (só respostas válidas do modo base)."""
    acc: Dict[str, List[float]] = {}
    for r in rows:
        if r.get("suite") != "_meta" and r.get("valido") and r.get("modo", "base") == "base" and r.get("lat"):
            acc.setdefault(r["modelo"], []).append(float(r["lat"]))
    return {m: sum(v) / len(v) for m, v in acc.items() if v}


def _minutos(n_itens: int, lat_s: float) -> int:
    return max(1, round(n_itens * lat_s / 60))


def plano(oll: Optional[Ollama], mesa: Optional[dict] = None) -> dict:
    inst = decide.modelos_do_boss(oll)
    rows = resultados.carregar()
    lat = _lat_media(rows)
    maq = parque.maquina_local()
    modelos: List[dict] = []
    for m in inst:
        med = m.get("medido") or {}
        n = med.get("n_itens") or 0
        nv = _nivel_atingido(n, m.get("caps") or []) if n else None
        tem_think = bool(m.get("medido_think"))
        tem_visao_cap = "vision" in (m.get("caps") or [])
        tem_visao_med = bool((med.get("suites") or {}).get("visao"))
        modelos.append({
            "id": m["id"], "bytes": m["bytes"], "params": m.get("params"), "quant": m.get("quant"), "caps": m.get("caps", []),
            "n_itens": n, "nivel": nv, "ultima": med.get("ultima"), "lat_s": round(lat.get(m["id"]) or custo.seg_por_item(maq, m["bytes"]), 2),
            "lat_estimada": m["id"] not in lat, "sonda": bool((m.get("sonda") or {}).get("pontos")),
            "ctx_max_gpu": (m.get("sonda") or {}).get("ctx_max_gpu"), "think": tem_think, "tem_thinking": "thinking" in (m.get("caps") or []),
            "tem_visao": tem_visao_cap, "visao_medida": tem_visao_med, "lat_img_s": round(custo.seg_por_imagem(maq, m["bytes"]), 1) if tem_visao_cap else None,
            "tps": med.get("tps_mediana"),
        })
    por_id = {m["id"]: m for m in modelos}
    passos: List[dict] = []
    pesos_todos = [m["bytes"] for m in modelos]
    custo_maq = custo.resumo(maq, pesos_todos, [m["tem_visao"] for m in modelos])

    # 1) sem nota nenhuma
    sem = [m for m in modelos if not m["n_itens"]]
    if sem:
        nv_sem = custo.recomendado(maq, [m["bytes"] for m in sem], [m["tem_visao"] for m in sem])
        mins = sum(_minutos(_esperado(next(i for i in inst if i["id"] == m["id"]).get("caps"), nv_sem), m["lat_s"])
                   + (_minutos(custo.itens_visao(nv_sem), custo.seg_por_imagem(maq, m["bytes"])) if m["tem_visao"] else 0) for m in sem)
        porque = ("Sem medição o painel não sabe se vale manter ou trocar. O nível Padrão é o mínimo que dá margem de erro útil."
                  if nv_sem == "padrao" else
                  f"Sem medição o painel não sabe se vale manter ou trocar. Esta máquina é lenta: o nível Padrão levaria horas, então o painel sugere o nível {nv_sem} "
                  "(mesmos itens, menos deles: a margem de erro fica grande, e o painel mostra isso).")
        passos.append({"id": "medir-novos", "prioridade": 1, "recomendado": True, "titulo": f"Medir {len(sem)} modelo(s) que ainda não têm nota",
                       "porque": porque, "modelos": [m["id"] for m in sem], "nivel": nv_sem, "modo": "base", "tipo": "bench", "minutos": mins})
    # 1b) modelos com visão que já foram medidos em texto mas ainda não na suíte visual
    sem_vis = [m for m in modelos if m["tem_visao"] and not m["visao_medida"] and m["n_itens"] > 0]
    if sem_vis:
        passos.append({"id": "medir-visao", "prioridade": 2, "recomendado": True,
                       "titulo": f"Medir capacidade de Visão ({len(sem_vis)} modelo(s) multimodal)",
                       "porque": "Testa leitura de notas fiscais (OCR), gráficos de barras e painéis visuais nos modelos que declaram visão.",
                       "modelos": [m["id"] for m in sem_vis], "nivel": "padrao", "modo": "base", "suites": ["visao"], "tipo": "bench",
                       "minutos": max(1, len(sem_vis) * 2)})
    # 2) medido só no rápido: não decide nada
    raso = [m for m in modelos if m["nivel"] == "rapido"] if custo_maq["recomendado"] == "padrao" else []
    if raso:
        falta = lambda m: _esperado(next(i for i in inst if i["id"] == m["id"]).get("caps"), "padrao") - m["n_itens"]
        passos.append({"id": "aprofundar-rapido", "prioridade": 2, "recomendado": True, "titulo": f"Completar {len(raso)} modelo(s) medido(s) só no nível Rápido",
                       "porque": "Poucos itens dão margem de erro de ±9 pontos ou mais: serve de triagem, não de decisão. O nível Padrão reaproveita o que já foi medido.",
                       "modelos": [m["id"] for m in raso], "nivel": "padrao", "modo": "base", "tipo": "bench",
                       "minutos": sum(_minutos(max(falta(m), 0), m["lat_s"]) for m in raso)})
    # 3) sem sonda: contexto real na GPU
    sem_sonda = [m for m in modelos if not m["sonda"]]
    if sem_sonda:
        passos.append({"id": "sonda", "prioridade": 3, "recomendado": False, "titulo": f"Medir VRAM e velocidade com contexto grande ({len(sem_sonda)} modelo(s))",
                       "porque": "Responde 'cabe com 32k de contexto na minha placa, e a que velocidade?' com medição, não com estimativa.",
                       "modelos": [m["id"] for m in sem_sonda], "nivel": None, "modo": None, "tipo": "sonda", "minutos": round(MIN_PASSO_SONDA * len(sem_sonda))})
    # 4) empates: mais itens estreitam a margem de erro
    emp = _empates(mesa, por_id)
    if emp:
        a, b, pid, dif = emp
        mi = _minutos(amostras_total("profundo") - amostras_total("padrao"), (por_id[a]["lat_s"] + por_id[b]["lat_s"]) / 2) * 2
        passos.append({"id": "desempatar", "prioridade": 4, "recomendado": False,
                       "titulo": f"Desempatar {a} × {b} ({papeis.POR_ID[pid]['rotulo']})",
                       "porque": f"A diferença é de {str(round(abs(dif), 1)).replace('.', ',')} ponto(s): dentro do ruído. O nível Profundo estreita a margem de erro em cerca de 30% — pode separar os dois, ou confirmar que o empate é real.",
                       "modelos": [a, b], "nivel": "profundo", "modo": "base", "tipo": "bench", "minutos": mi})
    # 5) raciocínio ligado
    pens = [m for m in modelos if m["tem_thinking"] and not m["think"] and m["n_itens"]]
    if pens:
        passos.append({"id": "think", "prioridade": 5, "recomendado": False, "titulo": f"Medir com o raciocínio ligado ({len(pens)} modelo(s))",
                       "porque": "Hoje o benchmark mede o jeito de usar no dia a dia (sem 'pensar'). O modo Raciocínio mostra o teto do modelo em matemática, código e perguntas difíceis — mais lento e usa mais tokens.",
                       "modelos": [m["id"] for m in pens], "nivel": "padrao", "modo": "think", "tipo": "bench",
                       "minutos": sum(_minutos(round(_esperado(["thinking"], "padrao") * 0.4), m["lat_s"] * 4) for m in pens)})
    passos.sort(key=lambda p: p["prioridade"])
    estim = {n["id"]: n for n in custo_maq["niveis"]}
    niveis = [{"id": nv, "itens": estim[nv]["itens"], "imagens": estim[nv]["imagens"], "minutos_total": estim[nv]["minutos"],
               "recomendado": nv == custo_maq["recomendado"],
               "para": {"minimo": "máquinas lentas (CPU, Raspberry): só um sinal de que o modelo funciona; margem de erro grande",
                        "rapido": "triagem: o modelo é minimamente capaz?", "padrao": "decisão do dia a dia (recomendado)",
                        "profundo": "desempate e decisão final"}[nv]}
              for nv in custo.ORDEM]
    usado_em: Dict[str, List[str]] = {s: [] for s in amostras.NIVEIS["padrao"]}
    for p in papeis.PAPEIS:
        for s in p.get("pesos", {}):
            usado_em[s].append(p["rotulo"])
    testes = [{"id": s, "nome": papeis.SUITES.get(s, s), "mede": SUITE_EXPLICA.get(s, ""), "usado_em": usado_em.get(s, []),
               "itens": {nv: amostras.NIVEIS[nv][s] for nv in amostras.NIVEIS}} for s in suites.ORDEM]
    return {"modelos": modelos, "passos": passos, "niveis": niveis, "testes": testes, "think_suites": suites.SUITES_THINK,
            "maquina": {"nome": custo_maq["maquina"], "sem_gpu": custo_maq["sem_gpu"], "nivel_recomendado": custo_maq["recomendado"]}}


def amostras_total(nivel: str) -> int:
    return sum(amostras.NIVEIS[nivel].values())


def _empates(mesa: Optional[dict], por_id: Dict[str, dict]) -> Optional[tuple]:
    """O empate que mais vale aprofundar: um modelo MENOR que empata com o titular numa função, com a maior diferença de nota."""
    if not mesa:
        return None
    melhor = None
    for pid, linhas in (mesa.get("ranking") or {}).items():
        tit = next((x for x in linhas if x["titular"]), None)
        if not tit or tit["modelo"] not in por_id or por_id[tit["modelo"]]["nivel"] not in ("padrao", "profundo"):
            continue
        for x in linhas:
            vs = x.get("vs_titular")
            if x["titular"] or not vs or vs["veredito"] != "empate" or x["modelo"] not in por_id:
                continue
            if por_id[x["modelo"]]["nivel"] not in ("padrao", "profundo"):
                continue
            if por_id[x["modelo"]]["nivel"] == "profundo" and por_id[tit["modelo"]]["nivel"] == "profundo":
                continue  # os dois já estão no teto de itens
            chave = (1 if x["bytes"] < tit["bytes"] else 0, abs(vs["dif"]))
            if melhor is None or chave > melhor[0]:
                melhor = (chave, tit["modelo"], x["modelo"], pid, vs["dif"])
    return None if not melhor else (melhor[1], melhor[2], melhor[3], melhor[4])


def visao_comparar() -> dict:
    """Modelos de visão medidos nas suítes `visao_leve` (imagens sintéticas) e `visao_fotos` (fotos suas), mais o detector atual.
    Contagem: 'exato' = acertou o número; 'erro médio' = |previsto − real| médio. O detector entra com as contagens do gabarito."""
    import json
    extras = ("visao_leve", "visao_fotos")
    ultimo: Dict[tuple, dict] = {}
    for r in resultados.carregar():
        if r.get("suite") in extras and r.get("valido") and r.get("modo", "base") == "base" and (r["item"].startswith("vl2-") or r["item"].startswith("foto-")):   # vl-* = 1ª versão das perguntas (instrução de 1 palavra), descartada
            ultimo[(r["modelo"], r["suite"], r["item"])] = r      # a medição mais recente de cada item vale
    por: Dict[str, dict] = {}
    for (modelo, suite, _), r in ultimo.items():
        e = por.setdefault(modelo, {"modelo": modelo, "leve": {"n": 0, "k": 0, "categorias": {}}, "fotos": {"n": 0, "k": 0, "erros": []}, "lat": []})
        det = r.get("det") or {}
        if r.get("lat"):
            e["lat"].append(float(r["lat"]))
        if suite == "visao_leve":
            c = e["leve"]["categorias"].setdefault(det.get("categoria") or "?", {"n": 0, "k": 0})
            c["n"] += 1
            c["k"] += 1 if r.get("ok") else 0
            e["leve"]["n"] += 1
            e["leve"]["k"] += 1 if r.get("ok") else 0
        else:
            e["fotos"]["n"] += 1
            e["fotos"]["k"] += 1 if r.get("ok") else 0
            try:
                e["fotos"]["erros"].append(abs(int(det.get("previsto")) - int(det.get("esperado"))))
            except (TypeError, ValueError):
                e["fotos"]["erros"].append(None)
    lista = []
    for e in por.values():
        erros = [x for x in e["fotos"]["erros"] if x is not None]
        lista.append({"modelo": e["modelo"], "leve": {**e["leve"], "acc": round(100 * e["leve"]["k"] / e["leve"]["n"], 1) if e["leve"]["n"] else None,
                                                      "ic": stats.wilson(e["leve"]["k"], e["leve"]["n"]) if e["leve"]["n"] else None},
                      "fotos": {"n": e["fotos"]["n"], "exato": round(100 * e["fotos"]["k"] / e["fotos"]["n"], 1) if e["fotos"]["n"] else None,
                                "erro_medio": round(sum(erros) / len(erros), 2) if erros else None, "sem_resposta": len(e["fotos"]["erros"]) - len(erros)},
                      "lat_s": round(statistics.median(e["lat"]), 1) if e["lat"] else None})
    lista.sort(key=lambda x: -(x["leve"]["acc"] or 0))
    detector, n_fotos = None, 0
    gab_arq = amostras.FOTOS / "gabarito.json"
    if gab_arq.exists():
        try:
            gab = json.loads(gab_arq.read_text("utf-8"))
            n_fotos = len([1 for v in gab.values() if isinstance(v, dict) and "contagem" in v])
            pares = [(int(v["contagem"]), int(v["detector"])) for v in gab.values() if isinstance(v, dict) and "contagem" in v and v.get("detector") is not None]
            if pares:
                detector = {"n": len(pares), "exato": round(100 * sum(1 for a, b in pares if a == b) / len(pares), 1),
                            "erro_medio": round(sum(abs(a - b) for a, b in pares) / len(pares), 2)}
        except (ValueError, TypeError, OSError):
            pass
    return {"modelos": lista, "detector": detector, "fotos_cadastradas": n_fotos, "pasta_fotos": str(amostras.FOTOS),
            "suites": ["visao_leve", "visao_fotos"], "niveis": {nv: {"leve": amostras.NIVEIS[nv]["visao_leve"], "fotos": amostras.NIVEIS[nv]["visao_fotos"]} for nv in amostras.NIVEIS}}
