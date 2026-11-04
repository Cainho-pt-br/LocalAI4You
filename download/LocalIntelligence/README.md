# Local AI Search — app local

O app que roda no seu computador. O site mostra **estimativas**. Aqui você **mede de verdade**:

- **Descobrir**: o Radar lista os modelos que cabem no seu PC, do mais indicado ao menos indicado (o catálogo já vem no ZIP).
- **Medir**: roda benchmarks públicos nos modelos instalados, com margem de erro, na sua própria máquina.
- **Duelar**: compara dois modelos nos mesmos testes e diz se a diferença é real ou empate.
- **Decidir**: mostra o melhor modelo para cada uso e quais podem ser apagados sem perda.

Tudo roda no seu computador. Nenhum resultado é enviado para lugar nenhum.

## O que instalar (uma vez)

1. **Python 3.10 ou mais recente**: [python.org/downloads](https://www.python.org/downloads/). No Windows, marque **“Add Python to PATH”** no instalador.
2. **Ollama**: [ollama.com/download](https://ollama.com/download). Deixe-o aberto.

Não precisa instalar nada com `pip`.

## Começar (Windows)

1. Extraia o ZIP numa pasta (por exemplo, `Documentos\LocalAISearch`).
2. Dê dois cliques em **`1_ABRIR_PAINEL.bat`**. O painel abre no navegador em `http://127.0.0.1:8765`.
3. Na aba **Radar**, escolha um modelo e clique em **Instalar** (ou copie o comando `ollama pull`).
4. Com um modelo instalado, use **Medir** (ou `2_MEDIR_MODELOS.bat`) e depois **Decidir**.

`3_PROCURAR_MODELOS_NOVOS.bat` atualiza o catálogo e grava um relatório do que saiu de novo. Ele não baixa nada.

## Começar (macOS e Linux)

```bash
cd LocalAISearch
python3 cli.py painel
```

Outros comandos: `python3 cli.py --help` (por exemplo, `bench`, `testar`, `radar`, `decidir`).

## Se algo der errado

- **“Python não encontrado”**: reinstale o Python marcando “Add Python to PATH” e abra o `.bat` de novo.
- **“Ollama desligado”**: abra o aplicativo do Ollama e recarregue a página.
- **O modelo está lento**: ele provavelmente não cabe todo na placa de vídeo. Escolha um menor no Radar.
- **Relatar um problema**: [github.com/Cainho-pt-br/LocalAISearch/issues](https://github.com/Cainho-pt-br/LocalAISearch/issues)

## Recursos avançados

Comandos para controlar outras máquinas pela rede (`token`, `painel-remoto`, `maquinas`) e a aba **Parque** existem para quem tem vários computadores. Eles ficam escondidos até você registrar uma segunda máquina.

## Apoiar o projeto

O Local AI Search é gratuito e de código aberto. Se ele te ajudou, dê uma estrela no [GitHub](https://github.com/Cainho-pt-br/LocalAISearch), conte o que achou ou mostre para quem está começando. No painel, o link **♥ Apoiar o projeto** fica no rodapé da barra lateral.
