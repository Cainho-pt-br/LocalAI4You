@echo off
chcp 65001 >nul
title Desinstalar Local AI Search
set "DESTINO=%LOCALAPPDATA%\Programs\Local AI Search"
choice /c SN /m "Remover o Local AI Search deste computador (os modelos do Ollama continuam)"
if errorlevel 2 exit /b 0
powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '%DESTINO%\*' } | Stop-Process -Force" >nul 2>nul
del /q "%USERPROFILE%\Desktop\Local AI Search.lnk" 2>nul
powershell -NoProfile -Command "Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Local AI Search.lnk'); Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Programs')) 'Local AI Search')"
echo Removido. Esta janela vai fechar.
start "" /b cmd /c "timeout /t 2 >nul & rmdir /s /q ""%DESTINO%"""
exit /b 0
