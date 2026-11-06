@echo off
chcp 65001 >nul
title Local AI 4 You
cd /d "%~dp0"
call deploy\achar-python.bat

if not defined PY (
  echo.
  echo  Para abrir o painel falta o Python ^(gratuito, ~30 MB^).
  where winget >nul 2>nul
  if errorlevel 1 goto :python_manual
  choice /c SN /m " Instalar agora automaticamente"
  if errorlevel 2 goto :python_manual
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  call deploy\achar-python.bat
)
if not defined PY goto :python_manual

rem Ollama: o programa que roda os modelos. Sem ele o painel abre, mas so mostra o Radar.
set "TEM_OLLAMA="
where ollama >nul 2>nul && set "TEM_OLLAMA=1"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "TEM_OLLAMA=1"
if not defined TEM_OLLAMA (
  echo.
  echo  O Ollama ^(gratuito^) roda os modelos de IA no seu PC. Ele ainda nao esta instalado.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo  Baixe em https://ollama.com/download - o painel abre mesmo assim e mostra o passo a passo.
  ) else (
    choice /c SN /m " Instalar o Ollama agora"
    if not errorlevel 2 winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
  )
)

echo.
echo  Abrindo o painel no navegador... ^(deixe esta janela aberta; feche-a para encerrar^)
%PY% cli.py painel
pause
exit /b 0

:python_manual
echo.
echo  Instale o Python 3.10 ou mais recente: https://www.python.org/downloads/
echo  No instalador, marque "Add Python to PATH". Depois abra este arquivo de novo.
start "" https://www.python.org/downloads/
pause
exit /b 1
