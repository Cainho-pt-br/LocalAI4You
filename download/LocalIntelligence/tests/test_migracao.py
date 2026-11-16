"""Migração de dados entre instalações (ZIP ↔ Microsoft Store) e janela do app."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import config, janela, migracao  # noqa: E402


class Migracao(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.antigo = self.tmp / "antigo" / "estado"
        self.novo = self.tmp / "novo" / "estado"
        self.antigo.mkdir(parents=True)
        self.novo.mkdir(parents=True)
        (self.antigo / "resultados.jsonl").write_text('{"m":"a","nota":80}\n{"m":"b","nota":70}\n', "utf-8")
        (self.antigo / "aposentados.json").write_text(json.dumps({"x": 1}), "utf-8")
        (self.antigo / "vereditos.json").write_text("[]", "utf-8")
        self.p = mock.patch.object(config, "ESTADO", self.novo)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_traz_notas_e_aposentados(self):
        r = migracao.importar_dados_antigos(self.antigo)
        self.assertIsNotNone(r)
        self.assertEqual(len((self.novo / "resultados.jsonl").read_text("utf-8").splitlines()), 2)
        self.assertEqual(json.loads((self.novo / "aposentados.json").read_text("utf-8")), {"x": 1})
        self.assertTrue((self.novo / migracao.MARCA).exists())
        self.assertTrue((self.antigo / "resultados.jsonl").exists(), "não pode apagar a origem")

    def test_so_uma_vez(self):
        migracao.importar_dados_antigos(self.antigo)
        (self.novo / "aposentados.json").unlink()
        self.assertIsNone(migracao.importar_dados_antigos(self.antigo))
        self.assertFalse((self.novo / "aposentados.json").exists(), "o que a pessoa apagou depois não volta")

    def test_nao_sobrescreve_e_une_resultados(self):
        (self.novo / "aposentados.json").write_text(json.dumps({"y": 2}), "utf-8")
        (self.novo / "resultados.jsonl").write_text('{"m":"b","nota":70}\n{"m":"c","nota":60}\n', "utf-8")
        r = migracao.importar_dados_antigos(self.antigo)
        self.assertEqual(json.loads((self.novo / "aposentados.json").read_text("utf-8")), {"y": 2})
        linhas = (self.novo / "resultados.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(len(linhas), 3)               # a, b, c: sem repetir b
        self.assertEqual(r["resultados_novos"], 1)

    def test_sem_origem_nao_faz_nada(self):
        with mock.patch.object(migracao, "_locais_antigos", return_value=[self.tmp / "nao-existe"]):
            self.assertIsNone(migracao.importar_dados_antigos())

    def test_origem_igual_ao_destino_e_ignorada(self):
        (self.novo / "resultados.jsonl").write_text("{}\n", "utf-8")
        self.assertIsNone(migracao.importar_dados_antigos(self.novo))


class Janela(unittest.TestCase):
    def test_desligada_por_variavel(self):
        with mock.patch.dict(os.environ, {"LI_JANELA": "0"}):
            self.assertIsNone(janela.disponivel())
            self.assertFalse(janela.abrir("http://127.0.0.1:1/"))

    def test_sem_navegador_cai_para_o_padrao(self):
        with mock.patch.object(janela, "_navegadores", return_value=[]), mock.patch.dict(os.environ, {"LI_JANELA": "1"}):
            self.assertFalse(janela.abrir("http://127.0.0.1:1/"))


if __name__ == "__main__":
    unittest.main()
