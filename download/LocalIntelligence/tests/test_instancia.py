"""Uma versão por vez: o painel novo fecha o antigo que ficou aberto na porta, reaproveita o mesmo e respeita o mais novo."""
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import config, instancia, migracao  # noqa: E402


def porta_vaga() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class PainelFalso(BaseHTTPRequestHandler):
    build = {}
    obedece = True

    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._json({"versao_painel": "3.0.0", "build": self.build})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._json({"ok": True})
        if self.obedece and self.path == "/api/encerrar":
            srv = self.server
            threading.Timer(0.1, lambda: (srv.shutdown(), srv.server_close())).start()   # como o painel real: o processo sai e a porta fica livre


class Instancia(unittest.TestCase):
    def subir(self, build, obedece=True):
        h = type("H", (PainelFalso,), {"build": build, "obedece": obedece})
        porta = porta_vaga()
        srv = ThreadingHTTPServer(("127.0.0.1", porta), h)
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return porta, srv

    def test_porta_livre(self):
        p = porta_vaga()
        self.assertEqual(instancia.preparar(p, {})["acao"], "livre")

    def test_versao_antiga_e_fechada(self):
        porta, srv = self.subir({"data": "2026-11-01", "commit": "aaaaaaa", "impressao": "velha"})
        r = instancia.preparar(porta, {"data": "2026-11-18", "commit": "bbbbbbb", "impressao": "nova"})
        srv.server_close()
        self.assertEqual(r["acao"], "substituida")
        self.assertEqual(r["porta"], porta)
        self.assertTrue(instancia.porta_livre(porta))

    def test_versao_sem_numero_e_fechada(self):          # o app muito antigo nem tinha VERSAO.txt
        porta, srv = self.subir({})
        r = instancia.preparar(porta, {"data": "2026-11-18", "impressao": "nova"})
        srv.server_close()
        self.assertEqual(r["acao"], "substituida")

    def test_mesma_versao_so_abre_a_janela(self):
        porta, _ = self.subir({"data": "2026-11-18", "impressao": "igual"})
        self.assertEqual(instancia.preparar(porta, {"data": "2026-11-18", "impressao": "igual"})["acao"], "mesma")

    def test_zip_e_store_do_mesmo_commit_sao_a_mesma_versao(self):
        porta, _ = self.subir({"data": "2026-11-18", "commit": "e684d7a", "impressao": "store"})
        self.assertEqual(instancia.preparar(porta, {"data": "2026-11-18", "commit": "e684d7a", "impressao": "zip"})["acao"], "mesma")

    def test_atalho_antigo_nao_derruba_versao_nova(self):
        porta, _ = self.subir({"data": "2026-11-20", "impressao": "nova"})
        self.assertEqual(instancia.preparar(porta, {"data": "2026-11-01", "impressao": "velha"})["acao"], "mais_nova")

    def test_quem_nao_fecha_leva_a_outra_porta(self):
        porta, _ = self.subir({"data": "2026-11-01", "impressao": "velha"}, obedece=False)
        with mock.patch.object(instancia, "_esperar_porta", return_value=False):
            r = instancia.preparar(porta, {"data": "2026-11-18", "impressao": "nova"})
        self.assertEqual(r["acao"], "outra_porta")
        self.assertNotEqual(r["porta"], porta)
        self.assertEqual(r["porta_ocupada"], porta)

    def test_so_forca_o_fechamento_do_painel(self):
        self.assertTrue(instancia.e_o_painel(r'"C:\Users\x\AppData\Local\Programs\Local AI 4 You\app\python\pythonw.exe" cli.py painel'))
        self.assertTrue(instancia.e_o_painel(r'"C:\Program Files\WindowsApps\x\python\pythonw.exe" -m cli painel'))
        self.assertFalse(instancia.e_o_painel(r'"C:\Program Files\Google\Chrome\chrome.exe" --type=renderer'))
        self.assertFalse(instancia.e_o_painel(r'python manage.py runserver 8765'))


class InstalacoesAntigas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.prog = self.tmp / "Programs"
        for nome in ("Local AI Search", "Local AI 4 You"):
            app = self.prog / nome / "app"
            (app / "estado").mkdir(parents=True)
            (app / "cli.py").write_text("")
            (app / "VERSAO.txt").write_text("abc1234 2026-11-05 ffff\n")
        (self.prog / "Local AI Search" / "app" / "estado" / "resultados.jsonl").write_text('{"m":"x"}\n')
        self.gravavel = self.tmp / "dados"
        self.patches = [mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.tmp)}),
                        mock.patch.object(config, "GRAVAVEL", self.gravavel),
                        mock.patch.object(config, "ESTADO", self.gravavel / "estado")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_lista_as_outras_mas_nao_a_propria(self):
        with mock.patch.object(config, "RAIZ", self.prog / "Local AI 4 You" / "app"):
            nomes = [a["nome"] for a in migracao.instalacoes_antigas()]
        self.assertEqual(nomes, ["Local AI Search"])
        with mock.patch.object(config, "RAIZ", self.tmp / "WindowsApps" / "pacote"):     # app da Store: as duas
            self.assertEqual(len(migracao.instalacoes_antigas()), 2)

    def test_remove_guardando_os_dados(self):
        with mock.patch.object(config, "RAIZ", self.tmp / "WindowsApps" / "pacote"):
            r = migracao.remover_instalacao(str(self.prog / "Local AI Search"))
            with self.assertRaises(ValueError):
                migracao.remover_instalacao(str(self.tmp))          # só pastas da lista
        self.assertTrue(r["removida"])
        self.assertFalse((self.prog / "Local AI Search").exists())
        self.assertTrue((Path(r["copia_dos_dados"]) / "resultados.jsonl").exists())
        self.assertIn('{"m":"x"}', (self.gravavel / "estado" / "resultados.jsonl").read_text())

    def test_limpa_config_importada_antes(self):
        est = self.gravavel / "estado"; est.mkdir(parents=True)
        (est / migracao.MARCA).write_text(json.dumps({"arquivos": ["resultados.jsonl", "config.json"]}))
        (est / "config.json").write_text(json.dumps({"broker_url": "https://x", "maquina_id": "boss", "ctx_bench": 4096}))
        with mock.patch.object(config, "CONFIG_ARQ", est / "config.json"):
            self.assertTrue(migracao.limpar_config_importada())
            self.assertFalse(migracao.limpar_config_importada())        # uma vez só
        self.assertEqual(json.loads((est / "config.json").read_text()), {"ctx_bench": 4096})


if __name__ == "__main__":
    unittest.main()
