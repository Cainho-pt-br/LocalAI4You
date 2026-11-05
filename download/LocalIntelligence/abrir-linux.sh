#!/bin/bash
# Abre o painel do Local AI Search (macOS e Linux). Confere o Python e o Ollama e oferece instalar o que faltar.
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Falta o Python 3.10 ou mais recente."
  if [ "$(uname)" = "Darwin" ]; then echo "Instale em https://www.python.org/downloads/ (ou: brew install python) e abra de novo."; open "https://www.python.org/downloads/" 2>/dev/null
  else echo "Instale pelo gerenciador da sua distribuição (ex.: sudo apt install python3) e abra de novo."; fi
  read -r -p "Enter para sair..." _; exit 1
fi
if ! command -v ollama >/dev/null 2>&1 && [ ! -x /Applications/Ollama.app/Contents/Resources/ollama ]; then
  echo "O Ollama (gratuito) roda os modelos de IA no seu computador e ainda não está instalado."
  if [ "$(uname)" = "Darwin" ]; then
    echo "Baixe em https://ollama.com/download — o painel abre mesmo assim e mostra o passo a passo."; open "https://ollama.com/download" 2>/dev/null
  else
    read -r -p "Instalar agora com o instalador oficial (pede a senha de administrador)? [s/N] " r
    if [ "$r" = "s" ] || [ "$r" = "S" ]; then curl -fsSL https://ollama.com/install.sh | sh; fi
  fi
fi
echo "Abrindo o painel no navegador… (deixe esta janela aberta; Ctrl+C encerra)"
exec "$PY" cli.py painel
