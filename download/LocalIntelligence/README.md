# Local AI 4 You — app local

O app que roda no seu computador. O site mostra **estimativas**. Aqui você **mede de verdade**:

- **Descobrir**: o Radar lista os modelos que cabem no seu PC, do mais indicado ao menos indicado (o catálogo já vem no ZIP).
- **Medir**: roda benchmarks públicos nos modelos instalados, com margem de erro, na sua própria máquina.
- **Duelar**: compara dois modelos nos mesmos testes e diz se a diferença é real ou empate.
- **Decidir**: mostra o melhor modelo para cada uso e quais podem ser apagados sem perda.

Tudo roda no seu computador. Nenhum resultado é enviado para lugar nenhum.

## Começar

**Windows:** extraia o ZIP numa pasta (por exemplo, `Documentos\LocalAISearch`) e dê dois cliques em **`1_ABRIR_PAINEL.bat`**.
Se faltar o Python ou o Ollama, ele pergunta e instala sozinho (pelo `winget`, que já vem no Windows 10 e 11). Depois o painel abre no navegador.

**macOS:** dê dois cliques em **`abrir-mac.command`** (na primeira vez, se o macOS bloquear: botão direito → Abrir).
**Linux:** rode `./abrir-linux.sh` no terminal.

No painel, o quadro **Primeiros passos** guia o resto: ligar o Ollama, instalar o primeiro modelo pelo Radar e fazer o primeiro duelo.

O que é usado (tudo gratuito): **Python 3.10+** e **Ollama** ([ollama.com](https://ollama.com/download)). Não precisa instalar nada com `pip`.

`2_MEDIR_MODELOS.bat` mede os modelos instalados; `3_PROCURAR_MODELOS_NOVOS.bat` atualiza o catálogo e grava um relatório do que saiu de novo (não baixa nada).

Pelo terminal (qualquer sistema): `python3 cli.py painel`. Outros comandos: `python3 cli.py --help` (por exemplo, `bench`, `testar`, `radar`, `decidir`).

## Se algo der errado

- **“Python não encontrado”** (Windows sem `winget`): instale pelo [python.org](https://www.python.org/downloads/) marcando “Add Python to PATH” e abra o `.bat` de novo.
- **O Windows avisou “O Windows protegeu o computador”**: clique em *Mais informações* → *Executar assim mesmo*. Os arquivos `.bat` são texto puro: dá para abrir no Bloco de Notas e conferir o que fazem.
- **“Ollama desligado”**: clique em *Ligar o Ollama* no quadro Primeiros passos (ou abra o aplicativo do Ollama).
- **O modelo está lento**: ele provavelmente não cabe todo na placa de vídeo. Escolha um menor no Radar.
- **Relatar um problema**: [github.com/Cainho-pt-br/LocalAISearch/issues](https://github.com/Cainho-pt-br/LocalAISearch/issues)

## Recursos avançados

Comandos para controlar outras máquinas pela rede (`token`, `painel-remoto`, `maquinas`) e a aba **Parque** existem para quem tem vários computadores. Eles ficam escondidos até você registrar uma segunda máquina.

## Apoiar o projeto

O Local AI 4 You é gratuito e de código aberto. Se ele te ajudou, dê uma estrela no [GitHub](https://github.com/Cainho-pt-br/LocalAISearch), conte o que achou ou mostre para quem está começando. No painel, o link **♥ Apoiar o projeto** fica no rodapé da barra lateral.
