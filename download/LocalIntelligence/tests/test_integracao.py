"""Testes de integração com um Ollama FALSO (servidor HTTP local): cliente, download com progresso,
execução de itens, retentativa de resposta vazia, kit offline e segurança do painel.

    python -m unittest discover -s tests -v
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import config, offline, ollama  # noqa: E402
from li.bench import suites  # noqa: E402
from li.ollama import ErroOllama, Ollama  # noqa: E402


class OllamaFalso(BaseHTTPRequestHandler):
    chamadas = []

    def log_message(self, *a):
        pass

    def _json(self, d, status=200):
        b = json.dumps(d).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "0.0-fake"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "fake:1b", "model": "fake:1b", "size": 1_000_000, "digest": "abc",
                                           "modified_at": "2026-10-01T00:00:00Z", "details": {"family": "qwen35", "parameter_size": "1B", "quantization_level": "Q4_K_M"}}]})
        if self.path == "/api/ps":
            return self._json({"models": [{"name": "fake:1b", "size": 1000, "size_vram": 1000, "context_length": 8192}]})
        self._json({"error": "nao"}, 404)

    def do_DELETE(self):
        OllamaFalso.chamadas.append(("delete", self.rfile.read(int(self.headers.get("Content-Length", 0)))))
        self._json({})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/show":
            return self._json({"capabilities": ["completion", "tools", "thinking"],
                               "model_info": {"general.architecture": "qwen35", "qwen35.block_count": 32, "qwen35.attention.head_count_kv": 4,
                                              "qwen35.attention.head_count": 16, "qwen35.embedding_length": 4096, "qwen35.attention.key_length": 256,
                                              "qwen35.full_attention_interval": 4, "qwen35.context_length": 262144, "general.parameter_count": 9_000_000_000}})
        if self.path == "/api/pull":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            modelo = corpo["model"]
            linhas = [{"status": "pulling manifest"}]
            if modelo == "quebra:1b":
                linhas.append({"error": "pull model manifest: file does not exist"})
            else:
                for dg, tot in (("sha256:aaa", 100), ("sha256:bbb", 300)):
                    for pct in (0, 50, 100):
                        linhas.append({"status": f"pulling {dg[:10]}", "digest": dg, "total": tot, "completed": tot * pct // 100})
                linhas += [{"status": "verifying sha256 digest"}, {"status": "writing manifest"}, {"status": "success"}]
            for l in linhas:
                self.wfile.write((json.dumps(l) + "\n").encode())
                self.wfile.flush()
                time.sleep(0.01)
            return
        if self.path == "/api/chat":
            OllamaFalso.chamadas.append(("chat", corpo))
            if not corpo.get("messages"):
                return self._json({"message": {"content": ""}, "done": True})
            maxt = corpo.get("options", {}).get("num_predict", 512)
            texto = corpo["messages"][-1]["content"]
            if "VAZIO" in texto and maxt < 2000:  # simula modelo que "pensa" até estourar o orçamento
                return self._json({"message": {"content": "", "thinking": "..."}, "eval_count": maxt, "eval_duration": 10**9, "prompt_eval_count": 50})
            if corpo.get("tools"):
                f = corpo["tools"][0]["function"]
                return self._json({"message": {"content": "", "tool_calls": [{"function": {"name": f["name"], "arguments": {"x": 1}}}]},
                                   "eval_count": 30, "eval_duration": 10**9, "prompt_eval_count": 80})
            return self._json({"message": {"content": "B"}, "eval_count": 40, "eval_duration": 10**9, "prompt_eval_count": 60})
        self._json({"error": "nao"}, 404)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), OllamaFalso)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.o = Ollama(f"http://127.0.0.1:{cls.porta}")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()


class TestCliente(Base):
    def test_basico(self):
        self.assertTrue(self.o.no_ar())
        self.assertEqual(self.o.versao(), "0.0-fake")
        self.assertFalse(Ollama("http://127.0.0.1:9").no_ar(timeout=0.5))

    def test_instalados_extrai_capacidades_e_arquitetura(self):
        m = self.o.instalados()[0]
        self.assertEqual(m["id"], "fake:1b")
        self.assertIn("tools", m["caps"])
        self.assertEqual(m["arch"]["camadas"], 32)
        self.assertEqual(m["arch"]["intervalo_atencao_cheia"], 4)
        self.assertEqual(m["ctx_max"], 262144)

    def test_download_agrega_progresso_das_camadas(self):
        vistos = []
        self.o.baixar("fake:1b", vistos.append)
        pcts = [v["pct"] for v in vistos if v["total"]]
        self.assertEqual(pcts[-1], 100.0)
        self.assertEqual(pcts, sorted(pcts))  # nunca anda para trás
        self.assertEqual(vistos[-1]["status"], "success")

    def test_download_com_erro_vira_excecao(self):
        with self.assertRaises(ErroOllama) as cm:
            self.o.baixar("quebra:1b")
        self.assertIn("does not exist", str(cm.exception))

    def test_download_cancelavel(self):
        ev = threading.Event()
        ev.set()
        with self.assertRaises(ErroOllama):
            self.o.baixar("fake:1b", None, ev)

    def test_remover(self):
        self.o.remover("fake:1b")
        self.assertEqual(OllamaFalso.chamadas[-1][0], "delete")


class TestSuites(Base):
    def test_mcq_acerta_e_registra_metricas(self):
        item = {"id": "x", "dominio": "d", "enunciado": "Q?", "rotulos": list("ABCDE"), "textos": list("12345"), "resposta": "B"}
        r = suites.executar_item(self.o, "mmlu_pt", "fake:1b", item, 8192)
        self.assertTrue(r["ok"])
        self.assertTrue(r["valido"])
        self.assertEqual(r["tps"], 40.0)

    def test_resposta_vazia_por_orcamento_repete_com_mais_tokens(self):
        item = {"id": "x", "dominio": "d", "enunciado": "VAZIO", "rotulos": list("ABCDE"), "textos": list("12345"), "resposta": "B"}
        OllamaFalso.chamadas.clear()
        r = suites.executar_item(self.o, "mmlu_pt", "fake:1b", item, 8192)
        self.assertTrue(r["ok"])
        self.assertTrue(r["reintentou"])
        self.assertEqual(len([c for c in OllamaFalso.chamadas if c[0] == "chat"]), 2)

    def test_prompt_truncado_nao_conta_como_erro_do_modelo(self):
        item = {"id": "x", "dominio": "d", "enunciado": "Q?", "rotulos": list("ABCDE"), "textos": list("12345"), "resposta": "B"}
        r = suites.executar_item(self.o, "mmlu_pt", "fake:1b", item, 70)  # ctx 70, prompt 60 → perto do limite
        self.assertFalse(r["valido"])

    def test_bfcl_nativo_le_tool_calls(self):
        item = {"id": "b", "tipo": "simple", "pergunta": [[{"role": "user", "content": "faça"}]],
                "funcoes": [{"name": "f", "description": "d", "parameters": {"type": "dict", "properties": {"x": {"type": "integer"}}}}],
                "gt": [{"f": {"x": [1]}}]}
        r = suites.executar_item(self.o, "bfcl_native", "fake:1b", item, 8192)
        self.assertTrue(r["ok"], r)

    def test_erro_de_conexao_nao_pune_o_modelo(self):
        item = {"id": "x", "dominio": "d", "enunciado": "Q?", "rotulos": list("ABCDE"), "textos": list("12345"), "resposta": "B"}
        r = suites.executar_item(Ollama("http://127.0.0.1:9"), "mmlu_pt", "fake:1b", item, 8192)
        self.assertFalse(r["valido"])
        self.assertIn("erro", r["det"])


class TestOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.modelos = base / "ollama"
        (self.modelos / "blobs").mkdir(parents=True)
        self.conteudo = b"pesos-do-modelo" * 1000
        self.digest = "sha256:" + hashlib.sha256(self.conteudo).hexdigest()
        (self.modelos / "blobs" / self.digest.replace(":", "-")).write_bytes(self.conteudo)
        man = self.modelos / "manifests" / "registry.ollama.ai" / "library" / "teste" / "1b"
        man.parent.mkdir(parents=True)
        man.write_text(json.dumps({"layers": [{"mediaType": "application/vnd.ollama.image.model", "digest": self.digest, "size": len(self.conteudo)}]}))
        self.antigo = os.environ.get("OLLAMA_MODELS")
        os.environ["OLLAMA_MODELS"] = str(self.modelos)
        self.destino = base / "kit"

    def tearDown(self):
        if self.antigo is None:
            os.environ.pop("OLLAMA_MODELS", None)
        else:
            os.environ["OLLAMA_MODELS"] = self.antigo
        self.tmp.cleanup()

    def test_blobs_e_tamanho(self):
        b = ollama.blobs_do_modelo("teste:1b")
        self.assertEqual(len(b), 1)
        self.assertTrue(b[0]["tamanho_ok"])

    def test_manifest_de_nome_com_ponto_nao_vira_registro(self):
        self.assertIn("library", str(ollama.caminho_manifest("qwen3.5:9b")))
        self.assertIn("hf.co", str(ollama.caminho_manifest("hf.co/unsloth/X-GGUF:Q4_K_M")))

    def test_exportar_kit_copia_e_gera_guia(self):
        r = offline.exportar_kit(str(self.destino), ["teste:1b"])
        self.assertTrue(r["ok"])
        self.assertTrue((self.destino / "RESTAURAR.md").exists())
        self.assertTrue((self.destino / "usar-sem-instalar.bat").exists())
        blob = self.destino / "models" / "blobs" / self.digest.replace(":", "-")
        self.assertEqual(blob.read_bytes(), self.conteudo)
        self.assertTrue((self.destino / "models" / "manifests" / "registry.ollama.ai" / "library" / "teste" / "1b").exists())
        # o kit é restaurável: o mesmo leitor de manifesto enxerga os arquivos copiados
        self.assertTrue(all(b["tamanho_ok"] for b in ollama.blobs_do_modelo("teste:1b", self.destino / "models")))

    def test_estado_do_kit_reconhece_modelo_em_dia_e_ausente(self):
        offline.exportar_kit(str(self.destino), ["teste:1b"])
        e = offline._estado_kit(str(self.destino), [{"id": "teste:1b"}, {"id": "outro:7b"}])
        self.assertTrue(e["existe"])
        self.assertEqual(e["modelos"]["teste:1b"], "em dia")
        self.assertEqual(e["modelos"]["outro:7b"], "ausente")
        self.assertFalse(e["instalador"])
        (self.destino / "OllamaSetup.exe").write_bytes(b"x")
        self.assertTrue(offline._estado_kit(str(self.destino), [])["instalador"])
        blob = self.destino / "models" / "blobs" / self.digest.replace(":", "-")
        blob.write_bytes(b"truncado")
        self.assertEqual(offline._estado_kit(str(self.destino), [{"id": "teste:1b"}])["modelos"]["teste:1b"], "incompleto")

    def test_exportar_recusa_destino_dentro_da_pasta_de_modelos(self):
        with self.assertRaises(ValueError):
            offline.exportar_kit(str(self.modelos / "kit"), ["teste:1b"])

    def test_verificacao_profunda_detecta_corrupcao(self):
        self.assertTrue(offline.verificar_profundo("teste:1b")["ok"])
        blob = self.modelos / "blobs" / self.digest.replace(":", "-")
        blob.write_bytes(self.conteudo[:-1] + b"X")  # mesmo tamanho, byte diferente
        self.assertFalse(offline.verificar_profundo("teste:1b")["ok"])


class TestSegurancaDoPainel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from li import server
        cls.porta = 18991
        server.Handler.porta = cls.porta
        cls.srv = ThreadingHTTPServer(("127.0.0.1", cls.porta), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, caminho, metodo="GET", headers=None, corpo=None):
        h = {"Host": f"127.0.0.1:{self.porta}"}
        h.update(headers or {})
        r = urllib.request.Request(f"http://127.0.0.1:{self.porta}{caminho}", method=metodo, headers=h, data=corpo)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_host_estranho_barrado(self):
        self.assertEqual(self.req("/api/config", headers={"Host": "evil.example"})[0], 421)

    def test_post_sem_cabecalho_ou_com_origem_estranha_barrado(self):
        self.assertEqual(self.req("/api/cancelar", "POST", corpo=b"{}")[0], 403)
        self.assertEqual(self.req("/api/cancelar", "POST", {"X-LI": "1", "Origin": "http://evil.example"}, b"{}")[0], 403)
        self.assertEqual(self.req("/api/cancelar", "POST", {"X-LI": "1", "Origin": f"http://127.0.0.1:{self.porta}"}, b"{}")[0], 200)

    def test_sem_cors(self):
        r = urllib.request.Request(f"http://127.0.0.1:{self.porta}/api/config", headers={"Host": f"127.0.0.1:{self.porta}"})
        with urllib.request.urlopen(r) as resp:
            self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))

    def test_so_serve_a_pasta_web(self):
        self.assertEqual(self.req("/index.html")[0], 200)
        for p in ("/../cli.py", "/%2e%2e/cli.py", "/estado/resultados.jsonl", "/li/config.py"):
            self.assertEqual(self.req(p)[0], 404, p)

    def test_acoes_destrutivas_pedem_confirmacao(self):
        h = {"X-LI": "1"}
        self.assertEqual(self.req("/api/remover", "POST", h, json.dumps({"modelo": "x"}).encode())[0], 400)
        self.assertEqual(self.req("/api/desafio", "POST", h, json.dumps({"candidato": "x"}).encode())[0], 400)
        self.assertEqual(self.req("/api/baixar", "POST", h, json.dumps({"pull": "x"}).encode())[0], 400)

    def test_nome_de_modelo_com_shell_injection_recusado(self):
        h = {"X-LI": "1"}
        c = json.dumps({"pull": "x; rm -rf /", "confirmo_download": True}).encode()
        self.assertEqual(self.req("/api/baixar", "POST", h, c)[0], 400)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.name == "nt", "o problema do SO_REUSEADDR é do Windows")
class TestPortaExclusiva(unittest.TestCase):
    def test_segunda_instancia_do_painel_nao_divide_a_porta(self):
        from li import server
        a = server.Servidor(("127.0.0.1", 0), server.Handler)
        try:
            porta = a.server_address[1]
            with self.assertRaises(OSError):
                server.Servidor(("127.0.0.1", porta), server.Handler)
        finally:
            a.server_close()


class TestThinkBase(unittest.TestCase):
    def test_modelo_que_ignora_think_false_usa_esforco_low(self):
        class Falso:
            def __init__(self, ignora, aceita_low=True):
                self.ignora, self.aceita_low, self.vistos = ignora, aceita_low, []

            def chat(self, modelo, msgs, **kw):
                self.vistos.append(kw.get("think"))
                if kw.get("think") == "low" and not self.aceita_low:
                    raise ErroOllama("HTTP 400")
                return {"message": {"content": "4", "thinking": "..." if (self.ignora and kw.get("think") is False) else ""}}
        self.assertFalse(suites.descobrir_think_base(Falso(ignora=False), "m"))              # obedece: continua False
        f = Falso(ignora=True)
        self.assertEqual(suites.descobrir_think_base(f, "m"), "low")                        # ignora: usa 'low'
        self.assertEqual(f.vistos, [False, "low"])
        self.assertFalse(suites.descobrir_think_base(Falso(ignora=True, aceita_low=False), "m"))  # nem 'low' aceita: segue False


class TestQuantsESonda(unittest.TestCase):
    def test_achar_instalado_nao_confunde_quantizacoes_diferentes_do_mesmo_repo(self):
        from li import desafio

        class OllMock:
            def instalados(self):
                return [{"id": "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S", "bytes": 12_000_000_000, "digest": "d1"}]

        oll = OllMock()
        # Mesma quantização: deve achar
        m1 = desafio._achar_instalado(oll, "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S")
        self.assertIsNotNone(m1)
        # Outra quantização explícita (:Q3_K_M ou :IQ3_M): NÃO deve casar com a :UD-IQ3_S!
        m2 = desafio._achar_instalado(oll, "hf.co/unsloth/Qwen3.8-27B-GGUF:Q3_K_M")
        self.assertIsNone(m2)
        # Sem tag explícita: pode casar com o instalado daquele repositório
        m3 = desafio._achar_instalado(oll, "hf.co/unsloth/Qwen3.8-27B-GGUF")
        self.assertIsNotNone(m3)

    def test_degraus_sonda_inclui_64k_e_128k_conforme_tamanho(self):
        from li.bench import sonda
        from li.util import GB
        # Modelo leve (6.6 GB em GPU de 16 GB): deve incluir 64k e 128k
        deg_leve = sonda.degraus_sonda({"bytes": int(6.6 * GB), "ctx_max": 131072}, vram_gb=16.0)
        self.assertIn(65536, deg_leve)
        self.assertIn(131072, deg_leve)
        # Modelo médio-grande (12 GB em GPU de 16 GB): deve incluir 64k, mas não 128k por padrão
        deg_medio = sonda.degraus_sonda({"bytes": int(12.0 * GB), "ctx_max": 131072}, vram_gb=16.0)
        self.assertIn(65536, deg_medio)
        self.assertNotIn(131072, deg_medio)
        # Mas se o usuário pedir explicitamente ate_ctx=131072, inclui 128k
        deg_forcado = sonda.degraus_sonda({"bytes": int(12.0 * GB), "ctx_max": 131072}, vram_gb=16.0, ate_ctx=131072)
        self.assertIn(131072, deg_forcado)
