; Instalador do Local AI Search para Windows (Inno Setup 6). Gerado pelo workflow "Publicar app local".
; Instala por usuário (sem pedir administrador), com Python embutido: quem baixa não precisa instalar Python.
; O CI monta dist\windows (app\ + python\) e compila:  iscc /DVersao=AAAA.MM.DD empacotar\windows\LocalAISearch.iss

#ifndef Versao
  #define Versao "1.0"
#endif
#define Dist "..\..\dist\windows"

[Setup]
AppId={{6E0F3A2C-2B5D-4F0E-9C8B-7A1D4C5E9F21}
AppName=Local AI Search
AppVersion={#Versao}
AppPublisher=Local AI Search (código aberto)
AppPublisherURL=https://github.com/Cainho-pt-br/LocalAISearch
DefaultDirName={localappdata}\Programs\Local AI Search
DefaultGroupName=Local AI Search
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=LocalAISearch-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Local AI Search
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na Área de Trabalho"
Name: "ollama"; Description: "Instalar também o Ollama (gratuito, roda os modelos de IA)"; Check: not OllamaInstalado

[Files]
Source: "{#Dist}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Dist}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Dist}\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\Local AI Search"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\cli.py"" painel"; WorkingDir: "{app}\app"
Name: "{group}\Desinstalar Local AI Search"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Local AI Search"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\cli.py"" painel"; WorkingDir: "{app}\app"; Tasks: atalho

[Run]
Filename: "{cmd}"; Parameters: "/c winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando o Ollama (pode levar alguns minutos)..."; Flags: runhidden waituntilterminated; Tasks: ollama
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\cli.py"" painel"; WorkingDir: "{app}\app"; Description: "Abrir o Local AI Search agora"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; fecha o painel se estiver aberto (só o pythonw desta instalação)
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "fechar"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app\estado"
Type: filesandordirs; Name: "{app}\app\relatorios"
Type: filesandordirs; Name: "{app}\app\__pycache__"

[Code]
function OllamaInstalado(): Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'));
end;
