"""Calculadora de hardware: o motor JavaScript (web/calc.js) tem de dar os MESMOS números do Python (li/fit.py, li/decide.py),
os dados exportados têm de ser coerentes e o HTML autônomo não pode ser quebrado por texto vindo do radar.

    python -m unittest tests.test_calc -v        (a parte JS precisa do Node; sem ele, é pulada com aviso)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from li import calc, config, decide, fit, papeis, scout  # noqa: E402
from li.util import agora_iso  # noqa: E402

ARCHS = {
    "qwen35": {"arquitetura": "qwen35", "camadas": 64, "kv_heads": 4, "key_len": 256, "val_len": 256, "intervalo_atencao_cheia": 4, "ctx_max": 262144},
    "gemma4": {"arquitetura": "gemma4", "camadas": 48, "kv_heads": 8, "key_len": 256, "val_len": 256, "janela": 1024,
               "layer_types": (["sliding_attention"] * 5 + ["full_attention"]) * 8, "kv_heads_global": 2, "head_dim_global": 512,
               "k_eq_v": True, "kv_compartilhadas": 4, "ctx_max": 131072},
    "denso": {"arquitetura": "llama", "camadas": 32, "kv_heads": 8, "key_len": 128, "val_len": 128, "ctx_max": 131072},
    "gptoss": {"arquitetura": "gpt-oss", "camadas": 24, "kv_heads": 8, "key_len": 64, "val_len": 64, "janela": 128, "ctx_max": 131072},
    "generica": scout.arch_generica(30),
    "vazia": {},
}
MAQS = json.loads((RAIZ / "parque" / "parque.json").read_text("utf-8"))["maquinas"] + [
    {"id": "g24", "gpu": {"vram_gb": 24, "bw_gbs": 1008}, "ram_gb": 64, "bw_gbs_min": 70, "bw_gbs_max": 90, "simd": ["avx", "avx2", "avx512"], "reserva_so_gb": 4},
    {"id": "g8", "gpu": {"vram_gb": 8, "bw_gbs": 288}, "ram_gb": 16, "bw_gbs_min": 40, "bw_gbs_max": 51, "simd": ["avx", "avx2"], "reserva_so_gb": 4},
    {"id": "mac", "gpu": {"vram_gb": 48, "bw_gbs": 546}, "ram_gb": 64, "bw_gbs_min": 546, "bw_gbs_max": 546, "simd": ["neon"], "reserva_so_gb": 0},
]
VARIANTES_27B = [("Q2_K", 9.8), ("IQ3_S", 12.0), ("Q3_K_M", 13.5), ("Q4_K_M", 16.8), ("Q5_K_M", 19.5), ("Q8_0", 28.7), ("BF16", 54.0)]


def _variantes(escala=1.0):
    return [{"tag": q, "pull": f"x:{q}", "quant": q, "bytes": int(g * escala * 1e9), "extra_bytes": 0, "padrao": False} for q, g in VARIANTES_27B]


def _golden():
    casos = []
    for nome, arch in ARCHS.items():
        comp = calc.arch_compacta(arch)
        casos.append({"tipo": "estrutura", "id": nome, "arch_compacta": comp, "camadas_tipo": list(fit._camadas_por_tipo(arch)) if arch else [0, 0, 0]})
        for ctx in (2048, 8192, 32768, 131072):
            for kv in ("f16", "q8_0", "q4_0"):
                casos.append({"tipo": "kv", "id": f"{nome}/{ctx}/{kv}", "arch": comp, "ctx": ctx, "kv": kv, "peso": 7_000_000_000,
                              "kv_bytes": fit.kv_bytes(arch, ctx, kv), "vram_total": fit.vram_total_bytes(7_000_000_000, arch, ctx, kv)})
    for m in MAQS:
        for nome in ("qwen35", "gemma4", "denso"):
            arch, comp = ARCHS[nome], calc.arch_compacta(ARCHS[nome])
            for peso in (2e9, 9e9, 17e9):
                for kv in ("f16", "q8_0"):
                    casos.append({"tipo": "maquina", "id": f"{m['id']}/{nome}/{peso}/{kv}", "maq": m, "arch": comp, "peso": int(peso), "ctx": 8192, "kv": kv, "reserva": 1.3,
                                  "orcamento": fit.orcamento_bytes(m, 1.3), "encaixe": fit.avaliar_encaixe(int(peso), arch, m, 8192, kv, 1.3),
                                  "tps_denso": fit.estimar_tps(int(peso), m, False), "tps_moe": fit.estimar_tps(int(peso), m, True)})
        for escala, params in ((1.0, 27.0), (0.3, 8.0), (0.1, 2.7)):
            for ctx in (4096, 32768):
                v = fit.escolher_variante(_variantes(escala), m, ARCHS["qwen35"], ctx, params, "q8_0", 1.3)
                casos.append({"tipo": "variante", "id": f"{m['id']}/{escala}/{ctx}", "maq": m, "arch": calc.arch_compacta(ARCHS["qwen35"]), "variantes": _variantes(escala),
                              "ctx": ctx, "params_b": params, "kv": "q8_0", "reserva": 1.3, "quant": v["quant"] if v else None})
    # candidatos completos (encaixe + prioridade), com a parte da prioridade que não depende da máquina vinda do Python
    for nome, params, ativos, dias, conf, pulls in (("modelo-a", 27.0, None, 20.0, "ollama-oficial", 3_000_000), ("modelo-b", 8.0, None, 200.0, "laboratorio", 50_000),
                                                    ("modelo-c", 35.0, 3.0, 60.0, "ollama-oficial", 900_000), ("modelo-d", 3.0, None, 500.0, "comunidade", 800)):
        c = {"id": "x:" + nome, "nome": nome, "origem": "ollama", "familia": nome, "params_b": params, "ativos_b": ativos, "moe": bool(ativos), "caps": ["tools", "thinking"],
             "dias": dias, "confianca": conf, "pulls": pulls, "descricao": "", "arch": ARCHS["qwen35"], "variantes": _variantes(params / 27.0), "papeis": ["chat_pt", "codigo", "raciocinio", "rapido"]}
        cjs = {**c, "arch": calc.arch_compacta(ARCHS["qwen35"]), "pop": pulls,
               "prio": {pid: {k: v for k, v in decide.prioridade_base(c, papeis.POR_ID[pid], []).items() if k != "razoes"} for pid in c["papeis"]}}
        for m in MAQS:
            for pid in ("chat_pt", "codigo", "rapido"):
                p = papeis.POR_ID[pid]
                enc = decide.encaixe_candidato(c, m, p, {"kv_cache": "q8_0", "reserva_vram_gb": 1.3})
                item = {"tipo": "candidato", "id": f"{nome}/{m['id']}/{pid}", "cand": cjs, "maq": m, "papel": {"id": pid, "ctx_alvo": p["ctx_alvo"]}, "kv": "q8_0", "reserva": 1.3,
                        "enc": {"cabe": bool(enc and enc.get("cabe"))}}
                if item["enc"]["cabe"]:
                    item["enc"].update({"quant": enc["variante"]["quant"], "nivel": enc["encaixe"]["nivel"], "ctx_max": enc["encaixe"]["ctx_max"], "tps": enc.get("tps_est")})
                    item["prioridade"] = decide.prioridade(c, p, enc, [], m)["pontos"]
                casos.append(item)
    return {"constantes": calc.constantes(), "casos": casos}


class TestParidadeComOPython(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node não instalado: paridade JS×Python não verificada")
    def test_js_da_os_mesmos_numeros_que_o_python(self):
        g = _golden()
        self.assertGreater(len(g["casos"]), 300)
        r = subprocess.run(["node", str(RAIZ / "tests" / "js" / "paridade.js")], input=json.dumps(g), text=True, capture_output=True, timeout=120, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        diffs = json.loads(r.stdout)
        self.assertEqual(diffs, [], "divergências JS×Python (primeiras): " + json.dumps(diffs[:5], ensure_ascii=False))


def _cand_sint(nome, params, **kw):
    c = {"id": "ollama:" + nome, "origem": "ollama", "familia": nome.split(":")[0], "tamanho": nome.split(":")[1], "nome": nome, "descricao": kw.pop("descricao", ""),
         "caps": ["tools"], "params_b": params, "ativos_b": None, "moe": False, "ctx_max": 131072, "dias": 30.0, "lancamento": "2026-09-01T00:00:00Z", "novo": False,
         "confianca": "ollama-oficial", "pulls": 2_000_000, "papeis": ["chat_pt", "regras", "codigo", "agente"], "licenca": "apache-2.0",
         "arch": ARCHS["denso"], "variantes": [{"tag": "q4", "pull": f"{nome}-q4", "quant": "Q4_K_M", "bytes": int(params * 0.6e9)}]}
    c.update(kw)
    return c


class TestDadosEHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ultimo = scout.ultimo
        cls.snap = {"criado": agora_iso(), "total": 2, "fontes": {}, "candidatos": [
            _cand_sint("bom:9b", 9, descricao="</script><script>alert(1)</script> <!-- x"), _cand_sint("outro:4b", 4)]}
        scout.ultimo = lambda: cls.snap

    @classmethod
    def tearDownClass(cls):
        scout.ultimo = cls._ultimo

    def test_dados_trazem_constantes_papeis_e_prioridade_pronta(self):
        d = calc.dados(None, incluir_parque=False)
        self.assertEqual(d["constantes"]["MIN_BPW"], fit.MIN_BPW)
        self.assertIn("contexto", [p["id"] for p in d["papeis"]])
        c = d["candidatos"][0]
        self.assertIn("camadas_tipo", c["arch"])
        self.assertIn("chat_pt", c["prio"])
        self.assertGreater(c["prio"]["chat_pt"]["escala"], 0)
        self.assertGreater(len(d["hardware"]["gpus"]), 100)

    def test_catalogo_de_hardware_e_consistente(self):
        hw = calc.hardware()
        ids = [g["id"] for g in hw["gpus"]] + [u["id"] for u in hw["unificadas"]]
        self.assertEqual(len(ids), len(set(ids)), "ids repetidos no catálogo")
        for g in hw["gpus"]:
            self.assertTrue(1 <= g["vram_gb"] <= 192 and 50 <= g["bw_gbs"] <= 5000, g)
        mem_ids = {m["id"] for m in hw["memorias_ram"]}
        self.assertEqual(len(mem_ids), len(hw["memorias_ram"]))
        for m in hw["memorias_ram"]:
            self.assertTrue(m["mts"] > 500 and m["gen"], m)
        self.assertGreater(len(hw["cpus"]), 60)
        cpu_ids = [c["id"] for c in hw["cpus"]]
        self.assertEqual(len(cpu_ids), len(set(cpu_ids)))
        for c in hw["cpus"]:
            self.assertIn(c["mem"], mem_ids, c)
            self.assertTrue(set(c["simd"]) <= {"sse", "avx", "avx2", "avx512", "neon"}, c)
            self.assertIn(c["canais"], hw["canais_opcoes"], c)
            if c.get("bw"):
                self.assertLess(c["bw"][0], c["bw"][1])

    def test_html_autonomo_nao_e_quebrado_por_texto_do_radar(self):
        h = calc.html_autonomo(None)
        self.assertEqual(h.count("</script>"), 5)  # dados + base + calc + ui + montagem: nenhum fechamento extra vindo dos dados
        self.assertNotIn("<script>alert(1)", h)
        m = re.search(r"window\.LI_DADOS = (.*?);</script>", h, re.S)
        d = json.loads(m.group(1))
        self.assertIn("alert(1)", d["candidatos"][0]["descricao"])  # o texto sobrevive, só não executa
        self.assertNotIn("maquinas", d)  # o arquivo para compartilhar não leva o parque pessoal


class TestJsSemRede(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node não instalado")
    def test_escolhas_por_atividade_em_tres_hardwares(self):
        """Fumaça do motor de escolhas com o catálogo sintético: 16 GB, 8 GB e só CPU devolvem coisas diferentes e sensatas."""
        cands = [_cand_sint("grande:30b", 30.0), _cand_sint("medio:12b", 12.0), _cand_sint("pequeno:4b", 4.0), _cand_sint("mini:1b", 1.0)]
        for c in cands:
            c["papeis"] = ["chat_pt", "regras", "codigo", "agente", "rapido"]
        snap = {"criado": agora_iso(), "total": 4, "fontes": {}, "candidatos": cands}
        antigo = scout.ultimo
        scout.ultimo = lambda: snap
        try:
            dados = calc.dados(None, incluir_parque=False)
        finally:
            scout.ultimo = antigo
        r = subprocess.run(["node", str(RAIZ / "tests" / "js" / "escolhas.js")], input=json.dumps(dados), text=True, capture_output=True, timeout=60, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        saida = json.loads(r.stdout)
        self.assertEqual(saida["erros"], [], saida["erros"])


if __name__ == "__main__":
    unittest.main()
