"""Gerador determinístico de imagens PNG (somente stdlib: zlib + struct + base64) para a suíte de Visão.

Gera 18 itens divididos em 3 categorias práticas (intercaladas para manter qualquer prefixo balanceado):
  1. ocr_nota: leitura de cupom/fatura (código, valor total, item específico);
  2. grafico: leitura de gráfico de barras com valores e rótulos (qual é o maior/menor ou valor de uma barra);
  3. painel: inspeção de cartão de status/alerta de servidor (porta, status, código de erro).
"""
from __future__ import annotations

import base64
import json
import struct
import zlib
from typing import Dict, List, Tuple

# Fonte 5x7 compacta (cada caractere = 7 linhas de 5 bits, MSB à esquerda), escalada em 3x na imagem (15x21 px por letra)
_FONTE: Dict[str, Tuple[int, ...]] = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 6, 8, 16, 31),
    "3": (31, 2, 4, 6, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (28, 18, 17, 17, 17, 18, 28),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 27, 17),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    ":": (0, 4, 4, 0, 4, 4, 0),
    ".": (0, 0, 0, 0, 0, 6, 6),
    ",": (0, 0, 0, 0, 6, 4, 8),
    "-": (0, 0, 0, 31, 0, 0, 0),
    "/": (1, 2, 2, 4, 8, 8, 16),
    "%": (25, 26, 2, 4, 8, 19, 19),
    "$": (4, 15, 20, 14, 5, 30, 4),
    "#": (10, 31, 10, 10, 31, 10, 0),
    "(": (2, 4, 8, 8, 8, 4, 2),
    ")": (8, 4, 2, 2, 2, 4, 8),
    "=": (0, 0, 31, 0, 31, 0, 0),
}


class Tela:
    def __init__(self, larg: int, alt: int, fundo: Tuple[int, int, int] = (248, 249, 252)):
        self.larg = larg
        self.alt = alt
        self.buf = bytearray(fundo * (larg * alt))

    def ret(self, x: int, y: int, w: int, h: int, cor: Tuple[int, int, int]) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.larg, x + w), min(self.alt, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        linha_cor = bytes(cor) * (x1 - x0)
        stride = self.larg * 3
        for yy in range(y0, y1):
            ini = yy * stride + x0 * 3
            self.buf[ini:ini + len(linha_cor)] = linha_cor

    def circ(self, cx: int, cy: int, r: int, cor: Tuple[int, int, int]) -> None:
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self.ret(cx - dx, cy + dy, 2 * dx + 1, 1, cor)

    def tri(self, cx: int, cy: int, r: int, cor: Tuple[int, int, int]) -> None:
        for i in range(2 * r):
            meia = int(r * i / (2 * r)) + 1
            self.ret(cx - meia, cy - r + i, 2 * meia, 1, cor)

    def texto(self, x: int, y: int, txt: str, cor: Tuple[int, int, int] = (20, 22, 28), escala: int = 3) -> None:
        cx = x
        for ch in txt.upper():
            grade = _FONTE.get(ch, _FONTE[" "])
            for gy, bits in enumerate(grade):
                for gx in range(5):
                    if (bits >> (4 - gx)) & 1:
                        self.ret(cx + gx * escala, y + gy * escala, escala, escala, cor)
            cx += 6 * escala

    def png_b64(self) -> str:
        stride = self.larg * 3
        bruto = bytearray()
        for y in range(self.alt):
            bruto.append(0)  # filtro None
            bruto.extend(self.buf[y * stride:(y + 1) * stride])

        def bloco(tipo: bytes, dados: bytes) -> bytes:
            crc = zlib.crc32(tipo + dados) & 0xFFFFFFFF
            return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", crc)

        ihdr = struct.pack(">IIBBBBB", self.larg, self.alt, 8, 2, 0, 0, 0)
        idat = zlib.compress(bytes(bruto), level=6)
        png = b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", ihdr) + bloco(b"IDAT", idat) + bloco(b"IEND", b"")
        return base64.b64encode(png).decode("ascii")


def _img_nota(num_nota: str, item_nome: str, qtd: int, total: str, extra: str) -> str:
    t = Tela(420, 260, (255, 255, 255))
    t.ret(12, 12, 396, 236, (242, 244, 248))
    t.ret(12, 12, 396, 44, (24, 36, 68))
    t.texto(26, 24, f"NOTA FISCAL #{num_nota}", (255, 255, 255), 3)
    t.texto(26, 74, f"ITEM: {item_nome}", (20, 22, 28), 3)
    t.texto(26, 110, f"QTD: {qtd} UN", (60, 64, 76), 3)
    t.texto(26, 146, f"SETOR: {extra}", (60, 64, 76), 3)
    t.ret(24, 182, 372, 4, (190, 195, 208))
    t.texto(26, 200, f"TOTAL R$ {total}", (18, 115, 52), 3)
    return t.png_b64()


def _img_grafico(titulo: str, barras: List[Tuple[str, int]]) -> str:
    t = Tela(440, 270, (255, 255, 255))
    t.ret(10, 10, 420, 38, (35, 42, 58))
    t.texto(22, 20, titulo, (255, 255, 255), 2)
    cores = [(47, 85, 212), (21, 128, 61), (180, 83, 9), (109, 63, 199)]
    maior = max(v for _, v in barras) or 1
    for i, (rot, val) in enumerate(barras):
        y = 66 + i * 48
        t.texto(22, y + 6, rot, (20, 22, 28), 3)
        larg = max(12, int(200 * val / maior))
        t.ret(130, y, larg, 30, cores[i % len(cores)])
        t.texto(138 + larg, y + 6, str(val), (20, 22, 28), 3)
    return t.png_b64()


def _img_painel(servico: str, porta: int, status: str, erro_cod: str) -> str:
    t = Tela(420, 240, (24, 26, 32))
    cor_st = (32, 148, 72) if status == "ONLINE" else (196, 48, 40)
    t.ret(16, 16, 388, 208, (36, 40, 50))
    t.ret(30, 30, 160, 34, cor_st)
    t.texto(42, 38, status, (255, 255, 255), 3)
    t.texto(30, 82, f"SRV: {servico}", (235, 238, 245), 3)
    t.texto(30, 120, f"PORTA: {porta}", (180, 195, 255), 3)
    t.texto(30, 158, f"CODIGO: {erro_cod}", (255, 196, 88), 3)
    return t.png_b64()


def construir_itens(maximo: int = 18) -> List[dict]:
    notas_cfg = [
        ("4092", "CABO DP", 3, "145", "REDE", "Qual é o valor total em reais (apenas o número) mostrado na nota fiscal?", "145", "numero"),
        ("7184", "SSD NVME", 2, "680", "STORAGE", "Qual é o número da nota fiscal (apenas os dígitos após #)?", "7184", "numero"),
        ("3310", "COOLER", 4, "220", "TERMICO", "Qual é a quantidade (QTD) em unidades mostrada na imagem? Responda só o número.", "4", "numero"),
        ("8821", "FONTE ATX", 1, "590", "ENERGIA", "Qual é o valor total em reais (apenas o número) mostrado na nota?", "590", "numero"),
        ("5506", "MEMORIA", 2, "410", "HARDWARE", "Qual é o nome exato da palavra que aparece após 'SETOR:' na imagem?", "HARDWARE", "texto"),
        ("9043", "SWITCH", 5, "375", "INFRA", "Qual é o número da nota fiscal (apenas os dígitos após #)?", "9043", "numero"),
    ]
    graficos_cfg = [
        ("LATENCIA MS", [("A", 24), ("B", 85), ("C", 42), ("D", 19)], "Qual barra (A, B, C ou D) possui o MAIOR valor no gráfico? Responda apenas a letra.", "B", "letra"),
        ("VENDAS UN", [("A", 60), ("B", 15), ("C", 92), ("D", 44)], "Qual barra (A, B, C ou D) possui o MAIOR valor no gráfico? Responda apenas a letra.", "C", "letra"),
        ("CONSUMO W", [("A", 110), ("B", 75), ("C", 40), ("D", 95)], "Qual barra (A, B, C ou D) possui o MENOR valor no gráfico? Responda apenas a letra.", "C", "letra"),
        ("LOTES OK", [("A", 32), ("B", 64), ("C", 128), ("D", 48)], "Qual é o valor numérico da barra C no gráfico? Responda apenas o número.", "128", "numero"),
        ("TAXA TOK", [("A", 98), ("B", 45), ("C", 72), ("D", 61)], "Qual barra (A, B, C ou D) possui o MAIOR valor no gráfico? Responda apenas a letra.", "A", "letra"),
        ("ERROS DIA", [("A", 12), ("B", 38), ("C", 27), ("D", 8)], "Qual barra (A, B, C ou D) possui o MENOR valor no gráfico? Responda apenas a letra.", "D", "letra"),
    ]
    paineis_cfg = [
        ("REDIS", 6379, "ONLINE", "E00", "Qual é o número da PORTA mostrada no painel? Responda apenas o número.", "6379", "numero"),
        ("BROKER", 8765, "ALERTA", "E42", "Retorne APENAS um JSON com as chaves \"porta\" (inteiro) e \"codigo\" (string) lidas na imagem.", '{"porta": 8765, "codigo": "E42"}', "json"),
        ("OLLAMA", 11434, "ONLINE", "E01", "Qual é o número da PORTA mostrada no painel? Responda apenas o número.", "11434", "numero"),
        ("POSTGRES", 5432, "ALERTA", "E19", "Qual é o código mostrado após 'CODIGO:' na imagem? Responda apenas o código.", "E19", "texto"),
        ("WORKER", 9090, "ONLINE", "E07", "Retorne APENAS um JSON com as chaves \"porta\" (inteiro) e \"codigo\" (string) lidas na imagem.", '{"porta": 9090, "codigo": "E07"}', "json"),
        ("GATEWAY", 4430, "ALERTA", "E88", "Qual é o nome do serviço mostrado após 'SRV:' na imagem? Responda apenas a palavra.", "GATEWAY", "texto"),
    ]

    g_notas = [
        {"id": f"vis-nota-{i+1}", "categoria": "ocr_nota", "pergunta": perg, "resposta": resp, "tipo": tipo,
         "imagem": _img_nota(num, item, qtd, tot, ext)}
        for i, (num, item, qtd, tot, ext, perg, resp, tipo) in enumerate(notas_cfg)
    ]
    g_graf = [
        {"id": f"vis-graf-{i+1}", "categoria": "grafico", "pergunta": perg, "resposta": resp, "tipo": tipo,
         "imagem": _img_grafico(tit, bs)}
        for i, (tit, bs, perg, resp, tipo) in enumerate(graficos_cfg)
    ]
    g_painel = [
        {"id": f"vis-painel-{i+1}", "categoria": "painel", "pergunta": perg, "resposta": resp, "tipo": tipo,
         "imagem": _img_painel(srv, prt, st, cod)}
        for i, (srv, prt, st, cod, perg, resp, tipo) in enumerate(paineis_cfg)
    ]

    # Intercala os 3 grupos para que rápido (6), padrão (12) e profundo (18) tenham proporção idêntica
    out: List[dict] = []
    for i in range(6):
        out.extend([g_notas[i], g_graf[i], g_painel[i]])
    return out[:maximo]


# ------------------------------------------------------------------ teste "leve" de visão: o que um modelo pequeno (Moondream & cia.) realmente faz
# Imagens simples, perguntas curtas em inglês (modelos pequenos são fracos em português), resposta de uma palavra ou número.
# Uma categoria vem de um uso real: contar sementes numa bandeja escura quadriculada.

_CORES = {"red": (220, 40, 40), "green": (40, 170, 60), "blue": (40, 80, 220), "yellow": (240, 210, 30),
          "orange": (245, 140, 20), "purple": (140, 60, 180)}


def _img_bandeja(n: int, seed: int) -> str:
    import random
    rnd = random.Random(seed)
    lado, celula = 320, 40
    t = Tela(lado, lado, (38, 40, 46))
    for k in range(0, lado + 1, celula):          # grade da bandeja
        t.ret(k, 0, 2, lado, (68, 70, 78))
        t.ret(0, k, lado, 2, (68, 70, 78))
    celulas = [(i, j) for i in range(8) for j in range(8)]
    rnd.shuffle(celulas)
    for i, j in celulas[:n]:                       # uma semente por casa, ligeiramente fora do centro
        t.circ(i * celula + 20 + rnd.randint(-5, 5), j * celula + 20 + rnd.randint(-5, 5), rnd.randint(9, 12), (226, 196, 140))
    return t.png_b64()


def _img_forma(forma: str, cor: str) -> str:
    t = Tela(320, 320, (250, 250, 250))
    if forma == "circle":
        t.circ(160, 160, 90, _CORES[cor])
    elif forma == "square":
        t.ret(70, 70, 180, 180, _CORES[cor])
    else:
        t.tri(160, 160, 95, _CORES[cor])
    return t.png_b64()


def _img_lado(lado: str) -> str:
    t = Tela(320, 320, (250, 250, 250))
    t.circ(70 if lado == "left" else 250, 160, 55, _CORES["red"])
    t.ret(205 if lado == "left" else 30, 105, 90, 110, (130, 130, 135))
    return t.png_b64()


def _img_numero(txt: str) -> str:
    t = Tela(320, 160, (250, 250, 250))
    escala = 9 if len(txt) <= 3 else 7
    t.texto(160 - len(txt) * 3 * escala, 160 // 2 - 3 * escala, txt, (20, 22, 28), escala)
    return t.png_b64()


def construir_itens_leve(maximo: int = 30) -> List[dict]:
    contagens = [3, 5, 7, 2, 9, 12]
    cores = ["red", "green", "blue", "yellow", "orange", "purple"]
    formas = [("circle", "blue"), ("square", "red"), ("triangle", "green"), ("circle", "orange"), ("square", "purple"), ("triangle", "yellow")]
    lados = ["left", "right", "right", "left", "left", "right"]
    numeros = ["482", "7315", "29", "640", "1853", "96"]
    g_cont = [{"id": f"vl2-contagem-{i+1}", "categoria": "contagem", "tipo": "contagem", "resposta": str(n),
               "pergunta": "How many light round seeds are on the dark tray?", "imagem": _img_bandeja(n, 1000 + i)}
              for i, n in enumerate(contagens)]
    g_cor = [{"id": f"vl2-cor-{i+1}", "categoria": "cor", "tipo": "cor", "resposta": c,
              "pergunta": "What color is the shape?", "imagem": _img_forma("circle", c)} for i, c in enumerate(cores)]
    g_forma = [{"id": f"vl2-forma-{i+1}", "categoria": "forma", "tipo": "forma", "resposta": f,
                "pergunta": "Is the shape a circle, a square or a triangle?", "imagem": _img_forma(f, c)} for i, (f, c) in enumerate(formas)]
    g_lado = [{"id": f"vl2-lado-{i+1}", "categoria": "posicao", "tipo": "lado", "resposta": s,
               "pergunta": "Is the red circle on the left or on the right side of the image?", "imagem": _img_lado(s)} for i, s in enumerate(lados)]
    g_num = [{"id": f"vl2-numero-{i+1}", "categoria": "leitura", "tipo": "contagem", "resposta": n,
              "pergunta": "What number is written in the image?", "imagem": _img_numero(n)} for i, n in enumerate(numeros)]
    out: List[dict] = []
    for i in range(6):   # rodízio: qualquer prefixo (5, 10, 20, 30) tem as 5 categorias em proporção igual
        out.extend([g_cont[i], g_cor[i], g_forma[i], g_lado[i], g_num[i]])
    return out[:maximo]


def itens_fotos(pasta, maximo: int = 999) -> List[dict]:
    """Fotos REAIS suas: `data/fotos-visao/gabarito.json` = {"foto.jpg": {"contagem": 23, "detector": 22, "objeto": "seeds"}}.
    `detector` é o que o sistema atual contou (opcional): serve para comparar modelo × detector na mesma foto."""
    import hashlib
    arq = pasta / "gabarito.json"
    if not arq.exists():
        return []
    try:
        gab = json.loads(arq.read_text("utf-8"))
    except Exception:
        return []
    itens = []
    for nome in sorted(gab):
        info, f = gab[nome], pasta / nome
        if not f.is_file() or f.stat().st_size > 6_000_000 or not isinstance(info, dict) or "contagem" not in info:
            continue
        dados = f.read_bytes()
        obj = str(info.get("objeto") or "seeds")
        itens.append({"id": f"foto-{nome}-{hashlib.sha256(dados).hexdigest()[:8]}", "categoria": "foto", "tipo": "contagem",
                      "resposta": str(int(info["contagem"])), "detector": info.get("detector"), "arquivo": nome,
                      "pergunta": f"How many {obj} are in the image?", "imagem": base64.b64encode(dados).decode("ascii")})
    return itens[:maximo]
