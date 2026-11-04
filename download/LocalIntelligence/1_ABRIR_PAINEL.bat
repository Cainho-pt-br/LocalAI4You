@echo off
title Local AI Search - Painel
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python nao encontrado.
  echo Instale o Python 3.10 ou mais recente: https://www.python.org/downloads/
  echo No instalador, marque "Add Python to PATH". Depois abra este arquivo de novo.
  pause
  exit /b 1
)
rem Sobe o Ollama se precisar (flash attention + KV cache q8_0), abre o painel no navegador.
%PY% cli.py painel
pause
