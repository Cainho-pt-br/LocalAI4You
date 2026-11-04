"""Fluxo "testar sem se comprometer" e "duelo direto A × B": baixa se necessário, mede com o mesmo protocolo e compara.

Nada é trocado sozinho: o resultado vira um veredito PENDENTE; promover ou apagar são ações explícitas.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from . import PROTOCOLO, aposentados, config, decide, fit, papeis, parque, resultados, scout
from .bench import runner, sonda, stats
from .fontes import ollama_lib
from .ollama import Ollama, pasta_modelos
from .util import GB, agora_iso, fmt_gb, gravar_json, slug

MARGEM_EFICIENCIA = {"tamanho": 0.8, "velocidade": 1.25}


class ErroDesafio(Exception):
    pass


def _achar_instalado(oll: Ollama, pull: str) -> Optional[dict]:
    alvo = pull.replace("hf.co/", "").lower()
    instalados = oll.instalados()
    for m in instalados:
        if m["id"].replace("hf.co/", "").lower() == alvo or m["id"].lower() == pull.lower():
            return m
    # IMPORTANTE: só aceita casamento por prefixo quando o usuário NÃO especificou uma tag/quantização explícita (ex.: digitou só 'gpt-oss').
    # Se `pull` tem `:tag` (ex.: `hf.co/unsloth/Qwen3.8-27B-GGUF:Q3_K_M`), NUNCA deve confundir com outra quantização instalada (`:UD-IQ3_S`).
    if ":" not in pull:
        sem_tag = pull.lower()
        for m in instalados:
            if m["id"].split(":")[0].lower() == sem_tag:
                return m
    elif pull.lower().endswith(":latest"):
        base = pull[:-7].lower()
        for m in instalados:
            if m["id"].lower() == base:
                return m
    return None


def _candidato(cand_id: str) -> dict:
    snap = scout.ultimo()
    if not snap:
        raise ErroDesafio("Radar sem dados: rode a varredura antes.")
    for c in snap["candidatos"]:
        if c["id"] == cand_id:
            return c
    raise ErroDesafio(f"Candidato {cand_id} não está no último radar.")


_PULL_OK = re.compile(r"^(hf\.co/[\w.\-]+/[\w.\-]+|[\w.\-]+(?:/[\w.\-]+)?):[\w.\-]+$")


def _encaixe_da_escolha(c: dict, boss: dict, p: dict, cfg: dict, pull: str) -> dict:
    """Confere nome, tamanho real (manifesto, sem baixar) e se cabe 100% na GPU."""
    if not _PULL_OK.match(pull):
        raise ErroDesafio("Nome de modelo/quantização inválido (esperado algo como `qwen3.5:9b` ou `hf.co/autor/repo:Q4_K_M`).")
    v = next((x for x in c["variantes"] if x["pull"].lower() == pull.lower()), None)
    if not v:
        pre = ollama_lib.preflight(pull)
        if not pre["ok"]:
            raise ErroDesafio("Não consegui confirmar essa quantização no registro: " + pre.get("erro", "erro desconhecido"))
        tag = pull.split(":", 1)[1]
        v = {"tag": tag, "pull": pull, "quant": fit.quant_de_nome(tag) or fit.quant_de_nome(tag.replace("-", "_")) or tag,
             "bytes": int(pre.get("bytes_modelo") or pre["bytes_total"]), "extra_bytes": int(pre.get("bytes_projetor", 0)),
             "padrao": False, "fonte": "hf" if pull.lower().startswith("hf.co/") else "ollama"}
    ctx = decide.ctx_para(boss, p)
    total = v["bytes"] + int(v.get("extra_bytes", 0))
    e = fit.avaliar_encaixe(total, c["arch"], boss, ctx, cfg["kv_cache"], cfg["reserva_vram_gb"])
    if e["nivel"] == "nao_cabe":
        raise ErroDesafio(f"{v['quant']} ({fmt_gb(total)}) não cabe na memória com folga (orçamento {e['orcamento_gb']} GB): escolha uma quantização menor.")
    v = {**v, "bpw": round(fit.bpw(v["bytes"], c["params_b"]), 2), "encaixe": e}
    return {"cabe": True, "variante": v, "encaixe": e}


def plano(cand_id: str, papel_id: Optional[str], oll: Optional[Ollama], pull: Optional[str] = None) -> dict:
    """Mostra o que o teste vai fazer (tamanho do download, espaço livre, quantização) ANTES de baixar."""
    c = _candidato(cand_id)
    cfg = config.carregar()
    pk = parque.carregar_parque(False)
    boss = parque.maquina_local(pk)
    p = papeis.POR_ID.get(papel_id or (c["papeis"][0] if c["papeis"] else "chat_pt"))
    enc = _encaixe_da_escolha(c, boss, p, cfg, pull.strip()) if pull else decide.encaixe_candidato(c, boss, p, cfg)
    if not enc or not enc.get("cabe"):
        raise ErroDesafio("Nenhuma quantização desse modelo cabe na máquina com folga: " + (enc or {}).get("motivo", "sem variantes"))
    v = enc["variante"]
    livre = parque.espaco_livre_gb(pasta_modelos())
    ja = _achar_instalado(oll, v["pull"]) if oll and oll.no_ar() else None
    pre = {"ok": True, "bytes_total": v["bytes"] + int(v.get("extra_bytes", 0))}
    if not ja:
        pre = ollama_lib.preflight(v["pull"])
        if not pre["ok"] and not pre.get("sem_rede"):
            raise ErroDesafio("O Ollama não vai conseguir baixar essa variante: " + pre["erro"])
        if not pre["ok"]:
            pre = {"ok": True, "bytes_total": v["bytes"] + int(v.get("extra_bytes", 0)), "aviso": "sem rede para conferir o tamanho exato"}
    baixa = int(pre["bytes_total"])
    return {"candidato": c["nome"], "pull": v["pull"], "quant": v["quant"], "bytes": baixa, "tamanho": fmt_gb(baixa),
            "bytes_modelo": v["bytes"], "bytes_projetor": int(pre.get("bytes_projetor", 0)), "preflight": "ok" if not pre.get("aviso") else pre["aviso"],
            "espaco_livre_gb": livre, "cabe_no_disco": livre is None or livre * GB > baixa * 1.1 + 2 * GB,
            "ja_instalado": bool(ja), "encaixe": enc["encaixe"], "papel": p["id"], "origem": v.get("fonte", c["origem"]),
            "aviso": None if c.get("confianca") != "comunidade" else "Modelo de comunidade: pode ter perdido qualidade geral."}


def _comparar_com_titulares(oll: Ollama, novo: dict, titulares: Dict[str, str], inst: List[dict]) -> Dict[str, dict]:
    por_papel: Dict[str, dict] = {}
    por_id = {m["id"]: m for m in inst}
    for p in papeis.PAPEIS:
        if p.get("sem_nota"):
            continue
        if any(e not in (novo.get("caps") or []) for e in p.get("exige", [])):
            por_papel[p["id"]] = {"veredito": "nao_aplica", "motivo": "o desafiante não declara " + ", ".join(p["exige"])}
            continue
        if p["id"] == "rapido" and novo["bytes"] > decide.RAPIDO_MAX_GB * GB:
            por_papel[p["id"]] = {"veredito": "nao_aplica", "motivo": f"grande demais para 'segundo plano' (limite {decide.RAPIDO_MAX_GB:g} GB)"}
            continue
        tit_id = titulares.get(p["id"])
        tit = por_id.get(tit_id) if tit_id else None
        if not tit or tit["id"] == novo["id"]:
            por_papel[p["id"]] = {"veredito": "sem_titular", "motivo": "não há titular medido nesta função"}
            continue
        cmp = resultados.comparar((novo["id"], novo["digest"]), (tit["id"], tit["digest"]), p["id"])
        if not cmp or cmp["cobertura"] < 0.5:
            por_papel[p["id"]] = {"veredito": "incompleto", "motivo": "faltam medições em comum"}
            continue
        ver = stats.veredito_pareado(cmp)
        eficiencia = False
        if ver == "empate":
            rn = resultados.resumo(novo["id"], novo["digest"])
            rt = resultados.resumo(tit["id"], tit["digest"])
            menor = novo["bytes"] <= tit["bytes"] * MARGEM_EFICIENCIA["tamanho"]
            tn, tt = (rn or {}).get("tps_mediana"), (rt or {}).get("tps_mediana")
            mais_rapido = bool(tn and tt and tn >= tt * MARGEM_EFICIENCIA["velocidade"])
            eficiencia = menor or mais_rapido
        por_papel[p["id"]] = {"veredito": ver, "titular": tit["id"], "nota_novo": cmp["a"], "nota_titular": cmp["b"],
                              "dif": cmp["dif"], "ic": cmp["ic"], "so_novo": cmp["so_a"], "so_titular": cmp["so_b"],
                              "itens": cmp["itens"], "eficiencia": eficiencia}
    return por_papel


def _texto_resumo(nome: str, por_papel: Dict[str, dict], ref_nome: str = "o titular") -> tuple:
    vence = [pid for pid, r in por_papel.items() if r.get("veredito") == "superior"]
    perde = [pid for pid, r in por_papel.items() if r.get("veredito") == "inferior"]
    emp_ef = [pid for pid, r in por_papel.items() if r.get("veredito") == "empate" and r.get("eficiencia")]
    rot = lambda ids: ", ".join(papeis.POR_ID[i]["rotulo"] for i in ids)
    if vence:
        rec = "promover"
        txt = f"{nome} foi MELHOR que {ref_nome} em: {rot(vence)} (diferença maior que o ruído estatístico)."
        if perde:
            txt += f" Mas foi pior em: {rot(perde)} — promova só nas funções em que venceu."
    elif emp_ef:
        rec = "eficiencia"
        txt = f"{nome} empatou com {ref_nome} em: {rot(emp_ef)}, sendo menor ou mais rápido. Vantagem prática por eficiência."
    elif perde:
        rec = "descartar"
        txt = f"{nome} perdeu para {ref_nome} em: {rot(perde)}." + (" Não compensa manter." if ref_nome == "o titular" else "")
    else:
        rec = "manter"
        txt = f"{nome} ficou em empate técnico com {ref_nome}. Sem diferença de conhecimento fora da margem de erro."
    return rec, txt


def testar(oll: Ollama, cand_id: str, papel_id: Optional[str] = None, nivel: str = "padrao",
           ao_progredir: Optional[Callable[[dict], None]] = None, cancelar: Optional[threading.Event] = None,
           baixar: bool = True, pull: Optional[str] = None) -> dict:
    prog = ao_progredir or (lambda d: None)
    cancelar = cancelar or threading.Event()
    pl = plano(cand_id, papel_id, oll, pull)
    if not pl["cabe_no_disco"]:
        raise ErroDesafio(f"Sem espaço: precisa de ~{fmt_gb(pl['bytes'] * 1.1 + 2 * GB)} livres, há {pl['espaco_livre_gb']} GB.")
    novo = _achar_instalado(oll, pl["pull"])
    baixou_agora = False
    if not novo:
        if not baixar:
            raise ErroDesafio("Modelo não instalado.")
        prog({"fase": "download", "msg": f"Baixando {pl['pull']} ({pl['tamanho']})…", "pct": 0})
        oll.baixar(pl["pull"], lambda d: prog({"fase": "download", "msg": f"Baixando {pl['pull']}: {d['pct']}% · {d['mb_s']} MB/s", "pct": d["pct"]}),
                   cancelar, total_esperado=int(pl["bytes"]))
        baixou_agora = True
        novo = _achar_instalado(oll, pl["pull"])
        if not novo:
            raise ErroDesafio("O download terminou mas o modelo não apareceu no Ollama (tag diferente?).")
    prog({"fase": "sonda", "msg": f"Medindo VRAM e velocidade de {novo['id']}…"})
    boss = parque.maquina_local(parque.carregar_parque(False))
    vram_gb, sem_gpu = parque.memoria_modelo(boss)
    ctxs = sonda.degraus_sonda(novo, vram_gb, cpu=sem_gpu)
    def cb_sonda(**kw):
        m_txt = kw.get("msg", "")
        prog({"fase": "sonda", "msg": m_txt, "pct": kw.get("pct"), "feitos": kw.get("feitos"), "total": kw.get("total")})
    sonda.salvar_modelo(novo["id"], novo["digest"], sonda.sondar_modelo(oll, novo["id"], novo["digest"], ctxs, cb_sonda,
                                                                        cancelar=cancelar, enchimento_max=3072 if sem_gpu else 8192, cpu=sem_gpu))
    res = runner.executar(oll, [{"id": novo["id"], "digest": novo["digest"], "caps": novo["caps"]}], nivel, None, "base", prog, cancelar)
    if cancelar.is_set():
        raise ErroDesafio("cancelado")
    _exigir_medidos(res)
    inst = decide.modelos_do_boss(oll)
    salvo = decide.squad_salvo()
    sug = decide.titulares_sugeridos([m for m in inst if m["id"] != novo["id"]], salvo.get("titulares", {}))
    atuais = {pid: (salvo["titulares"].get(pid) or sug[pid]["modelo"]) for pid in sug}
    por_papel = _comparar_com_titulares(oll, novo, atuais, inst)
    c_nome = f"{pl['candidato']} ({pl['quant']})" if pull else pl["candidato"]
    rec, txt = _texto_resumo(c_nome, por_papel)
    v = {"id": f"{slug(novo['id'])}-{int(time.time())}", "quando": agora_iso(), "candidato": {"id": novo["id"], "digest": novo["digest"], "nome": c_nome, "pull": pl["pull"], "bytes": novo["bytes"]},
         "baixado_agora": baixou_agora, "nivel": nivel, "protocolo": PROTOCOLO, "por_papel": por_papel, "recomendacao": rec,
         "titulo": f"Resultado do teste: {c_nome}", "resumo": txt, "pendente": True,
         "medido": resultados.resumo(novo["id"], novo["digest"]), "sonda": sonda.da_sonda(novo["id"], novo["digest"])}
    todos = decide.vereditos()
    todos.append(v)
    gravar_json(config.VEREDITOS, todos)
    prog({"fase": "concluido", "msg": txt, "veredito": v["id"]})
    return v


# ------------------------------------------------------------------ duelo direto A × B (com auto-pull)

def _resolver_modelo_duelo(oll: Ollama, ref: str, papel_id: str) -> Tuple[str, int]:
    """Transforma um nome/id (ex.: 'qwen3:8b', 'ollama:qwen3.8:9b', 'moondream', 'gpt-oss') em (pull_tag, bytes_esperados)."""
    ref = ref.strip()
    ja = _achar_instalado(oll, ref)
    if ja:
        return ja["id"], int(ja.get("bytes") or 0)
    snap = scout.ultimo()
    if snap:
        for c in snap.get("candidatos", []):
            if c["id"].lower() == ref.lower() or c["nome"].lower() == ref.lower():
                cfg = config.carregar()
                boss = parque.maquina_local(parque.carregar_parque(False))
                p = papeis.POR_ID.get(papel_id) or papeis.POR_ID["chat_pt"]
                enc = decide.encaixe_candidato(c, boss, p, cfg)
                if enc and enc.get("cabe"):
                    v = enc["variante"]
                    return v["pull"], int(v.get("bytes") or 0)
                if c.get("variantes"):
                    v = min(c["variantes"], key=lambda x: x["bytes"])
                    return v["pull"], int(v.get("bytes") or 0)
    pull = ref if ":" in ref else f"{ref}:latest"
    if not _PULL_OK.match(pull):
        raise ErroDesafio(f"Nome de modelo inválido: '{ref}'. Use uma tag como `qwen3:8b` ou `hf.co/autor/repo:Q4_K_M`.")
    pre = ollama_lib.preflight(pull)
    if not pre.get("ok") and not pre.get("sem_rede"):
        raise ErroDesafio(f"Não encontrei '{pull}' para download: {pre.get('erro', 'tag inexistente')}")
    return pull, int(pre.get("bytes_total") or 0)


def _garantir_instalado(oll: Ollama, ref: str, papel_id: str, prog: Callable[[dict], None],
                        cancelar: threading.Event) -> Tuple[dict, bool]:
    pull, bytes_esp = _resolver_modelo_duelo(oll, ref, papel_id)
    ja = _achar_instalado(oll, pull)
    if ja:
        return ja, False
    tam_txt = f" ({fmt_gb(bytes_esp)})" if bytes_esp else ""
    prog({"fase": "download", "msg": f"Baixando {pull}{tam_txt}…", "pct": 0})
    oll.baixar(pull, lambda d: prog({"fase": "download", "msg": f"Baixando {pull}: {d['pct']}% · {d['mb_s']} MB/s", "pct": d["pct"]}),
               cancelar, total_esperado=bytes_esp)
    novo = _achar_instalado(oll, pull)
    if not novo:
        raise ErroDesafio(f"Download de {pull} terminou, mas o modelo não apareceu no Ollama.")
    return novo, True


def duelo(oll: Ollama, ref_a: str, ref_b: str, papel_id: str = "chat_pt", nivel: str = "rapido",
          ao_progredir: Optional[Callable[[dict], None]] = None, cancelar: Optional[threading.Event] = None) -> dict:
    """Compara frente a frente o modelo A (desafiante) contra o modelo B (referência/titular).
    Se algum deles não estiver instalado, baixa automaticamente antes de rodar a bateria pareada."""
    prog = ao_progredir or (lambda d: None)
    cancelar = cancelar or threading.Event()
    if ref_a.strip().lower() == ref_b.strip().lower():
        raise ErroDesafio("Escolha dois modelos diferentes para o duelo.")
    ma, baixou_a = _garantir_instalado(oll, ref_a, papel_id, prog, cancelar)
    mb, baixou_b = _garantir_instalado(oll, ref_b, papel_id, prog, cancelar)
    if ma["id"] == mb["id"]:
        raise ErroDesafio(f"Os dois nomes apontam para o mesmo modelo instalado ({ma['id']}).")

    # Se algum dos dois ainda não tiver sonda de contexto, mede rapidamente os degraus (incluindo >32k se couber)
    boss = parque.maquina_local(parque.carregar_parque(False))
    vram_gb, sem_gpu = parque.memoria_modelo(boss)
    for m_sonda in (ma, mb):
        if cancelar.is_set():
            raise ErroDesafio("cancelado")
        if not sonda.da_sonda(m_sonda["id"], m_sonda["digest"]):
            ctxs = sonda.degraus_sonda(m_sonda, vram_gb, cpu=sem_gpu)
            sonda.salvar_modelo(m_sonda["id"], m_sonda["digest"],
                                sonda.sondar_modelo(oll, m_sonda["id"], m_sonda["digest"], ctxs, lambda s: prog({"fase": "sonda", "msg": s}),
                                                    cancelar=cancelar, enchimento_max=3072 if sem_gpu else 8192, cpu=sem_gpu))

    # Se o usuário escolheu uma função específica, roda as suítes dessa função (muito mais rápido e direto);
    # se escolheu 'todos', roda todas as suítes compatíveis.
    suites_alvo = None
    if papel_id and papel_id != "todos" and papel_id in papeis.POR_ID:
        suites_alvo = list(papeis.pesos_do_papel(papel_id).keys())

    res = runner.executar(oll, [{"id": ma["id"], "digest": ma["digest"], "caps": ma["caps"]},
                          {"id": mb["id"], "digest": mb["digest"], "caps": mb["caps"]}],
                    nivel, suites_alvo, "base", prog, cancelar)
    if cancelar.is_set():
        raise ErroDesafio("cancelado")
    _exigir_medidos(res)

    inst = decide.modelos_do_boss(oll)
    novo_inst = next((x for x in inst if x["id"] == ma["id"]), ma)
    adv_inst = next((x for x in inst if x["id"] == mb["id"]), mb)
    tit_map = {p["id"]: mb["id"] for p in papeis.PAPEIS}
    por_papel = _comparar_com_titulares(oll, novo_inst, tit_map, inst)
    rec, txt = _texto_resumo(ma["id"], por_papel, ref_nome=mb["id"])
    v = {
        "id": f"duelo-{slug(ma['id'])}-vs-{slug(mb['id'])}-{int(time.time())}",
        "tipo": "duelo",
        "quando": agora_iso(),
        "candidato": {
            "id": ma["id"],
            "digest": ma["digest"],
            "nome": f"{ma['id']} × {mb['id']}",
            "pull": ma["id"],
            "bytes": ma["bytes"],
            "tps": (novo_inst.get("medido") or {}).get("tps_mediana"),
            "ctx_gpu": (novo_inst.get("sonda") or {}).get("ctx_max_gpu"),
            "indice_pratico": (novo_inst.get("indice_pratico") or {}).get("total"),
        },
        "adversario": {
            "id": mb["id"],
            "digest": mb["digest"],
            "bytes": mb["bytes"],
            "tps": (adv_inst.get("medido") or {}).get("tps_mediana"),
            "ctx_gpu": (adv_inst.get("sonda") or {}).get("ctx_max_gpu"),
            "indice_pratico": (adv_inst.get("indice_pratico") or {}).get("total"),
        },
        "baixado_agora": baixou_a,
        "nivel": nivel, "protocolo": PROTOCOLO, "por_papel": por_papel, "recomendacao": rec,
        "titulo": f"Duelo: {ma['id']} × {mb['id']}", "resumo": txt, "pendente": True,
        "medido": resultados.resumo(ma["id"], ma["digest"]), "sonda": sonda.da_sonda(ma["id"], novo_inst["digest"]),
    }
    todos = decide.vereditos()
    todos.append(v)
    gravar_json(config.VEREDITOS, todos)
    prog({"fase": "concluido", "msg": txt, "veredito": v["id"]})
    return v


# ------------------------------------------------------------------ ações explícitas do usuário

def _exigir_medidos(res: dict) -> None:
    """Modelo que não carregou nesta máquina (arquitetura nova demais para o Ollama dela, falta de memória…) não pode virar veredito."""
    falhas = [f"{k}: {v['motivo']}" for k, v in (res or {}).items() if v.get("ok") is False and v.get("motivo")]
    if falhas:
        raise ErroDesafio("Não foi possível medir — " + "; ".join(falhas))


def promover(papel_id: str, modelo_id: str, motivo: str = "") -> dict:
    if papel_id not in papeis.POR_ID:
        raise ErroDesafio("Função desconhecida.")
    s = decide.squad_salvo()
    antes = s["titulares"].get(papel_id)
    s["titulares"][papel_id] = modelo_id
    s["historico"].append({"quando": agora_iso(), "papel": papel_id, "de": antes, "para": modelo_id, "motivo": motivo})
    gravar_json(config.SQUAD, s)
    return s


def aposentar(oll: Ollama, modelo: str, motivo: str = "", herdeiros: Optional[Dict[str, str]] = None) -> dict:
    herdeiros = dict(herdeiros or {})
    inst = decide.modelos_do_boss(oll)
    alvo = next((m for m in inst if m["id"] == modelo), None)
    if not alvo:
        raise ErroDesafio("Esse modelo não está instalado.")
    atuais, _ = decide.titulares_atuais(inst)
    titular_de = [pid for pid, mid in atuais.items() if mid == modelo]
    oll.remover(modelo)
    ficam = {m["id"] for m in inst if m["id"] != modelo}
    herdeiros = {pid: h for pid, h in herdeiros.items() if pid in titular_de and h in ficam}
    aposentados.registrar(modelo, alvo["digest"], alvo["bytes"], motivo, titular_de, herdeiros)
    for pid in titular_de:
        if pid in herdeiros:
            promover(pid, herdeiros[pid], f"herdeiro de {modelo} (aposentado)")
        else:
            salvo = decide.squad_salvo()
            if salvo["titulares"].get(pid) == modelo:
                salvo["titulares"].pop(pid, None)
                salvo["historico"].append({"quando": agora_iso(), "papel": pid, "de": modelo, "para": "—", "motivo": "aposentado, sem herdeiro indicado"})
                gravar_json(config.SQUAD, salvo)
    return {"ok": True, "removido": modelo, "liberou_bytes": alvo["bytes"], "titular_de": titular_de, "herdeiros": herdeiros}


def resolver_veredito(vid: str, acao: str, oll: Optional[Ollama] = None, confirmar_remocao: bool = False) -> dict:
    """acao: 'promover' (nas funções em que venceu) | 'manter' | 'descartar' (apaga o modelo — exige confirmação)."""
    todos = decide.vereditos()
    v = next((x for x in todos if x["id"] == vid), None)
    if not v:
        raise ErroDesafio("Veredito não encontrado.")
    feitos = []
    if acao == "promover":
        for pid, r in v["por_papel"].items():
            if r.get("veredito") == "superior" or (r.get("veredito") == "empate" and r.get("eficiencia")):
                promover(pid, v["candidato"]["id"], f"teste {v['id']}: {r['veredito']}")
                feitos.append(pid)
    elif acao == "descartar":
        if not confirmar_remocao:
            raise ErroDesafio("Remover o modelo apaga arquivos do disco: confirme explicitamente.")
        if not oll:
            raise ErroDesafio("Ollama indisponível.")
        aposentar(oll, v["candidato"]["id"], "descartado após o teste: " + v.get("resumo", ""))
        feitos.append("removido")
    elif acao != "manter":
        raise ErroDesafio("Ação inválida.")
    v["pendente"] = False
    v["resolvido"] = {"acao": acao, "quando": agora_iso(), "efeitos": feitos}
    gravar_json(config.VEREDITOS, todos)
    return v
