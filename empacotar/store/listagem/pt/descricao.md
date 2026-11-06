# Listagem da Microsoft Store — Local AI 4 You (pt-BR)

Copie cada bloco para o campo de mesmo nome em Partner Center → seu app → Envio → Listagens da Store → Português (Brasil).

## Descrição (até 10.000 caracteres)

Descubra qual inteligência artificial roda de verdade no seu computador — e use a melhor.

O Local AI 4 You olha para a sua placa de vídeo, a memória e o processador e mostra, em segundos, quais modelos de IA local cabem na sua máquina: do mais inteligente ao mais leve, com o comando pronto para baixar no Ollama. Nada de baixar 20 GB para descobrir que trava.

RADAR
Mais de 300 modelos do Ollama e do Hugging Face, atualizados todo dia, ordenados para o seu hardware. Os 5 melhores ganham pódio. Filtre por uso: conversa em português, código, agentes, extrair dados, raciocínio, imagens e documentos longos.

CALCULADORA
Quanto de memória cada modelo usa, quanto contexto cabe na placa e quão rápido ele responde. Simule uma placa nova e veja se o upgrade vale a pena antes de gastar.

DUELOS E MEDIÇÕES
Ficou em dúvida entre dois modelos? O duelo mede os dois no seu computador, com as mesmas perguntas de testes públicos (MMLU-Pro, IFEval, HumanEval, GSM8K e outros), mostra a margem de erro e diz quando é empate.

DECIDIR
Veja o melhor modelo instalado para cada uso e quais dá para apagar sem perder nada.

PRIMEIROS PASSOS
Um guia de 3 passos: ligar o Ollama, instalar o primeiro modelo e fazer o primeiro duelo.

PRIVADO
Tudo roda no seu computador. Sem conta, sem cadastro. O app não envia nada sem você pedir.

Gratuito e de código aberto. Disponível em português, inglês e espanhol.

Requer o Ollama (gratuito, ollama.com) para baixar e rodar os modelos. Sem ele, o Radar e a Calculadora funcionam normalmente.

## Descrição curta (até 1.000 caracteres)

Descubra quais modelos de IA local rodam bem no seu PC, do mais inteligente ao mais leve, com o comando pronto para o Ollama. Meça e compare modelos no seu próprio hardware. Gratuito, privado e de código aberto.

## Novidades desta versão

Primeira versão na Microsoft Store.

## Recursos do produto (até 20, 200 caracteres cada)

- Ranking de mais de 300 modelos de IA local para o seu hardware
- Pódio com os 5 melhores modelos para cada uso
- Comando do Ollama pronto, na versão certa para a sua memória
- Calculadora de memória, contexto e velocidade
- Simulação de upgrade de placa de vídeo
- Duelo entre dois modelos com testes públicos
- Notas medidas com margem de erro
- Guia de primeiros passos
- Funciona sem conta e sem cadastro
- Gratuito e de código aberto

## Palavras-chave (até 7)

IA local, Ollama, LLM, modelos de IA, benchmark, placa de vídeo, inteligência artificial

## Capturas de tela (1920×1080, nesta ordem) e legendas

1. `pt/1-inicio.png` — Descubra em segundos qual IA roda bem no seu computador
2. `pt/2-radar.png` — Radar: todos os modelos que cabem, do melhor ao mais leve
3. `pt/3-calculadora.png` — Calculadora: memória, contexto e velocidade antes de baixar
4. `pt/4-duelo.png` — Duelo: dois modelos, as mesmas perguntas, um vencedor (ou empate)

## Outros campos

- Categoria: Ferramentas de desenvolvedor (subcategoria: Outras ferramentas de desenvolvedor) — alternativa: Produtividade
- Site: https://localaisearch-site.vercel.app
- Contato de suporte: https://github.com/Cainho-pt-br/LocalAISearch/issues
- Política de privacidade: https://localaisearch-site.vercel.app/privacidade.html
- Direitos autorais: © 2026 Cainho Labs. Código sob licença Apache-2.0.
- Requisitos adicionais: Ollama (gratuito) para baixar e rodar modelos. Recomendado: 16 GB de RAM ou placa de vídeo com 8 GB ou mais.

## Justificativa da capacidade runFullTrust

O app é um painel local: inicia o Ollama, roda um servidor só em 127.0.0.1 para a interface e abre o navegador padrão. Precisa de confiança total para executar esses processos locais e medir o hardware (placa de vídeo e memória).

## Notas para a certificação

O app abre um painel no navegador padrão (http://127.0.0.1:8765). Para medir modelos é necessário o Ollama (gratuito, ollama.com); sem ele, o Radar e a Calculadora funcionam normalmente, e o quadro "Primeiros passos" mostra como instalar. Para fechar o app, use "Fechar o app" na barra lateral.
