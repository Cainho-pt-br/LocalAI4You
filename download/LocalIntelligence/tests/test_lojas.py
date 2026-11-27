"""Valida `site/lojas.json` (links de loja/afiliado lidos pelo site e pelo app).

Pega erro de digitação antes de chegar às pessoas: JSON inválido, link que não é HTTPS ou de domínio fora de
`HOSTS_LOJAS_OK`, expressão regular que não compila ou longa demais, `upgrades` que não existem no catálogo de placas,
e o fallback embutido em `web/lojas.js` (LOJAS_CONFIG) divergindo do JSON.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[3]          # raiz do repositório
LOJAS_JSON = RAIZ / "site" / "lojas.json"
LOJAS_JS = RAIZ / "download" / "LocalIntelligence" / "web" / "lojas.js"
DADOS_JS = RAIZ / "site" / "dados.js"
MAX_REGEX = 80


def _hosts_ok() -> set[str]:
    src = LOJAS_JS.read_text(encoding="utf-8")
    bloco = re.search(r"HOSTS_LOJAS_OK = new Set\(\[(.*?)\]\);", src, re.S).group(1)
    return set(re.findall(r"'([^']+)'", bloco))


def _ids_gpus() -> set[str]:
    t = DADOS_JS.read_text(encoding="utf-8")
    dados = json.loads(t[t.index("{"): t.rindex("}") + 1])
    return {g["id"] for g in dados["hardware"]["gpus"]}


def _fallback_js() -> dict | None:
    """Lê o LOJAS_CONFIG embutido em lojas.js rodando o arquivo no Node (sem navegador)."""
    if not shutil.which("node"):
        return None
    # RegExp não vira JSON: o final do script converte `busca` em texto (o código-fonte da expressão).
    fim = ("\n;const _c = Object.assign({}, LOJAS_CONFIG, {mercadolivre: LOJAS_CONFIG.mercadolivre"
           ".map(m => ({busca: m.busca.source, marca: m.marca, url: m.url}))});"
           "\nconsole.log(JSON.stringify({cfg: _c, hosts: [...HOSTS_LOJAS_OK]}));")
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "lojas_check.js"
        arq.write_text(LOJAS_JS.read_text(encoding="utf-8") + fim, encoding="utf-8")
        r = subprocess.run(["node", str(arq)], capture_output=True, text=True, timeout=60, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError("lojas.js não executa no Node:\n" + r.stderr)
    return json.loads(r.stdout)


class TestLojasJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = json.loads(LOJAS_JSON.read_text(encoding="utf-8"))
        cls.hosts = _hosts_ok()

    def _https_ok(self, url: str, onde: str):
        if not url:
            return
        p = urlparse(url)
        self.assertEqual(p.scheme, "https", f"{onde}: precisa ser HTTPS ({url})")
        self.assertIn(p.hostname, self.hosts, f"{onde}: domínio fora de HOSTS_LOJAS_OK ({p.hostname})")

    def test_urls_https_e_dominio_permitido(self):
        for i, item in enumerate(self.dados.get("mercadolivre", [])):
            self._https_ok(item["url"], f"mercadolivre[{i}]")
        for item in self.dados.get("nuvem", []):
            self._https_ok(item.get("url", ""), f"nuvem {item.get('nome')}")

    def test_regex_compila_e_tem_tamanho_limitado(self):
        for i, item in enumerate(self.dados.get("mercadolivre", [])):
            busca = item["busca"]
            self.assertLessEqual(len(busca), MAX_REGEX, f"mercadolivre[{i}].busca longa demais")
            try:
                re.compile(busca, re.I)
            except re.error as e:
                self.fail(f"mercadolivre[{i}].busca não compila: {e}")

    def test_upgrades_existem_no_catalogo(self):
        ids = _ids_gpus()
        for u in self.dados.get("upgrades", []):
            self.assertIn(u, ids, f"upgrade '{u}' não existe no catálogo de placas (site/dados.js)")

    def test_sem_awin_nem_vast(self):
        texto = LOJAS_JSON.read_text(encoding="utf-8").lower()
        self.assertNotIn("awin", texto)
        self.assertNotIn("vast", texto)


class TestFallbackIgualAoJson(unittest.TestCase):
    def test_fallback_embutido_igual_ao_json(self):
        js = _fallback_js()
        if js is None:
            self.skipTest("Node não instalado: fallback de lojas.js não verificado")
        cfg, dados = js["cfg"], json.loads(LOJAS_JSON.read_text(encoding="utf-8"))
        self.assertEqual(cfg["amazonTags"], dados["amazonTags"])
        self.assertEqual(cfg["upgrades"], dados["upgrades"])
        self.assertEqual([(n["nome"], n["url"]) for n in cfg["nuvem"]],
                         [(n["nome"], n["url"]) for n in dados["nuvem"]])
        ml_js = [(m["busca"], m["marca"], m["url"]) for m in cfg["mercadolivre"]]
        ml_json = [(m["busca"], m["marca"], m["url"]) for m in dados["mercadolivre"]]
        self.assertEqual(ml_js, ml_json)

    def test_hosts_do_js_batem_com_awin_removido(self):
        js = _fallback_js()
        if js is None:
            self.skipTest("Node não instalado")
        self.assertFalse(any("awin" in h or "vast" in h or "kabum" in h or "pichau" in h for h in js["hosts"]))


if __name__ == "__main__":
    unittest.main()
