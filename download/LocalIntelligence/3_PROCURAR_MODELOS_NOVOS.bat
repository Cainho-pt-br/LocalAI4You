@echo off
title Local Intelligence - Procurar modelos novos
cd /d "%~dp0"
rem Varre Ollama + Hugging Face, lista o que e novo e grava relatorios\AAAA-MM-DD-decisao.md. Nao baixa nada.
python cli.py vigia --relatorio
pause
