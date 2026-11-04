"""Controle das outras máquinas: quem pode entrar no painel pelo tailnet, o que pode ser registrado e o repasse da API.

    python -m unittest tests.test_remoto -v        (sem rede: um "painel remoto" falso em HTTP local)
"""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import config, remoto  # noqa: E402

HOST = "raspberrypi.example.ts.net:10000"


class PainelFalso(BaseHTTPRequestHandler):
    visto = []

    def log_message(self, *a):
        pass

    def _resp(self, st, d):
        b = json.dumps(d).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        PainelFalso.visto.append((self.command, self.path, self.headers.get("X-LI-Token"), self.headers.get("X-LI")))
        if self.headers.get("X-LI-Token") != "t" * 32:
            return self._resp(403, {"erro": "sem token"})
        if self.path == "/api/saude":
            return self._resp(200, {"ollama": {"no_ar": True, "versao": "0.0"}, "gpu": None, "protocolo": "v2"})
        self._resp(200, {"rota": self.path})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n) or b"{}")
        PainelFalso.visto.append((self.command, self.path, self.headers.get("X-LI-Token"), corpo))
        self._resp(200, {"ecoou": corpo})


class TestAcesso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ant = (config.CONFIG_ARQ, config.TOKEN_ARQ)
        config.CONFIG_ARQ, config.TOKEN_ARQ = Path(self.tmp.name) / "c.json", Path(self.tmp.name) / "t.txt"
        config.salvar({"hosts_painel": [HOST], "logins_permitidos": ["caio@exemplo.com"]})
        self.token = config.token_painel()

    def tearDown(self):
        config.CONFIG_ARQ, config.TOKEN_ARQ = self.ant
        self.tmp.cleanup()

    def test_loopback_e_sempre_local(self):
        self.assertEqual(remoto.acesso("127.0.0.1:8765", None, None, 8765), "local")
        self.assertEqual(remoto.acesso("localhost:8765", None, None, 8765), "local")
        self.assertEqual(remoto.acesso("127.0.0.1:9999", None, None, 8765), "negado")   # porta errada = rebinding

    def test_host_do_tailnet_exige_token_ou_login(self):
        self.assertEqual(remoto.acesso(HOST, None, None, 8765), "negado")
        self.assertEqual(remoto.acesso(HOST, "errado" * 6, None, 8765), "negado")
        self.assertEqual(remoto.acesso(HOST, self.token, None, 8765), "remoto")
        self.assertEqual(remoto.acesso(HOST, None, "CAIO@exemplo.com", 8765), "remoto")
        self.assertEqual(remoto.acesso(HOST, None, "intruso@exemplo.com", 8765), "negado")

    def test_host_desconhecido_e_negado_mesmo_com_token(self):
        self.assertEqual(remoto.acesso("evil.example.com", self.token, None, 8765), "negado")

    def test_token_e_estavel_e_forte(self):
        self.assertEqual(config.token_painel(), self.token)
        self.assertGreaterEqual(len(self.token), 32)


class TestRegistroERepasse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), PainelFalso)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ant = (config.REMOTAS, remoto._url_ok)
        config.REMOTAS = Path(self.tmp.name) / "r.json"
        PainelFalso.visto.clear()

    def tearDown(self):
        config.REMOTAS, remoto._url_ok = self.ant
        self.tmp.cleanup()

    def test_so_registra_maquina_do_parque_com_url_do_tailnet(self):
        tok = "t" * 32
        self.assertEqual(remoto.registrar("raspberrypi", tok)["url"], "https://raspberrypi.example.ts.net:10000")
        for ruim in ("x.evil.com/#", "../etc", "nao-existe", ""):
            with self.assertRaises(ValueError):
                remoto.registrar(ruim, tok)
        with self.assertRaises(ValueError):
            remoto.registrar("raspberrypi", "curto")
        with self.assertRaises(ValueError):
            remoto.registrar("raspberrypi", tok, "https://evil.com")          # não é .ts.net
        with self.assertRaises(ValueError):
            remoto.registrar("raspberrypi", tok, "http://x.ts.net")           # não é https

    def test_repasse_leva_o_token_e_devolve_a_resposta(self):
        remoto._url_ok = lambda u: True                                        # o servidor falso é http em loopback
        config.REMOTAS.write_text(json.dumps({"raspberrypi": {"url": self.url, "token": "t" * 32}}))
        st, corpo, _ = remoto.repassar("raspberrypi", "GET", "mesa", "a=1", None)
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(corpo)["rota"], "/api/mesa?a=1")
        st, corpo, _ = remoto.repassar("raspberrypi", "POST", "bench", "", json.dumps({"x": 1}).encode())
        self.assertEqual(json.loads(corpo)["ecoou"], {"x": 1})
        self.assertTrue(all(v[2] == "t" * 32 for v in PainelFalso.visto))
        self.assertEqual(remoto.sondar("raspberrypi")["online"], True)

    def test_rota_maliciosa_e_maquina_nao_registrada_sao_recusadas(self):
        remoto._url_ok = lambda u: True
        config.REMOTAS.write_text(json.dumps({"raspberrypi": {"url": self.url, "token": "t" * 32}}))
        for resto in ("../../etc/passwd", "a b", "mesa?x", ""):
            with self.assertRaises(ValueError):
                remoto.repassar("raspberrypi", "GET", resto, "", None)
        with self.assertRaises(ValueError):
            remoto.repassar("aspire5", "GET", "mesa", "", None)               # não registrada

    def test_maquina_desligada_vira_502_e_nao_excecao(self):
        remoto._url_ok = lambda u: True
        config.REMOTAS.write_text(json.dumps({"raspberrypi": {"url": "http://127.0.0.1:9", "token": "t" * 32}}))
        st, corpo, _ = remoto.repassar("raspberrypi", "GET", "mesa", "", None)
        self.assertEqual(st, 502)
        self.assertIn("não respondeu", json.loads(corpo)["erro"])
        self.assertFalse(remoto.sondar("raspberrypi")["online"])


if __name__ == "__main__":
    unittest.main()
