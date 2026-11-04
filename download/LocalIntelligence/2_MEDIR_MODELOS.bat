@echo off
title Local Intelligence - Medir modelos
cd /d "%~dp0"
echo Mede todos os modelos instalados no protocolo atual (retoma de onde parou).
echo Niveis: rapido (~5 min/modelo), padrao (~15-45 min/modelo), profundo (~2x).
echo A GPU fica ocupada: nao rode jogos durante a medicao.
echo.
set /p NIVEL=Nivel [padrao]: 
if "%NIVEL%"=="" set NIVEL=padrao
python cli.py bench --nivel %NIVEL%
pause
