# Local AI 4 You

Descubra qual IA local roda bem no **seu** computador e use-a do jeito certo.

- **No site**: informe seu hardware (ou confirme o palpite do navegador) e veja todos os modelos que cabem, do mais indicado ao menos indicado, com o comando para baixar. Tudo é estimado a partir do tamanho real dos arquivos e da memória da sua máquina.
- **No app baixado**: meça os modelos instalados com benchmarks públicos, faça duelos entre dois modelos e descubra qual manter. Roda no seu PC; nada é enviado.

## Estrutura

| Pasta | O que é |
|---|---|
| `download/LocalIntelligence/` | O app local (Python + Ollama). **Fonte única da interface** em `web/`. |
| `site/` | O site estático publicado no Vercel: `index.html` é a página inicial (`landing.css`/`landing.js`, só do site) e `app.html` é o app. `site/web/` é uma cópia de `download/LocalIntelligence/web/` + `public-mode.js`. |
| `site/dados.js` | Catálogo público, atualizado todo dia pelo GitHub Actions. |
| `site/placa/`, `site/en/gpu/`, `site/es/gpu/` | Páginas estáticas "o que roda em cada placa", **geradas** por `scripts/gerar-paginas.js` (não edite à mão). |
| `scripts/` | Atualização do catálogo e sincronização da interface. |

## Desenvolver

Edite a interface **só** em `download/LocalIntelligence/web/` e sincronize com o site:

```bash
python scripts/sincronizar-web.py
```

O comportamento que muda entre o site e o app fica no próprio código, atrás de `window.LI_PUBLIC_MODE`. O CI (`Verificar`) falha se `site/web` divergir da fonte.

Testes do app (incluem a paridade dos cálculos JavaScript × Python; o Node.js é opcional):

```bash
cd download/LocalIntelligence && python -m unittest discover -s tests
```

## Dados entre versões

As notas medidas, vereditos e modelos aposentados ficam em `estado/`, fora do pacote, então atualizar não apaga nada. O ZIP guarda ao lado do app (`…\Programs\Local AI 4 You\app\estado`) e a Microsoft Store numa pasta própria (`%LOCALAPPDATA%\LocalAISearch\estado`). Ao abrir, o app traz sozinho os dados de uma instalação anterior (uma vez, sem apagar nem sobrescrever); `python cli.py importar-dados [pasta-estado]` faz o mesmo à mão.

## Uma versão por vez

O painel usa a porta 8765. Ao abrir, ele olha quem já está nela (`li/instancia.py`): a mesma versão ou uma mais nova só ganham a janela; uma versão antiga é fechada (pelo `/api/encerrar` ou, no Windows, encerrando o processo do painel) e a tela avisa. Se a porta não liberar, o painel usa a próxima livre e avisa. O app também mostra quando há outra instalação do ZIP no computador e oferece removê-la, guardando antes uma cópia dos dados dela.

## Janela do app

O painel abre numa janela própria (Edge ou Chrome em modo aplicativo, sem abas nem barra de endereço) e encerra ao fechá-la, a menos que haja uma tarefa pesada rodando. Sem Edge nem Chrome, abre no navegador padrão. `LI_JANELA=0` ou `"janela_app": false` em `estado/config.json` desliga.

## Links com o hardware e páginas por placa

- `app.html?gpu=rtx-4060` (ou `?chip=m2&ram=16`, `?ram=16` para PC sem placa) abre o Radar já nesse computador. O botão **Compartilhar** do Radar gera esse link.
- `node scripts/gerar-paginas.js` refaz as páginas por placa e o `sitemap.xml` com o mesmo motor do Radar (`web/calc.js`). Roda sozinho todo dia, junto com o catálogo. O molde está no próprio script; o visual, em `site/placa.css`.
- Canais do projeto (YouTube, Discord…): preencha `CANAIS` em `download/LocalIntelligence/web/base.js`; os vazios não aparecem.

## Publicar

- **Site**: no Vercel, importe este repositório com `site` como **Root Directory**. Não há build.
- **Catálogo**: o workflow *Atualizar catálogo público* roda às 08:17 UTC (ou manualmente em **Actions**). Ele atualiza `site/dados.js` e o catálogo que vai no ZIP do app (`download/LocalIntelligence/data/radar-inicial.json.gz`). Se a varredura falhar, o último catálogo bom é mantido. Para republicar no Vercel automaticamente, salve um Deploy Hook como secret `VERCEL_DEPLOY_HOOK`.
- **App**: o workflow *Publicar app local* monta o download com `empacotar/montar.py` e publica no release `app-latest`: `LocalAI4You-Windows.zip` ("Instalar Local AI 4 You" + `app/` com o Python embutido oficial; os atalhos chamam o `pythonw.exe` assinado pela Python Software Foundation, então o SmartScreen não bloqueia e não abre janela preta) e `LocalAI4You.zip` (macOS/Linux: atalho de abrir, `LEIA-ME.txt` e `app/`). O site oferece o pacote certo para cada sistema.
- **Microsoft Store**: o workflow manual *Pacote da Microsoft Store* gera `LocalAI4You.msix` (Python embutido + app, manifesto em `empacotar/store/`) para enviar no Partner Center. Precisa das variáveis do repositório `STORE_IDENTITY_NAME`, `STORE_PUBLISHER` e `STORE_PUBLISHER_NAME`. Instalado pela Store, o app guarda os dados em `%LOCALAPPDATA%\LocalAISearch` (`LI_DADOS` também muda o local). Política de privacidade: `site/privacidade.html`. Prints da listagem (1920×1080, pt/en/es): com o painel rodando (`python cli.py painel --sem-navegador`), `node scripts/prints-store.js` refaz as telas 1 (Radar) e 4 (Trocar a placa?) a partir do app de verdade; as telas 2, 3 e 5 precisam de modelos medidos e ainda são feitas à mão. Ele roda quando o app muda, depois de cada atualização do catálogo, ou manualmente.

## Métricas e benchmarks da comunidade

O site e o app nunca falam direto com o banco: chamam `/api/coleta` (função do Vercel em `site/api/coleta.js`), que guarda as credenciais nas variáveis de ambiente e só repassa funções de gravação. Nenhuma chave fica no código. As migrações estão em `supabase/migrations/`.

- **Métricas (só no site)**: sem cookies e sem IP; respeitam *Do Not Track*/GPC; `localhost` e as prévias do Vercel não contam.
- **Benchmarks**: no app, aba Medir → *Compartilhar resultados com a comunidade*; a pessoa vê o JSON antes de enviar.

Detalhes do que é coletado: `site/privacidade.html`.

## Idiomas

Site e app em português, inglês e espanhol. O código continua escrito em português; `web/i18n.js` troca os textos da tela usando os dicionários de `web/i18n-dados.js` (frase exata, frase com números como `{n}` e regras para textos montados em partes). O idioma vem do navegador/sistema e pode ser trocado no seletor 🌐. Texto novo na interface: acrescente a linha `[português, inglês, espanhol]` em `i18n-dados.js`.

## Apoiar o projeto

O projeto é gratuito e de código aberto. Se ele te ajudou: deixe uma ⭐, [conte o que achou ou relate um problema](https://github.com/Cainho-pt-br/LocalAI4You/issues) e mostre para quem está começando com IA local.

Doações: [GitHub Sponsors](https://github.com/sponsors/Cainho-pt-br) e Pix.

Para ativar ou mudar doações no site e no app, preencha `APOIO` em `download/LocalIntelligence/web/apoio.js` (chave Pix e/ou link do GitHub Sponsors, Ko-fi, Apoia.se…) e rode `python scripts/sincronizar-web.py`. O apoio aparece sempre, sem atrapalhar: um link no rodapé da barra lateral, um bloco discreto no fim do Radar e uma linha compacta depois de cada momento útil (copiar um comando, terminar uma medição). A linha some sozinha em segundos e o ✕ a esconde até a próxima visita. Nada é rastreado.

## Dados e licença

O código é distribuído sob Apache-2.0 (`LICENSE`). O catálogo de hardware e os metadados dos modelos vêm das fontes originais indicadas no app. Modelos e conjuntos de dados de terceiros (MMLU-Pro, IFEval, BFCL, HumanEval, GSM8K e outros em `download/LocalIntelligence/data/`) mantêm suas próprias licenças; a licença do código não altera esses termos.
