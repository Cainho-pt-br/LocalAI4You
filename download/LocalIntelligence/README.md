# Local Intelligence — versão local

Painel para executar no próprio computador.

## O que instalar

- **Python 3.10 ou mais recente** — selecione “Add Python to PATH” no instalador do Windows.
- **Ollama** — instale pelo [site oficial](https://ollama.com/download) e mantenha-o aberto.
- **Um modelo no Ollama** — por exemplo, no terminal: `ollama run qwen3:8b`. O tamanho adequado depende da RAM/VRAM; consulte a calculadora do site antes de baixar.

Não precisa instalar pacotes Python com pip. O CAPITU usa `nltk` se estiver disponível; sem ele, essa suíte é pulada com aviso. Node.js é opcional e só é usado para conferir paridade da calculadora nos testes.

## Iniciar no Windows

1. Extraia esta pasta.
2. Execute `1_ABRIR_PAINEL.bat`; o painel abre em `http://127.0.0.1:8765`.
3. Execute `2_MEDIR_MODELOS.bat` para iniciar benchmarks locais.

O painel detecta hardware localmente; benchmarks e dados não são enviados ao site. Linux/macOS podem iniciar com `python cli.py painel`; confira a compatibilidade do Ollama e os scripts de instalação antes de usar os atalhos `.bat`.
