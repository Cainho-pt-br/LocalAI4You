@echo off
title Local Intelligence - Painel
cd /d "%~dp0"
where python >/dev/null 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale o Python 3 e tente de novo.
  pause
  exit /b 1
)
rem Sobe o Ollama se precisar (flash attention + KV cache q8_0), o painel e abre o navegador.
python cli.py painel
pause
