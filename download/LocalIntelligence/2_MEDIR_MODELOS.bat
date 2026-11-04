@echo off
title Local AI Search - Medir modelos
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
echo Mede todos os modelos instalados no protocolo atual (retoma de onde parou).
echo Niveis: rapido (~5 min/modelo), padrao (~15-45 min/modelo), profundo (~2x).
echo A GPU fica ocupada: nao rode jogos durante a medicao.
echo.
set /p NIVEL=Nivel [padrao]: 
if "%NIVEL%"=="" set NIVEL=padrao
%PY% cli.py bench --nivel %NIVEL%
pause
