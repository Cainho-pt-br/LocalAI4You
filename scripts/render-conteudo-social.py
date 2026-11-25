#!/usr/bin/env python3
"""Renderiza os pacotes gerados por scripts/gerar-conteudo-social.js em mídia pronta para postar:
   • slides/slide-*.png   (1080×1350 · Carrossel Instagram / LinkedIn / X)
   • video-9x16.mp4       (1080×1920 · TikTok / Reels / YouTube Shorts com narração Edge-TTS)

Dependências (instaladas automaticamente no workflow .github/workflows/conteudo-social.yml):
   pip install playwright edge-tts
   playwright install chromium
   ffmpeg no PATH
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


async def gerar_audio(texto: str, voz: str, destino: Path) -> None:
    import edge_tts
    com = edge_tts.Communicate(texto, voz, rate="+6%")
    await com.save(str(destino))


def duracao_audio(caminho: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(caminho)],
        text=True,
    ).strip()
    return max(2.2, float(out) + 0.35)


def renderizar_pacote(pasta: Path) -> None:
    roteiro_path = pasta / "roteiro.json"
    if not roteiro_path.exists():
        return
    roteiro = json.loads(roteiro_path.read_text(encoding="utf-8"))
    slides_dir = pasta / "slides"
    cenas_dir = pasta / "cenas-video"
    tmp_dir = pasta / "_tmp"
    tmp_dir.mkdir(exist_ok=True)

    # Narração antes do Playwright: o sync_playwright mantém um event loop aberto
    # nesta thread, e asyncio.run() falha dentro dele.
    for idx, cena in enumerate(roteiro["cenas"], start=1):
        asyncio.run(gerar_audio(cena["fala"], roteiro["voz_edge_tts"], tmp_dir / f"cena-{idx}.mp3"))

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1) Carrossel 1080x1350
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        for html in sorted(slides_dir.glob("slide-*.html")):
            page.goto(html.resolve().as_uri(), wait_until="load")
            page.screenshot(path=str(html.with_suffix(".png")))

        # 2) Cenas do vídeo vertical 1080x1920
        page_v = browser.new_page(viewport={"width": 1080, "height": 1920})
        segmentos: list[Path] = []
        for idx, cena in enumerate(roteiro["cenas"], start=1):
            html = pasta / cena["arquivo"]
            img = tmp_dir / f"cena-{idx}.png"
            aud = tmp_dir / f"cena-{idx}.mp3"
            seg = tmp_dir / f"seg-{idx}.mp4"

            page_v.goto(html.resolve().as_uri(), wait_until="load")
            page_v.screenshot(path=str(img))
            dur = duracao_audio(aud)

            # Leve zoom-in (Ken Burns sutil) + áudio sincronizado
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-i", str(aud),
                "-t", f"{dur:.2f}",
                "-vf", "scale=1080:1920,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k", "-shortest",
                str(seg),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            segmentos.append(seg)

        browser.close()

    # 3) Concatena segmentos em video-9x16.mp4
    lista = tmp_dir / "lista.txt"
    lista.write_text("\n".join(f"file '{s.resolve()}'" for s in segmentos), encoding="utf-8")
    saida = pasta / "video-9x16.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
        "-c", "copy", str(saida),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Limpa temporários
    for f in tmp_dir.iterdir():
        f.unlink()
    tmp_dir.rmdir()
    print(f"Renderizado: {pasta} -> slides PNG + {saida.name}")


def main() -> None:
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("conteudo-social")
    for roteiro in sorted(alvo.rglob("roteiro.json")):
        renderizar_pacote(roteiro.parent)


if __name__ == "__main__":
    main()
