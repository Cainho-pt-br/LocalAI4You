@echo off
title Local AI Search - Procurar modelos novos
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
rem Varre Ollama + Hugging Face, lista o que e novo e grava relatorios\AAAA-MM-DD-decisao.md. Nao baixa nada.
%PY% cli.py vigia --relatorio
pause
