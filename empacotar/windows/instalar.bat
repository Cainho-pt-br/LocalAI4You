@echo off
chcp 65001 >nul
title Instalar Local AI 4 You
rem Instala por usuário (sem administrador): copia para %LOCALAPPDATA%\Programs\Local AI 4 You e cria atalhos
rem que chamam o pythonw.exe OFICIAL embutido (assinado pela Python Software Foundation): sem janela preta e sem
rem executável desconhecido para o Windows bloquear.
cd /d "%~dp0"
set "DESTINO=%LOCALAPPDATA%\Programs\Local AI 4 You"
echo.
echo  Instalando o Local AI 4 You...
if exist "%DESTINO%\app\python\pythonw.exe" (
  powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '%DESTINO%\*' } | Stop-Process -Force" >nul 2>nul
)
robocopy "%~dp0app" "%DESTINO%\app" /E /NFL /NDL /NJH /NJS /NP /XD estado relatorios >nul
copy /y "%~dp0LEIA-ME.txt" "%DESTINO%\LEIA-ME.txt" >nul
copy /y "%~dp0app\desinstalar.bat" "%DESTINO%\Desinstalar.bat" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d='%DESTINO%'; Get-ChildItem -LiteralPath $d -Recurse -File | Unblock-File;" ^
  "$w=New-Object -ComObject WScript.Shell;" ^
  "foreach($p in @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) 'Local AI 4 You'))){" ^
  "  New-Item -ItemType Directory -Force -Path $p | Out-Null;" ^
  "  $s=$w.CreateShortcut((Join-Path $p 'Local AI 4 You.lnk'));" ^
  "  $s.TargetPath=(Join-Path $d 'app\python\pythonw.exe'); $s.Arguments='cli.py painel'; $s.WorkingDirectory=(Join-Path $d 'app');" ^
  "  $s.IconLocation=(Join-Path $d 'app\web\icone.ico'); $s.Description='Descubra e meça IA local no seu computador'; $s.Save() }" ^
  "$m=(Join-Path ([Environment]::GetFolderPath('Programs')) 'Local AI 4 You');" ^
  "$u=$w.CreateShortcut((Join-Path $m 'Desinstalar Local AI 4 You.lnk')); $u.TargetPath=(Join-Path $d 'Desinstalar.bat'); $u.Save()"
if errorlevel 1 (
  echo  Nao consegui criar os atalhos. Voce ainda pode abrir pelo arquivo:
  echo  %DESTINO%\app\python\pythonw.exe cli.py painel
)

set "TEM_OLLAMA="
where ollama >nul 2>nul && set "TEM_OLLAMA=1"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "TEM_OLLAMA=1"
if not defined TEM_OLLAMA (
  where winget >nul 2>nul
  if not errorlevel 1 (
    echo.
    echo  O Ollama ^(gratuito^) e o programa que roda os modelos de IA.
    choice /c SN /m " Instalar o Ollama agora"
    if not errorlevel 2 winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
  )
)

echo.
echo  Pronto! O atalho "Local AI 4 You" esta na Area de Trabalho e no menu Iniciar.
echo  Abrindo agora... ^(esta pasta baixada pode ser apagada^)
start "" "%DESTINO%\app\python\pythonw.exe" cli.py painel
timeout /t 4 >nul
exit /b 0
