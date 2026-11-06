@echo off
title Local AI 4 You - Medir modelos
cd /d "%~dp0"
call deploy\achar-python.bat
if not defined PY (
  echo Python nao encontrado.
  echo Abra primeiro o 1_ABRIR_PAINEL.bat: ele instala o que falta.
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
