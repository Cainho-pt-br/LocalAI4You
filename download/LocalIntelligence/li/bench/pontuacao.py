"""Corretores determinísticos de cada suíte (sem juiz-LLM: nota reproduzível).

Mudanças em relação ao protocolo v1 (todas deixam a nota MAIS fiel ao benchmark original):
  • BFCL: argumento opcional pode ser omitido (o gabarito oficial marca com "") e strings são
    comparadas como no BFCL (minúsculas, sem pontuação/espaços); v1 reprovava quem omitia opcional.
  • IFEval: regras como no código oficial (bullets exatos, 'less than' estrito, JSON com cerca).
  • Letra de múltipla escolha: lê "Resposta: C", "**C**", linha só com a letra — antes pegava
    qualquer 'A' solto (artigo em português!).
  • HumanEval: mantém os imports do enunciado e as funções auxiliares, e bloqueia imports perigosos.
  • Visão: avalia leitura determinística de número, letra de gráfico, texto exato e extração em JSON.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ..util import SEM_JANELA

# ------------------------------------------------------------------ texto da resposta

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def limpar(texto: str) -> str:
    t = _THINK.sub("", texto or "")
    if "</think>" in t:  # abertura perdida
        t = t.split("</think>")[-1]
    return t.strip()


def texto_resposta(resp: dict) -> str:
    return limpar((resp.get("message") or {}).get("content", ""))


# ------------------------------------------------------------------ múltipla escolha

def extrair_letra(texto: str, validas: str) -> str:
    t = limpar(texto)
    if not t:
        return ""
    cls = f"[{validas}]"
    linhas = [l.strip() for l in t.splitlines() if l.strip()]
    if linhas:
        m = re.fullmatch(rf"\(?\**({cls})\**\)?[.):]?", linhas[0], re.I) or re.fullmatch(rf"\(?\**({cls})\**\)?[.):]?", linhas[-1], re.I)
        if m:
            return m.group(1).upper()
    for pad in (rf"(?:resposta|alternativa|answer|op[cç][aã]o|letra|barra)[^A-Za-z0-9]{{0,12}}\(?\**({cls})\b",
                rf"\*\*\(?({cls})\)?\*\*", rf"\\boxed\{{\(?({cls})\)?\}}", rf"(?:é|is)\s+\(?\**({cls})\)?\b"):
        achados = re.findall(pad, t, re.I)
        if achados:
            return achados[-1].upper()
    soltas = re.findall(rf"(?<![A-Za-z0-9À-ú])({cls})(?![A-Za-z0-9À-ú])", t)
    return soltas[-1].upper() if soltas else ""


# ------------------------------------------------------------------ BFCL

def _norm_str(s: str) -> str:
    return re.sub(r"[ \,\.\/\-\_\*\^]", "", s).lower().replace("'", '"')


def _valor_igual(got: Any, ok: Any) -> bool:
    if isinstance(got, str) and isinstance(ok, str):
        return _norm_str(got) == _norm_str(ok)
    if isinstance(got, bool) or isinstance(ok, bool):
        return got == ok
    if isinstance(got, (int, float)) and isinstance(ok, (int, float)):
        return float(got) == float(ok)
    if isinstance(got, list) and isinstance(ok, list):
        return len(got) == len(ok) and all(_valor_igual(a, b) for a, b in zip(got, ok))
    if isinstance(got, dict) and isinstance(ok, dict):
        return set(got) == set(ok) and all(_valor_igual(got[k], ok[k]) for k in ok)
    return got == ok


def _alguma_igual(got: Any, permitidos: Any) -> bool:
    if not isinstance(permitidos, list):
        permitidos = [permitidos]
    return any(_valor_igual(got, p) for p in permitidos)


def chamada_correta(nome: Optional[str], args: Any, gabarito: Any) -> Tuple[bool, str]:
    alternativas = gabarito if isinstance(gabarito, list) else [gabarito]
    viu_nome = False
    for esperado in alternativas:
        if not isinstance(esperado, dict) or len(esperado) != 1:
            continue
        nome_ok, args_ok = next(iter(esperado.items()))
        if nome != nome_ok:
            continue
        viu_nome = True
        if not isinstance(args, dict) or not isinstance(args_ok, dict):
            continue
        if any(k not in args_ok for k in args):  # argumento inventado
            continue
        bom = True
        for k, permitidos in args_ok.items():
            lista = permitidos if isinstance(permitidos, list) else [permitidos]
            if k not in args:
                if "" in lista:  # opcional: pode omitir
                    continue
                bom = False
                break
            if not _alguma_igual(args[k], lista):
                bom = False
                break
        if bom:
            return True, "correto"
    return False, ("argumentos_errados" if viu_nome else "ferramenta_errada")


def json_da_resposta(s: str) -> Any:
    s = limpar(s)
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip())
    try:
        return json.loads(s)
    except Exception:
        pass
    for a, b in (("{", "}"), ("[", "]")):
        i, j = s.find(a), s.rfind(b)
        if i >= 0 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                continue
    return None


def bfcl_prompt(resposta: str, gabarito: Any) -> Tuple[bool, str]:
    obj = json_da_resposta(resposta)
    if isinstance(obj, list) and obj:
        obj = obj[0]
    if not isinstance(obj, dict):
        return False, "json_invalido"
    nome = obj.get("tool") or obj.get("name") or obj.get("function")
    args = obj.get("arguments", obj.get("args", obj.get("parameters", {})))
    if isinstance(nome, dict):
        args, nome = nome.get("arguments", nome.get("args", args)), nome.get("name")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return False, "argumentos_invalidos"
    return chamada_correta(nome, args, gabarito)


def bfcl_nativo(resp: dict, gabarito: Any) -> Tuple[bool, str, Optional[dict]]:
    chamadas = (resp.get("message") or {}).get("tool_calls") or []
    if not chamadas:
        return False, "sem_chamada", None
    f = chamadas[0].get("function", {})
    ok, why = chamada_correta(f.get("name"), f.get("arguments", {}), gabarito)
    return ok, why, {"tool": f.get("name"), "arguments": f.get("arguments", {})}


def normalizar_schema(schema: Any) -> Any:
    """O BFCL usa 'dict'/'list'/'float'; a API de tools do Ollama quer JSON Schema."""
    if isinstance(schema, dict):
        t = schema.get("type")
        if t == "dict":
            schema["type"] = "object"
        elif t == "list":
            schema["type"] = "array"
        elif t == "float":
            schema["type"] = "number"
        elif t == "tuple":
            schema["type"] = "array"
        for v in list(schema.values()):
            normalizar_schema(v)
    elif isinstance(schema, list):
        for x in schema:
            normalizar_schema(x)
    return schema


# ------------------------------------------------------------------ IFEval (regras do código oficial)

def ifeval(regra: str, kw: dict, texto: str) -> Optional[bool]:
    t = limpar(texto)
    if regra == "punctuation:no_comma":
        return "," not in t
    if regra == "change_case:english_lowercase":
        return t.islower()
    if regra == "change_case:english_capital":
        return t.isupper()
    if regra == "keywords:existence":
        return all(re.search(re.escape(str(k)), t, re.I) for k in kw.get("keywords", []))
    if regra == "keywords:forbidden_words":
        return not any(re.search(r"\b" + re.escape(str(w)) + r"\b", t, re.I) for w in kw.get("forbidden_words", []))
    if regra == "keywords:frequency":
        n = len(re.findall(re.escape(str(kw.get("keyword", ""))), t, re.I))
        alvo = int(kw.get("frequency", 0))
        return n < alvo if kw.get("relation") == "less than" else n >= alvo
    if regra == "detectable_format:json_format":
        v = t.strip().removeprefix("```json").removeprefix("```JSON").removeprefix("```").removesuffix("```").strip()
        try:
            json.loads(v)
            return True
        except Exception:
            return False
    if regra == "detectable_format:number_bullet_lists":
        n = len(re.findall(r"^\s*\*[^\*].*$", t, re.M)) + len(re.findall(r"^\s*-.*$", t, re.M))
        return n == int(kw.get("num_bullets", 0))
    if regra == "startend:end_checker":
        return t.strip().strip('"').lower().endswith(str(kw.get("end_phrase", "")).strip().lower())
    return None


# ------------------------------------------------------------------ GSM8K

def numero_final(texto: str) -> str:
    t = limpar(texto)
    for pad in (r"####\s*\$?\s*(-?[\d.,]+)", r"\\boxed\{\$?\s*(-?[\d.,]+)", r"(?:resposta final|final answer|answer is|a resposta é|resultado final)[^\d\-]{0,20}(-?[\d.,]+)"):
        m = re.findall(pad, t, re.I)
        if m:
            return m[-1].replace(",", "").rstrip(".")
    nums = re.findall(r"(?<![A-Za-z])-?\d[\d,]*\.?\d*", t)
    return nums[-1].replace(",", "").rstrip(".") if nums else ""


def gsm8k(texto: str, esperado: str) -> Tuple[bool, str]:
    got = numero_final(texto)
    try:
        return float(got) == float(esperado.replace(",", "")), got
    except Exception:
        return False, got


# ------------------------------------------------------------------ Visão (OCR, gráficos e painéis)

def visao(item: dict, texto: str) -> Tuple[bool, str]:
    t = limpar(texto)
    tipo = item.get("tipo", "texto")
    esp = str(item.get("resposta", "")).strip()
    if tipo == "numero":
        return gsm8k(t, esp)
    if tipo == "letra":
        got = extrair_letra(t, "ABCD")
        return got == esp.upper(), got
    if tipo == "json":
        obj = json_da_resposta(t)
        esp_obj = json.loads(esp)
        if not isinstance(obj, dict):
            return False, "json_invalido"
        ok = all(str(obj.get(k, "")).strip().upper() == str(v).strip().upper() for k, v in esp_obj.items())
        return ok, json.dumps(obj, ensure_ascii=False)
    # tipo == "texto"
    limpo = re.sub(r"[^A-Za-z0-9]", " ", t).upper().split()
    return esp.upper() in limpo or esp.upper() in t.upper(), t[:80]


# ------------------------------------------------------------------ HumanEval (execução em subprocesso)

_IMPORTS_OK = {"math", "re", "collections", "itertools", "typing", "heapq", "functools", "string", "decimal", "fractions",
               "bisect", "operator", "statistics", "random", "copy", "numbers", "hashlib", "json", "datetime", "textwrap",
               "array", "cmath", "enum", "dataclasses", "abc", "unittest"}
_NOMES_PROIBIDOS = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "exit", "quit", "globals", "setattr", "delattr"}


def bloqueado(codigo: str) -> Optional[str]:
    """Análise estática: não é um sandbox de verdade, só impede o óbvio (rede, disco, processos)."""
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as e:
        return f"sintaxe: {e.msg}"
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.name.split(".")[0] not in _IMPORTS_OK:
                    return f"import proibido: {a.name}"
        elif isinstance(no, ast.ImportFrom):
            if (no.module or "").split(".")[0] not in _IMPORTS_OK:
                return f"import proibido: {no.module}"
        elif isinstance(no, ast.Name) and no.id in _NOMES_PROIBIDOS:
            return f"nome proibido: {no.id}"
        elif isinstance(no, ast.Attribute) and no.attr.startswith("__") and no.attr not in ("__name__", "__init__", "__len__", "__iter__", "__next__", "__eq__", "__lt__", "__repr__", "__str__"):
            return f"atributo proibido: {no.attr}"
    return None


def extrair_codigo(texto: str) -> str:
    t = limpar(texto)
    blocos = re.findall(r"```(?:python|py)?\s*\n(.*?)```", t, re.S | re.I)
    if blocos:
        com_def = [b for b in blocos if re.search(r"^\s*def\s", b, re.M)]
        return (com_def[0] if com_def else blocos[0]).strip()
    return re.sub(r"^```\w*|```$", "", t, flags=re.M).strip()


def humaneval(item: dict, texto: str, timeout: float = 8.0) -> Tuple[bool, str]:
    codigo = extrair_codigo(texto)
    entrada = item["entrada"]
    if re.search(rf"^\s*def\s+{re.escape(entrada)}\s*\(", codigo, re.M):
        programa = item["prompt"] + "\n" + codigo
    else:
        corpo = codigo if codigo.startswith((" ", "\t")) else "\n".join("    " + l for l in codigo.splitlines())
        programa = item["prompt"] + corpo
    motivo = bloqueado(programa)
    if motivo:
        return False, f"bloqueado ({motivo})"
    programa += f"\n\n{item['teste']}\n\ncheck({entrada})\n"
    with tempfile.TemporaryDirectory(prefix="li-he-") as pasta:
        arq = Path(pasta) / "t.py"
        arq.write_text(programa, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "PYTHONIOENCODING": "utf-8"}
        try:
            r = subprocess.run([sys.executable, "-I", str(arq)], cwd=pasta, env=env, capture_output=True, text=True,
                               timeout=timeout, stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
            return r.returncode == 0, ("ok" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["erro"])[-1][:160])
        except subprocess.TimeoutExpired:
            return False, "tempo esgotado"
        except Exception as e:
            return False, str(e)[:120]


# ------------------------------------------------------------------ CAPITU

_REGISTRO = None


def capitu_registro():
    """Carrega os verificadores oficiais do CAPITU (precisam de nltk). Devolve None se indisponível."""
    global _REGISTRO
    if _REGISTRO is None:
        pasta = str((Path(__file__).resolve().parent.parent.parent / "data" / "capitu").resolve())
        if pasta not in sys.path:
            sys.path.insert(0, pasta)
        try:
            import instructions_registry  # type: ignore
            _REGISTRO = instructions_registry
        except Exception as e:  # nltk ausente / recursos não baixados
            _REGISTRO = False
            capitu_registro.erro = str(e)
    return _REGISTRO or None


def capitu(item: dict, texto: str) -> Tuple[bool, List[bool]]:
    reg = capitu_registro()
    t = limpar(texto)
    checks = []
    for iid, kw in zip(item["instrucoes"], item["kwargs"]):
        chk = reg.get_instruction_by_id(iid)(iid)
        chk.build_description(**kw)
        checks.append(bool(chk.check_following(t)))
    return bool(checks) and all(checks), checks


# ------------------------------------------------------------------ visão leve (resposta de uma palavra ou número)

_NUM_PAL = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
            "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12}
_SINONIMOS = {
    "cor": {"red": ("red", "vermelh"), "green": ("green", "verde"), "blue": ("blue", "azul"), "yellow": ("yellow", "amarel"),
            "orange": ("orange", "laranja"), "purple": ("purple", "violet", "roxo", "lilás", "lilas")},
    "forma": {"circle": ("circle", "círculo", "circulo", "round"), "square": ("square", "quadrad", "rectangle", "retângulo"),
              "triangle": ("triangle", "triângulo", "triangulo")},
    "lado": {"left": ("left", "esquerd"), "right": ("right", "direit")},
}


def inteiro_da_resposta(texto: str) -> Optional[int]:
    t = limpar(texto).lower()
    m = re.search(r"\d+", t)
    if m:
        return int(m.group())
    for p in re.findall(r"[a-zçã]+", t):
        if p in _NUM_PAL:
            return _NUM_PAL[p]
    return None


def visao_leve(item: dict, texto: str) -> Tuple[bool, str]:
    """Contagem/leitura: o número tem que ser exatamente o esperado. Cor/forma/lado: vale a PRIMEIRA opção citada na resposta."""
    t = limpar(texto)
    tipo, esp = item.get("tipo"), str(item.get("resposta", "")).strip().lower()
    if tipo == "contagem":
        got = inteiro_da_resposta(t)
        return got is not None and str(got) == esp, "" if got is None else str(got)
    tabela = _SINONIMOS.get(tipo or "", {})
    baixo = t.lower()
    achados = [(baixo.find(s), chave) for chave, sins in tabela.items() for s in sins if baixo.find(s) >= 0]
    if not achados:
        return False, t[:40]
    chave = min(achados)[1]
    return chave == esp, chave
