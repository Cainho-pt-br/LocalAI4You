"""Explorador de quantizações, aba Medir (o que vale rodar), bateria de Visão, Duelo A×B e regra de custo-benefício.

    python -m unittest tests.test_quants_lab -v        (sem rede e sem GPU)
"""
import base64
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import aposentados, config, decide, desafio, lab, parque, quants, resultados  # noqa: E402
from li.bench import amostras, pontuacao, visao_gerador  # noqa: E402
from li.fontes import hf  # noqa: E402
from li.util import agora_iso, gravar_json  # noqa: E402

GB = 1_000_000_000


def _linha(modelo, nota, bytes_, titular=False, vs=None, atende=True, tps=50):
    return {"modelo": modelo, "nota": nota, "ic": [nota - 5, nota + 5], "atende": atende, "titular": titular, "tps": tps, "bytes": int(bytes_),
            "vs_titular": None if titular else {"veredito": vs, "dif": 0.0, "ic": [-3, 3]}}


def _inst(*ids_bytes):
    return [{"id": i, "bytes": int(b), "digest": "d-" + i, "medido": {"n_itens": 295}} for i, b in ids_bytes]


class TestCustoBeneficio(unittest.TestCase):
    """O gpt-oss:20b (13,8 GB) "liderava" Raciocínio por 1,4 ponto, dentro do ruído, sobre um modelo de 6,6 GB: tem de poder sair."""

    def setUp(self):
        self.inst = _inst(("grande:20b", 13.8 * GB), ("pequeno:9b", 6.6 * GB), ("tit:12b", 7.6 * GB))

    def _ranking(self, vs_pequeno="empate", vs_grande_chat="empate", vs_tit="empate"):
        return {"raciocinio": [_linha("grande:20b", 80.3, 13.8 * GB, titular=True), _linha("pequeno:9b", 78.9, 6.6 * GB, vs=vs_pequeno), _linha("tit:12b", 77.5, 7.6 * GB, vs=vs_tit)],
                "chat_pt": [_linha("tit:12b", 84.6, 7.6 * GB, titular=True), _linha("grande:20b", 80.1, 13.8 * GB, vs=vs_grande_chat), _linha("pequeno:9b", 83.4, 6.6 * GB, vs="empate")]}

    def test_lider_so_por_empate_com_modelo_bem_menor_pode_sair(self):
        d = decide.dispensaveis(self.inst, self._ranking())
        self.assertEqual([x["modelo"] for x in d], ["grande:20b"])
        self.assertEqual(d[0]["tipo"], "custo")
        self.assertEqual(d[0]["herdeiros"], {"raciocinio": "pequeno:9b"})
        self.assertIn("52% menor", d[0]["motivo"])

    def test_herdeiro_pior_que_o_titular_nao_serve(self):
        self.assertEqual(decide.dispensaveis(self.inst, self._ranking(vs_pequeno="inferior", vs_tit="inferior")), [])

    def test_quem_vence_com_folga_em_algum_lugar_fica(self):
        self.assertEqual(decide.dispensaveis(self.inst, self._ranking(vs_grande_chat="superior")), [])

    def test_herdeiro_precisa_ser_30_por_cento_menor(self):
        inst = _inst(("grande:20b", 13.8 * GB), ("quase:14b", 11.0 * GB))
        rk = {"raciocinio": [_linha("grande:20b", 80, 13.8 * GB, titular=True), _linha("quase:14b", 79, 11.0 * GB, vs="empate")]}
        self.assertEqual(decide.dispensaveis(inst, rk), [])

    def test_sem_medir_todos_nao_decide(self):
        inst = self.inst + [{"id": "novo:3b", "bytes": 2 * GB, "digest": "x", "medido": None}]
        self.assertEqual(decide.dispensaveis(inst, self._ranking()), [])


class _Isolado(unittest.TestCase):
    """Estado de execução num diretório temporário (nunca toca o estado real)."""

    CHAVES = ("ESTADO", "RESULTADOS", "SONDAS", "APOSENTADOS", "SNAPSHOTS", "CACHE", "SQUAD", "VEREDITOS")

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.antigos = {k: getattr(config, k) for k in cls.CHAVES}
        config.ESTADO, config.RESULTADOS, config.SONDAS = base, base / "r.jsonl", base / "s.json"
        config.APOSENTADOS, config.SQUAD, config.CACHE = base / "ap.json", base / "sq.json", base / "cache"
        config.VEREDITOS = base / "vereditos.json"
        config.SNAPSHOTS = base / "snap"
        config.SNAPSHOTS.mkdir()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.antigos.items():
            setattr(config, k, v)
        cls.tmp.cleanup()


class TestAposentados(_Isolado):
    def test_medido_e_ausente_vira_aposentado_com_notas(self):
        for s, n in amostras.NIVEIS["rapido"].items():
            for k in range(n):
                resultados.anexar({"modelo": "sumiu:9b", "digest": "dg1", "suite": s, "item": f"i{k}", "modo": "base", "valido": True, "ok": k % 2 == 0, "tps": 40})
        aposentados.registrar("registrado:3b", "dg2", 3 * GB, "teste", ["rapido"], {"rapido": "outro"})
        lista = aposentados.listar(_inst(("fica:12b", 7 * GB)))
        por = {a["modelo"]: a for a in lista}
        self.assertIn("sumiu:9b", por)
        self.assertFalse(por["sumiu:9b"]["registrado"])              # apagado fora do painel: sem data, mas com as notas
        self.assertGreater(por["sumiu:9b"]["n_itens"], 100)
        self.assertTrue(por["sumiu:9b"]["papeis"])
        self.assertEqual(por["registrado:3b"]["herdeiros"], {"rapido": "outro"})
        self.assertEqual(por["registrado:3b"]["bytes"], 3 * GB)
        # se o mesmo arquivo (mesmo digest) estiver instalado, não é aposentado
        de_volta = aposentados.listar([{"id": "sumiu:9b", "digest": "dg1", "bytes": 5 * GB}])
        self.assertNotIn("sumiu:9b", [a["modelo"] for a in de_volta])
        # tag atualizada (digest novo): a medição é de uma versão antiga e isso é avisado
        velho = {a["modelo"]: a for a in aposentados.listar([{"id": "sumiu:9b", "digest": "dg-novo", "bytes": 5 * GB}])}
        self.assertTrue(velho["sumiu:9b"]["versao_antiga"])


class _OllFalso:
    def __init__(self, ms):
        self.ms = ms

    def no_ar(self):
        return True

    def instalados(self):
        return self.ms


class TestPlanoDeMedicao(_Isolado):
    def _medir(self, modelo, nivel, digest):
        for s, n in amostras.NIVEIS[nivel].items():
            if s == "visao":
                continue
            for k in range(n):
                resultados.anexar({"modelo": modelo, "digest": digest, "suite": s, "item": f"i{k}", "modo": "base", "valido": True, "ok": True, "tps": 50, "lat": 2.0})

    def test_o_que_vale_rodar_agora(self):
        ms = [{"id": n, "bytes": 5 * GB, "digest": "d-" + n, "caps": ["tools"], "arch": {}, "params": "5B", "quant": "Q4_K_M"} for n in ("vazio:5b", "raso:5b", "pleno:5b")]
        self._medir("raso:5b", "rapido", "d-raso:5b")
        self._medir("pleno:5b", "padrao", "d-pleno:5b")
        gravar_json(config.SONDAS, {"pleno:5b": {"digest": "d-pleno:5b", "ctx": {"4096": {"ok": True, "gpu_integral": True, "tps": 50, "pct_gpu": 100, "total_bytes": GB, "leitura_tps": 900}}}})
        pl = lab.plano(_OllFalso(ms))
        passos = {p["id"]: p for p in pl["passos"]}
        self.assertEqual(passos["medir-novos"]["modelos"], ["vazio:5b"])
        self.assertEqual(passos["aprofundar-rapido"]["modelos"], ["raso:5b"])
        self.assertEqual(passos["sonda"]["tipo"], "sonda")
        self.assertEqual(set(passos["sonda"]["modelos"]), {"vazio:5b", "raso:5b"})
        self.assertTrue(passos["medir-novos"]["recomendado"] and passos["medir-novos"]["minutos"] >= 1)
        niveis = {m["id"]: m["nivel"] for m in pl["modelos"]}
        self.assertEqual((niveis["vazio:5b"], niveis["raso:5b"], niveis["pleno:5b"]), (None, "rapido", "padrao"))
        self.assertEqual(len(pl["testes"]), 9)
        self.assertTrue(all(t["mede"] for t in pl["testes"]))

    def test_modelo_sem_ferramentas_nao_e_cobrado_pelo_teste_que_nao_pode_fazer(self):
        # sem 'tools' e sem 'vision', bfcl_native e visao são pulados
        n = sum(v for s, v in amostras.NIVEIS["padrao"].items() if s not in ("bfcl_native", "visao", "visao_leve", "visao_fotos"))
        self.assertEqual(lab._esperado([], "padrao"), n)
        self.assertEqual(lab._nivel_atingido(n, []), "padrao")
        self.assertEqual(lab._nivel_atingido(n, ["tools"]), "rapido")


class TestVisaoGeradorEPontuacao(unittest.TestCase):
    def test_gera_18_itens_png_validos_e_corrige_respostas(self):
        itens = visao_gerador.construir_itens()
        self.assertEqual(len(itens), 18)
        # Intercalado: primeiros 6 (nível rápido) têm 2 de cada categoria
        cats_rapido = [x["categoria"] for x in itens[:6]]
        self.assertEqual(cats_rapido.count("ocr_nota"), 2)
        self.assertEqual(cats_rapido.count("grafico"), 2)
        self.assertEqual(cats_rapido.count("painel"), 2)
        raw = base64.b64decode(itens[0]["imagem"])
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        for it in itens:
            ok, det = pontuacao.visao(it, f"A resposta correta é {it['resposta']}.")
            self.assertTrue(ok, f"Falhou para {it['id']}: {det}")
            ok_err, _ = pontuacao.visao(it, "Não consigo ver a imagem.")
            self.assertFalse(ok_err)

    def test_maquina_local_universal(self):
        m = parque.maquina_local({"maquinas": [{"id": "custom-pc", "nome": "Meu PC", "local": True, "ram_gb": 16}]})
        self.assertEqual(m["id"], "custom-pc")
        m_vazio = parque.maquina_local({"maquinas": []})
        self.assertTrue(m_vazio["local"])


class TestExplorarQuantizacoes(_Isolado):
    def setUp(self):
        c = {"id": "ollama:fam:9b", "origem": "ollama", "familia": "fam", "tamanho": "9b", "nome": "fam 9B", "descricao": "", "caps": ["tools", "vision"], "params_b": 9.0,
             "ativos_b": None, "moe": False, "ctx_max": 131072, "dias": 30.0, "lancamento": agora_iso(), "confianca": "ollama-oficial", "pulls": 1_000_000,
             "papeis": ["chat_pt"], "repo": "Lab/Fam-9B", "arch": {"camadas": 32, "kv_heads": 8, "key_len": 128, "val_len": 128, "ctx_max": 131072},
             "variantes": [{"tag": "9b", "pull": "fam:9b", "quant": "Q4_K_M", "bytes": 6 * GB, "padrao": True},
                           {"tag": "9b-q8_0", "pull": "fam:9b-q8_0", "quant": "Q8_0", "bytes": 10 * GB}]}
        gravar_json(config.SNAPSHOTS / "ultimo-completo.json", {"criado": agora_iso(), "total": 1, "fontes": {}, "candidatos": [c]})
        self._hf = (hf.repos_gguf_do_base, hf.arquivos_gguf)
        hf.repos_gguf_do_base = lambda base, limite=25: [
            {"id": "unsloth/Fam-9B-GGUF", "downloads": 900}, {"id": "bartowski/Fam-9B-GGUF", "downloads": 500},
            {"id": "alguem-aleatorio/Fam-9B-GGUF", "downloads": 9999}, {"id": "Lab/Fam-9B-FP8", "downloads": 10}]
        hf.arquivos_gguf = lambda repo, forcar=False: {"variantes": [{"quant": "UD-IQ3_S", "arquivo": "x-IQ3_S.gguf", "bytes": 4 * GB, "partes": 1},
                                                                     {"quant": "Q4_K_M", "arquivo": "x-Q4_K_M.gguf", "bytes": 5_500_000_000, "partes": 1}], "mmproj_bytes": 800_000_000}

    def tearDown(self):
        hf.repos_gguf_do_base, hf.arquivos_gguf = self._hf

    def test_lista_ollama_e_quantizadores_confiaveis_com_links_do_hf(self):
        r = quants.explorar("ollama:fam:9b")
        nomes = [f["nome"] for f in r["fontes"]]
        self.assertEqual(nomes[0], "Biblioteca do Ollama (oficial)")
        self.assertIn("unsloth/Fam-9B-GGUF", nomes)
        self.assertIn("bartowski/Fam-9B-GGUF", nomes)
        self.assertNotIn("alguem-aleatorio/Fam-9B-GGUF", nomes)       # só quantizador conhecido ou o próprio laboratório
        uns = next(f for f in r["fontes"] if f["nome"].startswith("unsloth"))
        v = next(x for x in uns["variantes"] if x["quant"] == "UD-IQ3_S")
        self.assertEqual(v["pull"], "hf.co/unsloth/Fam-9B-GGUF:UD-IQ3_S")
        self.assertEqual(v["extra_bytes"], 800_000_000)               # modelo com visão: o projetor entra na conta
        self.assertTrue(r["links"]["ollama"].startswith("https://ollama.com/library/fam"))
        self.assertEqual(r["links"]["hf_base"], "https://huggingface.co/Lab/Fam-9B")
        self.assertIn("base_model:quantized:Lab/Fam-9B", r["links"]["hf_quantizados"])
        self.assertIn("camadas_tipo", r["candidato"]["arch"])

    def test_sem_rede_devolve_o_que_o_radar_ja_tinha(self):
        def quebra(*a, **k):
            raise OSError("sem rede")
        hf.repos_gguf_do_base = quebra
        r = quants.explorar("ollama:fam:9b")
        self.assertTrue(r["aviso"])
        self.assertEqual(r["fontes"][0]["nome"], "Biblioteca do Ollama (oficial)")

    def test_candidato_inexistente(self):
        with self.assertRaises(quants.ErroQuants):
            quants.explorar("ollama:nao-existe:1b")


class TestTarefasPesadas(unittest.TestCase):
    def test_tudo_que_baixa_ou_mede_corre_sozinho(self):
        from li import jobs
        for tipo in ("bench", "sonda", "desafio", "duelo", "atualizar", "download", "exportar", "verificar"):
            self.assertIn(tipo, jobs.PESADAS, tipo)  # duelo e atualizar ficaram de fora e podiam rodar junto com um benchmark


class TestSondaSemGpu(unittest.TestCase):
    def test_cpu_nunca_sonda_contexto_gigante(self):
        from li import parque
        from li.bench import sonda
        m = {"bytes": 1_050_000_000, "ctx_max": 131072}
        self.assertEqual(max(sonda.degraus_sonda(m, 1.4, cpu=True)), 32768)             # CPU: nunca passa de 32k sem pedido explícito (128k travaria a máquina)
        pequeno = dict(m, arch={"camadas": 18, "kv_heads": 1, "key_len": 256, "val_len": 256, "ctx_max": 131072})
        self.assertEqual(max(sonda.degraus_sonda(pequeno, 4.0, cpu=True, ate_ctx=65536)), 65536)
        self.assertLess(max(sonda.degraus_sonda(pequeno, 1.4, cpu=True)), 32768)   # Pi (1,4 GB): o KV de 32k não cabe junto do modelo
        grande = {"bytes": 5_000_000_000, "ctx_max": 131072}
        self.assertEqual(sonda.degraus_sonda(grande, 4.6, cpu=True), [4096])            # modelo não cabe na RAM: só o degrau mínimo
        denso = {"bytes": 2_000_000_000, "ctx_max": 131072,
                 "arch": {"camadas": 28, "kv_heads": 8, "key_len": 128, "val_len": 128}}  # KV grande: o contexto é limitado pela RAM
        self.assertLess(max(sonda.degraus_sonda(denso, 3.0, cpu=True)), 32768)
        self.assertGreater(max(sonda.degraus_sonda(denso, 16.0, cpu=True)), max(sonda.degraus_sonda(denso, 3.0, cpu=True)))
        self.assertIn(131072, sonda.degraus_sonda(m, 16.0, cpu=False))                  # GPU grande continua testando contexto longo
        pi = next(x for x in parque.carregar_parque(False)["maquinas"] if x["id"] == "raspberrypi")
        mem, sem_gpu = parque.memoria_modelo(pi)
        self.assertTrue(sem_gpu)
        self.assertLessEqual(mem, 1.5)                                                   # respeita max_modelo_gb do Pi, não os 16 GB do boss


class TestCancelamentoEmVoo(unittest.TestCase):
    def test_cancelar_derruba_requisicao_em_andamento(self):
        import http.server
        import threading
        import time
        from li.ollama import Cancelado, Ollama

        class Lento(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(8)          # um prompt de 8k na CPU
                try:
                    self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Lento)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            o = Ollama(f"http://127.0.0.1:{srv.server_address[1]}")
            ev = threading.Event()
            o.cancelar = ev
            threading.Timer(0.5, ev.set).start()
            t0 = time.time()
            with self.assertRaises(Cancelado):
                o.chat("x", [{"role": "user", "content": "oi"}], timeout=30)
            self.assertLess(time.time() - t0, 3)       # voltou em ~0,5 s, não em 8 s
        finally:
            srv.shutdown()


class TestNivelPorHardware(unittest.TestCase):
    def test_pi_nao_recebe_o_padrao_e_o_boss_sim(self):
        from li import parque
        from li.bench import amostras, custo
        pk = parque.carregar_parque(False)["maquinas"]
        pi = next(x for x in pk if x["id"] == "raspberrypi")
        boss = next(x for x in pk if x["id"] == "boss")
        pesos = [1_100_000_000, 1_000_000_000, 1_700_000_000]
        self.assertEqual(custo.recomendado(pi, pesos), "minimo")                       # CPU de 4 GB: horas por modelo no padrão
        self.assertEqual(custo.limitar(pi, pesos, "padrao"), "minimo")                  # pedido pesado é reduzido sozinho
        self.assertEqual(custo.recomendado(boss, [9_000_000_000] * 3), "padrao")        # GPU: continua o padrão de sempre
        self.assertEqual(custo.limitar(boss, [9_000_000_000] * 2, "padrao"), "padrao")
        ids = list(amostras.NIVEIS)
        self.assertEqual(ids[0], "minimo")
        for suite, n in amostras.NIVEIS["minimo"].items():                              # mínimo é prefixo do rápido: mesmos itens congelados
            self.assertLessEqual(n, amostras.NIVEIS["rapido"][suite])


class TestModeloQueNaoCarrega(unittest.TestCase):
    def test_duelo_com_modelo_que_nao_carrega_vira_erro_claro(self):
        from li import desafio
        from li.bench import runner
        with self.assertRaises(desafio.ErroDesafio) as c:
            desafio._exigir_medidos({"lfm": {"ok": False, "motivo": runner._motivo_gate({"erro": "error loading model: unknown model architecture: 'lfm3'"})}})
        self.assertIn("Ollama desta máquina", str(c.exception))
        desafio._exigir_medidos({"x": {"ok": True, "feitos": 3}})   # modelo medido: nada a dizer

    def test_reserva_do_painel_vale_sem_gpu(self):
        from li import fit
        pi = {"ram_gb": 3.7, "reserva_so_gb": 2.2, "max_modelo_gb": 4}
        self.assertAlmostEqual(fit.orcamento_bytes(pi) / fit.GIB, 1.5, 1)                # padrão: reserva do parque.json
        self.assertAlmostEqual(fit.orcamento_bytes(pi, 1.0) / fit.GIB, 2.7, 1)           # “1 GB livre” definido no painel


class TestVisaoLeve(unittest.TestCase):
    def test_benchmark_padrao_inclui_visao_para_quem_enxerga(self):
        from li.bench import amostras, runner, suites

        class Oll:
            cancelar = None
            def descarregar(self, m): pass
        pedidos = []
        orig = amostras.itens_do_nivel
        amostras.itens_do_nivel = lambda s, n: pedidos.append(s) or []
        try:
            r = runner.executar(Oll(), [{"id": "x", "digest": "d", "caps": ["completion"]}, {"id": "y", "digest": "d", "caps": ["completion", "vision"]}], "minimo")
        finally:
            amostras.itens_do_nivel = orig
        self.assertIn("visao_leve", pedidos)                                       # entra sem ninguém pedir
        self.assertTrue(any(p["suite"] == "visao_leve" for p in r["x"]["pulados"]))  # quem não enxerga é pulado, com o motivo
        self.assertFalse(any(p["suite"] == "visao_leve" for p in r["y"]["pulados"]))

    def test_itens_balanceados_e_deterministicos(self):
        import base64
        from li.bench import amostras, visao_gerador
        a = visao_gerador.construir_itens_leve(30)
        self.assertEqual([i["id"] for i in a], [i["id"] for i in visao_gerador.construir_itens_leve(30)])
        self.assertEqual(a[0]["imagem"], visao_gerador.construir_itens_leve(30)[0]["imagem"])      # congelado: mesma imagem sempre
        self.assertEqual({i["categoria"] for i in a[:5]}, {"contagem", "cor", "forma", "posicao", "leitura"})   # até o nível mínimo tem os 5 tipos
        self.assertTrue(base64.b64decode(a[0]["imagem"]).startswith(bytes([137]) + b"PNG"))
        self.assertEqual(len(amostras.itens_do_nivel("visao_leve", "minimo")), 5)

    def test_pontuacao_aceita_palavra_e_portugues_mas_nao_chute(self):
        from li.bench import pontuacao as P
        casos = [({"tipo": "contagem", "resposta": "7"}, "There are seven seeds.", True), ({"tipo": "contagem", "resposta": "12"}, "I count 11.", False),
                 ({"tipo": "cor", "resposta": "red"}, "The shape is Red.", True), ({"tipo": "forma", "resposta": "circle"}, "A square, not a circle", False),
                 ({"tipo": "lado", "resposta": "right"}, "À direita", True), ({"tipo": "cor", "resposta": "blue"}, "I cannot tell", False)]
        for item, resp, esperado in casos:
            self.assertEqual(P.visao_leve(item, resp)[0], esperado, (item, resp))

    def test_fotos_do_usuario_com_gabarito_e_detector(self):
        import json
        import tempfile
        from pathlib import Path
        from li.bench import visao_gerador
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            self.assertEqual(visao_gerador.itens_fotos(pasta), [])                                   # sem gabarito: nada, sem erro
            (pasta / "a.jpg").write_bytes(bytes([255, 216]) + b"fake")
            (pasta / "gabarito.json").write_text(json.dumps({"a.jpg": {"contagem": 23, "detector": 22}, "sumiu.jpg": {"contagem": 3}, "x.jpg": {"detector": 1}}), "utf-8")
            itens = visao_gerador.itens_fotos(pasta)
            self.assertEqual(len(itens), 1)
            self.assertEqual((itens[0]["resposta"], itens[0]["detector"]), ("23", 22))


if __name__ == "__main__":
    unittest.main()


class TestRadarFamiliasRecentes(unittest.TestCase):
    def test_familia_nova_com_poucos_downloads_nao_e_cortada_por_popularidade(self):
        from datetime import datetime, timedelta, timezone
        from li import scout
        agora = datetime.now(timezone.utc)
        iso = lambda d: (agora - timedelta(days=d)).isoformat(timespec="minutes")
        velhas = [{"nome": f"classico{i}", "caps": [], "tamanhos": ["7b"], "pulls": 5_000_000 - i, "atualizado": iso(300), "descricao": ""} for i in range(150)]
        novas = [{"nome": f"novo{i}", "caps": [], "tamanhos": ["2b"], "pulls": 900 + i, "atualizado": iso(5), "descricao": ""} for i in range(6)]
        lidas = []
        orig = (scout.ollama_lib.listar, scout._variantes_ollama)
        scout.ollama_lib.listar = lambda ordem, forcar=False: velhas + novas      # a página "newest" do Ollama devolve a biblioteca inteira
        scout._variantes_ollama = lambda nome, desc, caps: lidas.append(nome) or {}
        try:
            scout.candidatos_ollama(False, 110, lambda s: None)
        finally:
            scout.ollama_lib.listar, scout._variantes_ollama = orig
        self.assertTrue(all(f"novo{i}" in lidas for i in range(6)), "família recente com poucos downloads ficou de fora")
        self.assertLessEqual(len(lidas), 110 + 6)
