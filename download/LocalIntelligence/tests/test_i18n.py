"""Forma dos dicionários de tradução (web/i18n-dados.js).

Um erro aqui passa calado no navegador: sem uma vírgula entre dois itens, o JavaScript lê `[a][b]` como acesso por
índice, o item vira `undefined` e a tradução inteira para (ou some uma regra). Lemos o arquivo como JSON, que é
mais estrito, e conferimos cada linha.
"""
import json
import re
import unittest
from pathlib import Path

ARQ = Path(__file__).resolve().parent.parent / "web" / "i18n-dados.js"


def _lista(nome: str) -> list:
    texto = ARQ.read_text(encoding="utf-8")
    m = re.search(r"window\." + nome + r" = \[\n(.*?)\n\];", texto, re.S)
    if not m:
        raise AssertionError(f"{nome} não encontrado em {ARQ.name}")
    linhas = [l for l in m.group(1).split("\n") if l.strip() and not l.lstrip().startswith("//")]
    corpo = "\n".join(linhas).rstrip().rstrip(",")
    try:
        return json.loads("[" + corpo + "]")
    except json.JSONDecodeError as e:
        perto = corpo.split("\n")[max(0, e.lineno - 2):e.lineno + 1]
        raise AssertionError(f"{nome}: não é uma lista válida (vírgula faltando?) perto de:\n" + "\n".join(perto)) from None


class TestDicionarios(unittest.TestCase):
    def test_frases(self):
        dados = _lista("LI_I18N_DADOS")
        self.assertGreater(len(dados), 1000)
        vistas = set()
        for linha in dados:
            with self.subTest(linha=linha[:1]):
                self.assertIsInstance(linha, list)
                self.assertEqual(len(linha), 3, "cada linha é [português, inglês, espanhol]")
                self.assertTrue(all(isinstance(x, str) and x for x in linha))
                pt = linha[0]
                # a tradução procura o texto já aparado: chave com espaço nas pontas nunca é encontrada
                self.assertEqual(pt, pt.strip(), "chave com espaço nas pontas")
                self.assertFalse(pt in vistas, "chave repetida")
                vistas.add(pt)
                n = pt.count("{n}")
                self.assertEqual(linha[1].count("{n}"), n, "inglês com outra quantidade de {n}")
                self.assertEqual(linha[2].count("{n}"), n, "espanhol com outra quantidade de {n}")

    def test_regras(self):
        regras = _lista("LI_I18N_REGRAS")
        self.assertGreater(len(regras), 100)
        for r in regras:
            with self.subTest(regra=r[:1]):
                self.assertEqual(len(r), 3)
                grupos = re.compile(r[0]).groups
                for alvo in r[1:]:
                    refs = [int(x) for x in re.findall(r"\$(\d)", alvo)]
                    self.assertTrue(all(1 <= k <= grupos for k in refs), f"{alvo!r} usa grupo que não existe")


if __name__ == "__main__":
    unittest.main()
