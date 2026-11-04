"""Fluxo completo "testar o desafiante" contra um Ollama falso: baixa, sonda, mede (nível rápido, itens reais),
compara com um titular sintético e resolve o veredito. Prova a cola entre as peças sem GPU e sem rede.

    python -m unittest tests.test_desafio -v
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

from li import aposentados, config, decide, desafio, resultados, scout  # noqa: E402
from li.bench import amostras, pontuacao, sonda  # noqa: E402
from li.ollama import Ollama  # noqa: E402
from li.fontes import ollama_lib  # noqa: E402
from li.util import agora_iso, gravar_json  # noqa: E402

CHAMADAS = []


class Falso(BaseHTTPRequestHandler):
    instalado_novo = False

    def log_message(self, *a):
        pass

    def _j(self, d, status=200):
        b = json.dumps(d).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/version":
            return self._j({"version": "fake"})
        if self.path == "/api/tags":
            ms = [{"name": "inc:1b", "size": 2_000_000_000, "digest": "inc-digest", "details": {"parameter_size": "1B", "quantization_level": "Q4_K_M"}}]
            if Falso.instalado_novo:
                ms.append({"name": "novo:1b", "size": 1_000_000_000, "digest": "novo-digest", "details": {"parameter_size": "1B", "quantization_level": "Q4_K_M"}})
            return self._j({"models": ms})
        if self.path == "/api/ps":
            return self._j({"models": [{"name": n, "size": 1000, "size_vram": 1000, "context_length": 8192} for n in ("inc:1b", "novo:1b")]})
        self._j({}, 404)

    def do_DELETE(self):
        CHAMADAS.append(("delete", json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))))
        Falso.instalado_novo = False
        self._j({})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/show":
            return self._j({"capabilities": ["completion", "tools"], "model_info": {"general.architecture": "llama", "llama.block_count": 16,
                            "llama.attention.head_count_kv": 4, "llama.attention.head_count": 16, "llama.embedding_length": 2048, "llama.context_length": 32768}})
        if self.path == "/api/pull":
            CHAMADAS.append(("pull", corpo["model"]))
            self.send_response(200)
            self.end_headers()
            for l in ({"status": "pulling x", "digest": "sha256:a", "total": 100, "completed": 50}, {"status": "success"}):
                self.wfile.write((json.dumps(l) + "\n").encode())
            Falso.instalado_novo = True
            return
        if self.path == "/api/chat":
            if not corpo.get("messages"):
                return self._j({"message": {"content": ""}})
            if corpo.get("tools"):
                f = corpo["tools"][0]["function"]
                return self._j({"message": {"content": "", "tool_calls": [{"function": {"name": f["name"], "arguments": {}}}]},
                                "eval_count": 30, "eval_duration": 10 ** 9, "prompt_eval_count": 80})
            return self._j({"message": {"content": "B"}, "eval_count": 40, "eval_duration": 10 ** 9, "prompt_eval_count": 60})
        self._j({}, 404)


class TestFluxoDoDesafiante(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._preflight = ollama_lib.preflight  # sem rede nos testes: o registro "responde" o tamanho do falso
        ollama_lib.preflight = lambda pull: {"ok": True, "bytes_total": 1_000_000_000, "bytes_modelo": 1_000_000_000, "bytes_projetor": 0}
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.o = Ollama(f"http://127.0.0.1:{cls.srv.server_address[1]}")
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.antigos = {k: getattr(config, k) for k in ("ESTADO", "RESULTADOS", "SONDAS", "SQUAD", "VEREDITOS", "SNAPSHOTS", "PROGRESSO", "CACHE", "APOSENTADOS")}
        config.ESTADO, config.RESULTADOS, config.SONDAS = base, base / "r.jsonl", base / "s.json"
        config.SQUAD, config.VEREDITOS, config.PROGRESSO = base / "sq.json", base / "v.json", base / "p.json"
        config.APOSENTADOS = base / "ap.json"  # sem isto o teste gravaria um registro falso no estado REAL
        config.SNAPSHOTS, config.CACHE = base / "snap", base / "cache"
        config.SNAPSHOTS.mkdir()
        # titular sintético "inc:1b": errou tudo no nível rápido (itens reais), digest fixo
        for s in amostras.NIVEIS["rapido"]:
            if s == "capitu" and pontuacao.capitu_registro() is None:
                continue
            for it in amostras.itens_do_nivel(s, "rapido"):
                resultados.anexar({"modelo": "inc:1b", "digest": "inc-digest", "suite": s, "item": it["id"], "modo": "base", "valido": True, "ok": False, "tps": 30})
        cand = {"id": "ollama:novo:1b", "origem": "ollama", "familia": "novo", "tamanho": "1b", "nome": "novo 1B", "descricao": "", "caps": ["tools"],
                "params_b": 1.0, "ativos_b": None, "moe": False, "ctx_max": 32768, "dias": 10.0, "lancamento": agora_iso(), "novo": True,
                "confianca": "ollama-oficial", "pulls": 5_000_000, "papeis": ["chat_pt", "regras", "agente", "codigo", "rapido"],
                "arch": {"camadas": 16, "kv_heads": 4, "key_len": 128, "val_len": 128, "ctx_max": 32768},
                "variantes": [{"tag": "1b", "pull": "novo:1b", "quant": "Q4_K_M", "bytes": 1_000_000_000}]}
        gravar_json(config.SNAPSHOTS / "ultimo-completo.json", {"criado": agora_iso(), "total": 1, "fontes": {}, "candidatos": [cand]})

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.antigos.items():
            setattr(config, k, v)
        ollama_lib.preflight = cls._preflight
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def test_1_plano_mostra_o_que_vai_baixar(self):
        pl = desafio.plano("ollama:novo:1b", "chat_pt", self.o)
        self.assertEqual(pl["pull"], "novo:1b")
        self.assertFalse(pl["ja_instalado"])
        self.assertIn("GB", pl["tamanho"])

    def test_2_testar_baixa_mede_compara_e_deixa_pendente(self):
        Falso.instalado_novo = False
        CHAMADAS.clear()
        passos = []
        v = desafio.testar(self.o, "ollama:novo:1b", "chat_pt", "rapido", lambda d: passos.append(d.get("fase")))
        self.assertIn(("pull", "novo:1b"), CHAMADAS)
        self.assertIn("download", passos)
        self.assertIn("sonda", passos)
        self.assertTrue(v["pendente"])
        self.assertTrue(v["baixado_agora"])
        self.assertEqual(v["candidato"]["id"], "novo:1b")
        # medições do desafiante existem no mesmo protocolo e a sonda foi gravada
        self.assertIsNotNone(resultados.resumo("novo:1b", "novo-digest"))
        self.assertIsNotNone(sonda.da_sonda("novo:1b", "novo-digest"))
        # comparação por função, contra o titular sintético
        pp = v["por_papel"]
        self.assertIn(pp["chat_pt"]["veredito"], ("superior", "empate", "inferior", "incompleto"))
        self.assertEqual(pp["rapido"].get("titular"), "inc:1b")
        self.assertEqual(v["protocolo"], "v2")
        self.assertEqual(len(decide.vereditos()), 1)

    def test_3_resolver_manter_nao_muda_nada_e_promover_grava_historico(self):
        v = decide.vereditos()[-1]
        antes = decide.squad_salvo()["titulares"].copy()
        r = desafio.resolver_veredito(v["id"], "manter", self.o)
        self.assertFalse(r["pendente"])
        self.assertEqual(decide.squad_salvo()["titulares"], antes)
        desafio.promover("chat_pt", "novo:1b", "teste")
        s = decide.squad_salvo()
        self.assertEqual(s["titulares"]["chat_pt"], "novo:1b")
        self.assertEqual(s["historico"][-1]["para"], "novo:1b")
        with self.assertRaises(desafio.ErroDesafio):
            desafio.promover("papel-inexistente", "x")

    def test_4_descartar_exige_confirmacao_e_apaga(self):
        v = decide.vereditos()[-1]
        with self.assertRaises(desafio.ErroDesafio):
            desafio.resolver_veredito(v["id"], "descartar", self.o, confirmar_remocao=False)
        CHAMADAS.clear()
        desafio.resolver_veredito(v["id"], "descartar", self.o, confirmar_remocao=True)
        self.assertEqual(CHAMADAS[0][0], "delete")
        self.assertEqual(CHAMADAS[0][1]["model"], "novo:1b")
        # apagar pelo painel deixa registro (quando, tamanho, motivo) e limpa o titular que apontava para o modelo apagado
        reg = aposentados.carregar()[-1]
        self.assertEqual(reg["modelo"], "novo:1b")
        self.assertEqual(reg["bytes"], 1_000_000_000)
        self.assertIn("descartado", reg["motivo"])
        self.assertNotEqual(decide.squad_salvo()["titulares"].get("chat_pt"), "novo:1b")

    def test_5_candidato_inexistente_e_erro_claro(self):
        with self.assertRaises(desafio.ErroDesafio):
            desafio.plano("ollama:nao-existe:9b", None, self.o)

    def test_6_plano_com_a_quantizacao_escolhida_pelo_usuario(self):
        pl = desafio.plano("ollama:novo:1b", "chat_pt", self.o, pull="novo:1b")
        self.assertEqual(pl["pull"], "novo:1b")
        # quantização que o radar não tinha (GGUF do Hugging Face): confirmada no registro, sem baixar
        pl2 = desafio.plano("ollama:novo:1b", "chat_pt", self.o, pull="hf.co/autor/repo:UD-Q8_0")
        self.assertEqual((pl2["pull"], pl2["quant"], pl2["origem"]), ("hf.co/autor/repo:UD-Q8_0", "UD-Q8_0", "hf"))
        with self.assertRaises(desafio.ErroDesafio):
            desafio.plano("ollama:novo:1b", "chat_pt", self.o, pull="rm -rf / ; novo:1b")
        # grande demais para a GPU: recusa em vez de medir um modelo que vazaria para a RAM
        antes = ollama_lib.preflight
        ollama_lib.preflight = lambda pull: {"ok": True, "bytes_total": 60_000_000_000, "bytes_modelo": 60_000_000_000, "bytes_projetor": 0}
        try:
            with self.assertRaises(desafio.ErroDesafio) as cm:
                desafio.plano("ollama:novo:1b", "chat_pt", self.o, pull="hf.co/autor/repo:Q8_0")
            self.assertIn("não cabe", str(cm.exception))
        finally:
            ollama_lib.preflight = antes

    def test_7_aposentar_passa_as_funcoes_ao_herdeiro(self):
        Falso.instalado_novo = True
        desafio.promover("chat_pt", "inc:1b", "preparo")
        CHAMADAS.clear()
        r = desafio.aposentar(self.o, "inc:1b", "teste de aposentadoria", {"chat_pt": "novo:1b", "codigo": "nao-existe"})
        self.assertEqual(CHAMADAS[0][1]["model"], "inc:1b")
        self.assertEqual(r["herdeiros"], {"chat_pt": "novo:1b"})          # herdeiro que não existe é ignorado
        self.assertEqual(decide.squad_salvo()["titulares"]["chat_pt"], "novo:1b")
        self.assertEqual(aposentados.carregar()[-1]["herdeiros"], {"chat_pt": "novo:1b"})
        with self.assertRaises(desafio.ErroDesafio):
            desafio.aposentar(self.o, "fantasma:1b")


if __name__ == "__main__":
    unittest.main()
