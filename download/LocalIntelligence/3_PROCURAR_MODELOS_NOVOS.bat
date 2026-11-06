@echo off
title Local AI 4 You - Procurar modelos novos
cd /d "%~dp0"
call deploy\achar-python.bat
if not defined PY (
  echo Python nao encontrado.
  echo Abra primeiro o 1_ABRIR_PAINEL.bat: ele instala o que falta.
  pause
  exit /b 1
)
rem Varre Ollama + Hugging Face, lista o que e novo e grava relatorios\AAAA-MM-DD-decisao.md. Nao baixa nada.
%PY% cli.py vigia --relatorio
pause
