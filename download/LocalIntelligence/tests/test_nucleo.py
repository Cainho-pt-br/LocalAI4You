"""Testes do núcleo (sem rede, sem Ollama real): memória, estatística, corretores, parsers e decisão.

    python -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import config, decide, fit, papeis, scout  # noqa: E402
from li.bench import pontuacao as P  # noqa: E402
from li.bench import stats  # noqa: E402
from li.fontes import ollama_lib  # noqa: E402
from li.util import GB  # noqa: E402

BOSS = {"id": "boss", "gpu": {"vram_gb": 15.9, "bw_gbs": 448}, "ram_gb": 32, "simd": ["avx2"]}
PI = {"id": "pi", "ram_gb": 3.7, "reserva_so_gb": 2.2, "max_modelo_gb": 1.4, "bw_gbs_min": 3, "bw_gbs_max": 5, "simd": ["neon"]}
# config.json real do Qwen3.8-27B: 64 camadas, 16 de atenção cheia, 4 cabeças KV, head_dim 256
ARCH_Q38 = fit.arch_de_config_hf({"text_config": {"num_hidden_layers": 64, "num_key_value_heads": 4, "head_dim": 256,
                                                  "num_attention_heads": 24, "hidden_size": 5120, "max_position_embeddings": 262144,
                                                  "layer_types": (["linear_attention"] * 3 + ["full_attention"]) * 16}})


class TestFit(unittest.TestCase):
    def test_quant_de_nome(self):
        self.assertEqual(fit.quant_de_nome("Qwen3.8-27B-UD-IQ3_S.gguf"), "UD-IQ3_S")
        self.assertEqual(fit.quant_de_nome("model-Q4_K_M.gguf"), "Q4_K_M")
        self.assertEqual(fit.quant_de_nome("gpt-oss-20b-MXFP4.gguf"), "MXFP4")
        self.assertEqual(fit.quant_de_nome("x-BF16.gguf"), "BF16")
        self.assertIsNone(fit.quant_de_nome("mmproj.gguf"))

    def test_kv_qwen38_so_cobra_camadas_de_atencao_cheia(self):
        # 16 camadas × 4 cabeças × (256+256) × 2 bytes = 64 KiB por token em f16
        kv = fit.kv_bytes(ARCH_Q38, 32768, "f16") - int(fit.ESTADO_LINEAR_GB * GB)
        self.assertAlmostEqual(kv / 32768, 65536, delta=2)
        self.assertLess(fit.kv_bytes(ARCH_Q38, 32768, "q8_0"), fit.kv_bytes(ARCH_Q38, 32768, "f16"))

    def test_janela_deslizante_limita_o_kv(self):
        arch = {"camadas": 24, "kv_heads": 8, "key_len": 64, "val_len": 64, "janela": 128, "arquitetura": "gptoss"}
        self.assertLess(fit.kv_bytes(arch, 131072), fit.kv_bytes({**arch, "janela": None}, 131072) * 0.6)

    def test_27b_cabe_em_iq3_mas_nao_em_q4(self):
        q4 = fit.avaliar_encaixe(16_460_000_000, ARCH_Q38, BOSS, 16384)
        iq3 = fit.avaliar_encaixe(12_040_000_000, ARCH_Q38, BOSS, 16384)
        self.assertEqual(q4["nivel"], "justo" if q4["ctx_max"] >= 4096 else "nao_cabe")
        self.assertNotEqual(q4["nivel"], "confortavel")
        self.assertEqual(iq3["nivel"], "confortavel")

    def test_escolher_variante_ignora_bf16_e_iq1(self):
        vs = [{"quant": "IQ1_S", "bytes": int(0.9e9), "pull": "a"}, {"quant": "Q4_K_M", "bytes": int(3.4e9), "pull": "b"},
              {"quant": "Q8_0", "bytes": int(5.1e9), "pull": "c"}, {"quant": "BF16", "bytes": int(9.3e9), "pull": "d"}]
        arch = {"camadas": 32, "kv_heads": 4, "key_len": 256, "val_len": 256, "intervalo_atencao_cheia": 4}
        v = fit.escolher_variante(vs, BOSS, arch, 8192, 4.7)
        self.assertIn(v["quant"], ("Q8_0", "Q4_K_M"))
        self.assertNotIn(v["quant"], ("BF16", "IQ1_S"))

    def test_escolher_variante_cpu_prefere_q4(self):
        vs = [{"quant": "Q4_K_M", "bytes": int(0.5e9), "pull": "a"}, {"quant": "Q8_0", "bytes": int(0.8e9), "pull": "b"}]
        arch = {"camadas": 28, "kv_heads": 8, "key_len": 128, "val_len": 128}
        v = fit.escolher_variante(vs, PI, arch, 4096, 0.75)
        self.assertEqual(v["quant"], "Q4_K_M")  # CPU: teto de ~5 bits por peso

    def test_modelo_grande_nao_cabe_no_pi(self):
        arch = {"camadas": 32, "kv_heads": 8, "key_len": 128, "val_len": 128}
        self.assertEqual(fit.avaliar_encaixe(int(5e9), arch, PI, 4096)["nivel"], "nao_cabe")

    def test_tps_gpu_denso_na_faixa_medida(self):
        # qwen2.5-coder 14B Q4 (9 GB) mediu 35–42 tok/s na RTX 5060 Ti
        lo, hi = fit.estimar_tps(9_000_000_000, BOSS, False)
        self.assertLessEqual(lo, 35)
        self.assertGreaterEqual(hi, 42)

    def test_ativos_de_nome(self):
        self.assertEqual(fit.ativos_de_nome("Qwen3.6-35B-A3B"), 3.0)
        self.assertEqual(fit.ativos_de_nome("gemma-4-26B-A4B-it"), 4.0)
        self.assertIsNone(fit.ativos_de_nome("Qwen3.8-27B"))

    def test_faixas_de_qualidade(self):
        self.assertEqual(fit.faixa_qualidade(4.5)[0], "excelente")
        self.assertEqual(fit.faixa_qualidade(2.0)[0], "degradada")


class TestStats(unittest.TestCase):
    def test_wilson(self):
        lo, hi = stats.wilson(14, 16)
        self.assertLess(lo, 87.5)
        self.assertGreater(hi, 87.5)
        self.assertEqual(stats.wilson(0, 0), (0.0, 100.0))
        self.assertGreater(stats.wilson(30, 30)[0], 85)

    def test_composto_renormaliza_pesos(self):
        c = stats.composto({"a": [1, 1], "b": [0, 0]}, {"a": 0.5, "b": 0.5, "c": 0.5})
        self.assertEqual(c, 50.0)

    def test_pareado_identicos_empatam(self):
        itens = {f"i{k}": k % 2 for k in range(40)}
        c = stats.comparar_pareado({"s": itens}, {"s": dict(itens)}, {"s": 1.0})
        self.assertEqual(c["dif"], 0)
        self.assertEqual(stats.veredito_pareado(c), "empate")

    def test_pareado_claramente_melhor(self):
        a = {f"i{k}": 1 for k in range(60)}
        b = {f"i{k}": 1 if k % 2 else 0 for k in range(60)}
        c = stats.comparar_pareado({"s": a}, {"s": b}, {"s": 1.0})
        self.assertEqual(stats.veredito_pareado(c), "superior")
        self.assertEqual(c["so_b"], 0)

    def test_pareado_diferenca_pequena_e_ruido(self):
        a = {f"i{k}": 1 if k % 10 else 0 for k in range(30)}
        b = {f"i{k}": 1 if (k + 1) % 10 else 0 for k in range(30)}  # mesma taxa, itens trocados
        c = stats.comparar_pareado({"s": a}, {"s": b}, {"s": 1.0})
        self.assertEqual(stats.veredito_pareado(c), "empate")


class TestPontuacao(unittest.TestCase):
    def test_letra(self):
        self.assertEqual(P.extrair_letra("C", "ABCDE"), "C")
        self.assertEqual(P.extrair_letra("Resposta: B", "ABCDE"), "B")
        self.assertEqual(P.extrair_letra("A resposta correta é a alternativa **D**.", "ABCDE"), "D")
        self.assertEqual(P.extrair_letra("<think>talvez A</think>\nE", "ABCDE"), "E")
        self.assertEqual(P.extrair_letra("A banana é amarela. A", "ABCDE"), "A")

    def test_bfcl_opcional_pode_ser_omitido(self):
        gt = [{"get_user": {"id": [7890], "special": ["black", ""]}}]
        self.assertTrue(P.chamada_correta("get_user", {"id": 7890}, gt)[0])
        self.assertTrue(P.chamada_correta("get_user", {"id": 7890, "special": "Black"}, gt)[0])
        self.assertFalse(P.chamada_correta("get_user", {"id": 1}, gt)[0])
        self.assertFalse(P.chamada_correta("get_user", {"id": 7890, "inventado": 1}, gt)[0])
        self.assertFalse(P.chamada_correta("outra", {"id": 7890}, gt)[0])

    def test_bfcl_prompt_com_cerca_markdown(self):
        gt = [{"f": {"x": [1]}}]
        self.assertTrue(P.bfcl_prompt('```json\n{"tool":"f","arguments":{"x":1}}\n```', gt)[0])
        self.assertFalse(P.bfcl_prompt("não sei", gt)[0])

    def test_ifeval_regras_oficiais(self):
        self.assertTrue(P.ifeval("keywords:frequency", {"keyword": "a", "frequency": 2, "relation": "less than"}, "a"))
        self.assertFalse(P.ifeval("keywords:frequency", {"keyword": "a", "frequency": 2, "relation": "less than"}, "a a"))
        self.assertTrue(P.ifeval("detectable_format:number_bullet_lists", {"num_bullets": 2}, "* um\n* dois"))
        self.assertFalse(P.ifeval("detectable_format:number_bullet_lists", {"num_bullets": 2}, "* um\n* dois\n- três"))
        self.assertTrue(P.ifeval("detectable_format:json_format", {}, '```json\n{"a":1}\n```'))
        self.assertTrue(P.ifeval("startend:end_checker", {"end_phrase": "Fim."}, '"texto fim."'))

    def test_gsm8k(self):
        self.assertTrue(P.gsm8k("1,200 maçãs\n#### 1200", "1200")[0])
        self.assertTrue(P.gsm8k("a resposta final é $72.00", "72")[0])
        self.assertFalse(P.gsm8k("#### 71", "72")[0])

    def test_humaneval_executa_e_bloqueia(self):
        it = {"id": "x", "prompt": 'from typing import List\n\ndef f(a: List[int]) -> int:\n    """soma"""\n',
              "teste": "def check(c):\n    assert c([1,2])==3\n", "entrada": "f"}
        self.assertTrue(P.humaneval(it, "```python\ndef f(a):\n    return sum(a)\n```")[0])
        self.assertFalse(P.humaneval(it, "```python\ndef f(a):\n    return 0\n```")[0])
        self.assertTrue(P.humaneval(it, "    return sum(a)")[0])
        ok, why = P.humaneval(it, "```python\nimport os\ndef f(a):\n    os.system('echo oi')\n    return 3\n```")
        self.assertFalse(ok)
        self.assertIn("bloqueado", why)
        ok, why = P.humaneval(it, "```python\ndef f(a):\n    while True: pass\n```")
        self.assertFalse(ok)


class TestParsersOllama(unittest.TestCase):
    def test_listagem(self):
        html = (RAIZ / "tests" / "fixtures" / "ollama_library.html").read_text("utf-8")
        itens = ollama_lib._parse_listagem(html)
        self.assertEqual(len(itens), 2)
        nomes = {i["nome"] for i in itens}
        self.assertTrue({"llama3.1", "qwen3.5"} & nomes)
        for i in itens:
            self.assertGreater(i["pulls"], 1000)
            self.assertTrue(i["tamanhos"])

    def test_tags(self):
        html = (RAIZ / "tests" / "fixtures" / "ollama_tags_gemma4.html").read_text("utf-8")
        t = ollama_lib._parse_tags(html, "gemma4")
        self.assertTrue(t)
        self.assertTrue(all(x["bytes"] > 1e9 for x in t))
        self.assertTrue(any(x["ctx"] and x["ctx"] >= 131072 for x in t))

    def test_params(self):
        self.assertAlmostEqual(ollama_lib.parse_params_b("9.7B"), 9.7)
        self.assertAlmostEqual(ollama_lib.parse_params_b("335M"), 0.335)
        self.assertEqual(ollama_lib.parse_params_b("8x7b"), 56.0)


class TestScout(unittest.TestCase):
    def test_chave_familia(self):
        self.assertEqual(scout.chave_familia("Qwen3.8-27B"), "qwen38")
        self.assertEqual(scout.chave_familia("qwen3.8"), "qwen38")
        self.assertEqual(scout.chave_familia("google/gemma-4-26B-A4B-it"), "gemma4")
        self.assertEqual(scout.chave_familia("gemma4"), "gemma4")

    def test_tamanho_de_nome_hf(self):
        self.assertEqual(scout.tamanho_de_nome_hf("gemma-4-26B-A4B-it"), "26b-a4b")
        self.assertEqual(scout.tamanho_de_nome_hf("Qwen3.8-27B"), "27b")

    def test_papeis_provaveis(self):
        self.assertEqual(scout.papeis_provaveis("qwen2.5-coder 14b", ["tools"], 14)[0], "codigo")
        self.assertNotIn("chat_pt", scout.papeis_provaveis("qwen2.5-coder 14b", ["tools"], 14))
        p = scout.papeis_provaveis("qwen3.8 27b", ["vision", "tools", "thinking"], 27)
        self.assertIn("chat_pt", p)  # modelo geral com visão continua servindo para conversa
        self.assertIn("codigo", p)
        self.assertEqual(scout.papeis_provaveis("qwen3-vl 8b", ["vision", "tools"], 8), ["visao"])      # VL no nome = visão primeiro
        self.assertEqual(scout.papeis_provaveis("LFM2.5-VL-3B", ["vision"], 3.1), ["visao"])
        self.assertIn("chat_pt", scout.papeis_provaveis("gemma4 12b", ["vision", "tools"], 12))        # geral com visão nativa

    def test_especializado(self):
        self.assertTrue(scout.eh_especializado("UI-Mate-27B", ["computer-use-agent", "gui-agent"]))
        self.assertTrue(scout.eh_especializado("x", ["ocr"]))
        self.assertIsNone(scout.eh_especializado("granite-4.2-8b", ["reasoning", "tool-calling", "conversational"]))
        for nome in ("granite-guardian-4.1-8b", "SingGuard-2b", "Llama Guard 4"):          # classificadores de segurança não conversam
            self.assertTrue(scout.eh_especializado(nome, []), nome)
        self.assertTrue(scout.eh_especializado("tev1 4B", [], "A 4B decision model from Together AI for fast classification."))
        self.assertIsNone(scout.eh_especializado("vanguard-7b", []))


def _cand(nome, params, **kw):
    base = {"id": "hf:" + nome, "origem": "ollama", "familia": nome.split(":")[0], "tamanho": f"{int(params)}b", "nome": nome,
            "descricao": "", "caps": ["tools"], "params_b": params, "ativos_b": None, "moe": False, "ctx_max": 32768, "dias": 20.0,
            "lancamento": "2026-09-10", "novo": True, "confianca": "ollama-oficial", "pulls": 2_000_000, "papeis": ["chat_pt", "regras", "agente", "codigo"],
            "arch": {"camadas": 36, "kv_heads": 8, "key_len": 128, "val_len": 128},
            "variantes": [{"tag": "q4", "pull": f"{nome}:q4", "quant": "Q4_K_M", "bytes": int(params * 0.6e9)}]}
    base.update(kw)
    return base


class TestCatalogoInicial(unittest.TestCase):
    """O ZIP traz um catálogo: o Radar funciona antes da primeira varredura, e a varredura local sempre vence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ant = (config.SNAPSHOTS, config.CATALOGO_INICIAL)
        config.SNAPSHOTS = Path(self.tmp.name) / "snapshots"
        config.SNAPSHOTS.mkdir()
        config.CATALOGO_INICIAL = Path(self.tmp.name) / "radar-inicial.json.gz"

    def tearDown(self):
        config.SNAPSHOTS, config.CATALOGO_INICIAL = self.ant
        self.tmp.cleanup()

    def test_usa_o_embutido_so_sem_varredura_local(self):
        self.assertIsNone(scout.ultimo())                                       # sem nada: radar vazio, sem erro
        snap = {"criado": "2026-01-01T00:00:00Z", "total": 1, "fontes": {"ollama": True}, "candidatos": [
            {"id": "ollama:x:4b", "nome": "x 4B", "origem": "ollama", "caps": [], "lancamento": "2025-01-01T00:00:00Z", "dias": 3, "novo": True}]}
        scout.gravar_catalogo_inicial(snap)
        a = scout.gravar_catalogo_inicial(snap).read_bytes()
        self.assertEqual(a, scout.gravar_catalogo_inicial(snap).read_bytes())  # determinístico: o workflow só commita mudança real
        u = scout.ultimo()
        self.assertTrue(u["embutido"])
        self.assertGreater(u["candidatos"][0]["dias"], 300)                      # idade recalculada para hoje
        self.assertFalse(u["candidatos"][0]["novo"])
        self.assertTrue(decide._resumo_radar(u)["embutido"])
        (config.SNAPSHOTS / "ultimo-completo.json").write_text(json.dumps({**snap, "criado": "2026-02-01T00:00:00Z"}), "utf-8")
        self.assertFalse(scout.ultimo().get("embutido"))                        # varredura local vence

    def test_o_zip_traz_um_catalogo_valido(self):
        config.CATALOGO_INICIAL = self.ant[1]
        if not config.CATALOGO_INICIAL.exists():
            self.skipTest("catálogo inicial ainda não gerado")
        u = scout.catalogo_inicial()
        self.assertGreater(len(u["candidatos"]), 50)
        self.assertTrue(all(c.get("variantes") or c.get("sem_gguf") for c in u["candidatos"]))   # sem arquivo baixável só se marcado


class TestDecisao(unittest.TestCase):
    def setUp(self):
        self.snap = {"criado": "2026-10-01T00:00:00+00:00", "total": 4, "fontes": {}, "candidatos": [
            _cand("bom:9b", 9), _cand("ui:9b", 9, especializado="ui-mate", origem="hf", baixas=50000),
            _cand("pouco:9b", 9, origem="hf", baixas=300), _cand("gigante:70b", 70)]}

    def test_filtros_de_candidatos(self):
        lst = decide.candidatos_para(BOSS, [], self.snap, "chat_pt")
        ids = [c["nome"] for c in lst]
        self.assertIn("bom:9b", ids)
        self.assertNotIn("ui:9b", ids)        # especializado
        self.assertNotIn("pouco:9b", ids)     # sem adoção
        self.assertNotIn("gigante:70b", ids)  # não cabe

    def test_prioridade_em_faixa_e_explica(self):
        c = self.snap["candidatos"][0]
        enc = decide.encaixe_candidato(c, BOSS, papeis.POR_ID["chat_pt"], config.carregar())
        pr = decide.prioridade(c, papeis.POR_ID["chat_pt"], enc, [], BOSS)
        self.assertTrue(0 <= pr["pontos"] <= 100)
        self.assertTrue(pr["razoes"])

    def test_comunidade_pontua_menos(self):
        a, b = _cand("a:9b", 9), _cand("b:9b", 9, confianca="comunidade")
        enc = decide.encaixe_candidato(a, BOSS, papeis.POR_ID["chat_pt"], config.carregar())
        pa = decide.prioridade(a, papeis.POR_ID["chat_pt"], enc, [], BOSS)["pontos"]
        pb = decide.prioridade(b, papeis.POR_ID["chat_pt"], enc, [], BOSS)["pontos"]
        self.assertGreater(pa, pb)

    def test_familia_versao(self):
        self.assertEqual(decide._familia_versao("qwen3.5:9b"), ("qwen", 3.5))
        self.assertEqual(decide._familia_versao("qwen3.8"), ("qwen", 3.8))
        self.assertEqual(decide._familia_versao("gemma4:12b"), ("gemma", 4.0))


class TestTitulares(unittest.TestCase):
    def test_empate_mantem_o_atual(self):
        import li.resultados as R
        with tempfile.TemporaryDirectory() as d:
            orig = config.RESULTADOS
            config.RESULTADOS = Path(d) / "r.jsonl"
            try:
                def pon(modelo, ok_fn):
                    for s in ("mmlu_pt", "capitu", "ifeval", "mmlu_pro"):
                        for i in range(30):
                            R.anexar({"modelo": modelo, "digest": "d" + modelo, "suite": s, "item": f"{s}{i}", "modo": "base",
                                      "valido": True, "ok": ok_fn(i), "tps": 50})
                pon("a", lambda i: i % 4 != 0)
                pon("b", lambda i: i % 4 != 1 or i in (1, 5))  # 2 itens a mais que "a", itens diferentes → empate técnico
                inst = [{"id": m, "digest": "d" + m, "caps": ["tools"], "bytes": 5 * GB, "medido": R.resumo(m, "d" + m)} for m in ("a", "b")]
                sug = decide.titulares_sugeridos(inst, {"chat_pt": "a"})
                self.assertEqual(sug["chat_pt"]["modelo"], "a")
                self.assertIn("empate", sug["chat_pt"]["motivo"])
            finally:
                config.RESULTADOS = orig


if __name__ == "__main__":
    unittest.main()


class TestJobs(unittest.TestCase):
    def setUp(self):
        import li.jobs as J
        self.J = J
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = config.PROGRESSO
        config.PROGRESSO = Path(self.tmp.name) / "p.json"

    def tearDown(self):
        config.PROGRESSO = self.orig
        self.tmp.cleanup()

    def _grava(self, **kw):
        from li.util import agora_iso, gravar_json
        d = {"fase": "rodando", "pid": 1, "atualizado": agora_iso(), "titulo": "x"}
        d.update(kw)
        gravar_json(config.PROGRESSO, d)

    def test_trava_externa_por_batimento(self):
        self.assertIsNone(self.J.externo())
        self._grava()
        self.assertIsNotNone(self.J.externo())
        self._grava(atualizado="2020-01-01T00:00:00+00:00")
        self.assertIsNone(self.J.externo())          # batimento velho = processo morto
        self._grava(fase="concluido")
        self.assertIsNone(self.J.externo())
        import os
        self._grava(pid=os.getpid())
        self.assertIsNone(self.J.externo())          # a própria tarefa não se bloqueia

    def test_tarefa_pesada_uma_por_vez_e_respeita_o_terminal(self):
        import threading
        g = self.J.Gerente()
        solta = threading.Event()
        g.iniciar("bench", "primeira", lambda ctx: solta.wait(5))
        with self.assertRaises(RuntimeError):
            g.iniciar("sonda", "segunda", lambda ctx: None)
        g.iniciar("varredura", "leve passa", lambda ctx: None)   # tarefa leve não é bloqueada
        solta.set()
        import time
        for _ in range(50):
            if not g.pesado_em_andamento():
                break
            time.sleep(0.05)
        self._grava(titulo="bench no terminal")
        with self.assertRaises(RuntimeError) as cm:
            g.iniciar("bench", "terceira", lambda ctx: None)
        self.assertIn("terminal", str(cm.exception))

    def test_erro_na_tarefa_nao_derruba(self):
        import time
        g = self.J.Gerente()
        j = g.iniciar("varredura", "quebra", lambda ctx: 1 / 0)
        for _ in range(50):
            if j.estado != "rodando":
                break
            time.sleep(0.05)
        self.assertEqual(j.estado, "erro")
        self.assertIn("ZeroDivisionError", j.erro)


class TestParque(unittest.TestCase):
    PARQUE = {"maquinas": [
        {"id": "boss", "nome": "boss", "gpu": {"vram_gb": 15.9, "bw_gbs": 448}, "ram_gb": 32, "simd": ["avx2"], "local": True},
        {"id": "pi", "nome": "pi", "ram_gb": 3.7, "reserva_so_gb": 2.2, "max_modelo_gb": 1.4, "bw_gbs_min": 3, "bw_gbs_max": 5, "simd": ["neon"]},
        {"id": "celeron", "nome": "celeron", "ram_gb": 7.9, "reserva_so_gb": 3.5, "max_modelo_gb": 2.5, "bw_gbs_min": 5, "bw_gbs_max": 8, "simd": ["sse"]},
    ]}

    def snap(self):
        peq = _cand("pequeno:0b", 0.8, tamanho="0.8b", pulls=3_000_000, caps=[], papeis=["chat_pt", "regras", "rapido"],
                    variantes=[{"tag": "q4", "pull": "pequeno:q4", "quant": "Q4_K_M", "bytes": int(0.55e9)}])
        med = _cand("medio:9b", 9, papeis=["chat_pt", "regras", "agente", "codigo"])
        return {"criado": "2026-10-01T00:00:00+00:00", "total": 2, "fontes": {}, "candidatos": [peq, med]}

    def test_classes(self):
        classes = {m["id"]: decide.classe_da_maquina(m)["classe"] for m in self.PARQUE["maquinas"]}
        self.assertEqual(classes, {"boss": "forte", "pi": "mínima", "celeron": "mínima"})  # celeron: sem AVX/NEON → mínima

    def test_recomendacoes_respeitam_o_limite_de_cada_maquina(self):
        recs = {e["maquina"]["id"]: e for e in decide.recomendacoes_parque(self.snap(), None, pk=self.PARQUE)}
        todos_pi = [x["nome"] for lst in recs["pi"]["papeis"].values() for x in lst]
        self.assertIn("pequeno:0b", todos_pi)
        self.assertNotIn("medio:9b", todos_pi)           # 5,4 GB não cabe no limite de 1,4 GB do Pi
        todos_boss = [x["nome"] for lst in recs["boss"]["papeis"].values() for x in lst]
        self.assertIn("medio:9b", todos_boss)

    def test_kit_tem_modelos_distintos(self):
        recs = {e["maquina"]["id"]: e for e in decide.recomendacoes_parque(self.snap(), None, pk=self.PARQUE)}
        ids = [k["candidato"]["id"] for k in recs["boss"]["kit"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(recs["boss"]["kit"])

    def test_sem_radar_nao_quebra(self):
        recs = decide.recomendacoes_parque(None, None, pk=self.PARQUE)
        self.assertEqual(len(recs), 3)
        self.assertTrue(all(e["papeis"] == {} for e in recs))


class TestPreflight(unittest.TestCase):
    def test_tag_inexistente_e_pega_antes_de_baixar(self):
        from li.fontes import ollama_lib
        from li.util import ErroHTTP
        orig = ollama_lib.http_json
        chamadas = []

        def falso(url, **kw):
            chamadas.append(url)
            if "IQ3_M" in url:
                raise ErroHTTP("HTTP 400")
            return {"layers": [{"mediaType": "application/vnd.ollama.image.model", "size": 12_000_000_000},
                               {"mediaType": "application/vnd.ollama.image.projector", "size": 900_000_000},
                               {"mediaType": "application/vnd.ollama.image.params", "size": 67}]}
        ollama_lib.http_json = falso
        try:
            ok = ollama_lib.preflight("hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S")
            self.assertTrue(ok["ok"])
            self.assertEqual(ok["bytes_total"], 12_900_000_067)       # o projetor de visão também é baixado
            self.assertEqual(ok["bytes_projetor"], 900_000_000)
            self.assertIn("huggingface.co/v2/unsloth/Qwen3.8-27B-GGUF/manifests/UD-IQ3_S", chamadas[0])
            ruim = ollama_lib.preflight("hf.co/unsloth/Qwen3.8-27B-GGUF:IQ3_M")
            self.assertFalse(ruim["ok"])
            self.assertIn("não conhece", ruim["erro"])
            lib = ollama_lib.preflight("qwen3.5:9b")
            self.assertIn("registry.ollama.ai/v2/library/qwen3.5/manifests/9b", chamadas[-1])
            self.assertTrue(lib["ok"])
        finally:
            ollama_lib.http_json = orig


class TestAmostras(unittest.TestCase):
    def test_ids_unicos_em_todos_os_niveis(self):
        from li.bench import amostras
        for suite in amostras.NIVEIS["padrao"]:
            for nivel in amostras.NIVEIS:
                ids = [x["id"] for x in amostras.itens_do_nivel(suite, nivel)]
                self.assertEqual(len(ids), len(set(ids)), f"{suite}/{nivel} tem id repetido (os resultados colapsariam)")

    def test_niveis_sao_prefixos_um_do_outro(self):
        from li.bench import amostras
        for suite in amostras.NIVEIS["padrao"]:
            r = [x["id"] for x in amostras.itens_do_nivel(suite, "rapido")]
            p = [x["id"] for x in amostras.itens_do_nivel(suite, "padrao")]
            self.assertEqual(p[:len(r)], r, suite)  # resultados de níveis diferentes se comparam nos itens em comum


class TestRitmo(unittest.TestCase):
    def test_ritmo_recente_e_previsao(self):
        from datetime import datetime, timedelta, timezone
        agora = datetime.now(timezone.utc)
        def dt(dias):
            return (agora - timedelta(days=dias)).isoformat()
        cands = [_cand("x", 9, origem="ollama", familia=f, lancamento=dt(d), data_aproximada=False)
                 for f, d in (("zeta2", 400), ("zeta3", 200), ("zeta3.5", 100), ("zeta4", 40))]
        cands.append(_cand("aprox", 9, origem="ollama", familia="zeta9", lancamento=dt(5), data_aproximada=True))   # data aproximada não conta
        cands.append(_cand("coder", 9, origem="ollama", familia="zeta-coder", lancamento=dt(3), data_aproximada=False))  # variante especializada não conta
        r = decide.ritmo_familias({"candidatos": cands}, [{"id": "zeta3:9b"}])
        self.assertEqual(len(r), 1)
        self.assertEqual([v["nome"] for v in r[0]["versoes"]], ["zeta2", "zeta3", "zeta3.5", "zeta4"])
        self.assertEqual(r[0]["intervalo_medio_dias"], 80)         # média dos 2 últimos intervalos (100 e 60)
        self.assertEqual(r[0]["proxima_em_dias"], 40)               # 80 − 40 dias desde a última
        self.assertEqual(decide.ritmo_familias(None, []), [])
