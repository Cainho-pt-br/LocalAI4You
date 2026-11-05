# Local AI Search

Descubra qual IA local roda bem no **seu** computador e use-a do jeito certo.

- **No site**: informe seu hardware (ou confirme o palpite do navegador) e veja todos os modelos que cabem, do mais indicado ao menos indicado, com o comando para baixar. Tudo é estimado a partir do tamanho real dos arquivos e da memória da sua máquina.
- **No app baixado**: meça os modelos instalados com benchmarks públicos, faça duelos entre dois modelos e descubra qual manter. Roda no seu PC; nada é enviado.

## Estrutura

| Pasta | O que é |
|---|---|
| `download/LocalIntelligence/` | O app local (Python + Ollama). **Fonte única da interface** em `web/`. |
| `site/` | O site estático publicado no Vercel: `index.html` é a página inicial (`landing.css`/`landing.js`, só do site) e `app.html` é o app. `site/web/` é uma cópia de `download/LocalIntelligence/web/` + `public-mode.js`. |
| `site/dados.js` | Catálogo público, atualizado todo dia pelo GitHub Actions. |
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

## Publicar

- **Site**: no Vercel, importe este repositório com `site` como **Root Directory**. Não há build.
- **Catálogo**: o workflow *Atualizar catálogo público* roda às 08:17 UTC (ou manualmente em **Actions**). Ele atualiza `site/dados.js` e o catálogo que vai no ZIP do app (`download/LocalIntelligence/data/radar-inicial.json.gz`). Se a varredura falhar, o último catálogo bom é mantido. Para republicar no Vercel automaticamente, salve um Deploy Hook como secret `VERCEL_DEPLOY_HOOK`.
- **App**: o workflow *Publicar app local* gera `LocalAISearch.zip` (só o app, sem o site) e o publica no release `app-latest`. O botão “Baixar o app local” do site aponta para `releases/latest/download/LocalAISearch.zip`. Ele roda quando o app muda, depois de cada atualização do catálogo, ou manualmente.

## Métricas, e-mails e benchmarks da comunidade

O banco fica no Supabase (organização **Local AI Search**, projeto **LocalAISearch**). As tabelas estão no schema `privado`, fora da API: o site e o app só chamam três funções de gravação (`registrar_evento`, `registrar_lead`, `enviar_benchmark`). A chave em `web/coleta.js` é publicável e não lê nada. As migrações estão em `supabase/migrations/`.

- **Métricas (só no site)**: sem cookies e sem IP; respeitam *Do Not Track*/GPC; `localhost` e as prévias do Vercel (`…-projects.vercel.app`) não entram nas visões; a produção (`localaisearch-site.vercel.app`) entra. Use links com UTM nos conteúdos (`?utm_source=youtube&utm_campaign=video-rtx4060`).
- **E-mails**: só com consentimento explícito, guardado junto. Exporte em **Table Editor → privado.leads**.
- **Benchmarks**: no app, aba Medir → *Compartilhar resultados com a comunidade*; a pessoa vê o JSON antes de enviar.

Consultas prontas (SQL Editor): `select * from privado.v_diario;`, `v_origens` (de onde vêm e quem converte), `v_hardware` (placas mais configuradas), `v_modelos_copiados`, `v_abas`.

## Apoiar o projeto

O projeto é gratuito e de código aberto. Se ele te ajudou: deixe uma ⭐, [conte o que achou ou relate um problema](https://github.com/Cainho-pt-br/LocalAISearch/issues) e mostre para quem está começando com IA local.

Para ativar doações no site e no app, preencha `APOIO` em `download/LocalIntelligence/web/apoio.js` (chave Pix e/ou link do GitHub Sponsors, Ko-fi, Apoia.se…) e rode `python scripts/sincronizar-web.py`. O apoio aparece sempre, sem atrapalhar: um link no rodapé da barra lateral, um bloco discreto no fim do Radar e uma linha compacta depois de cada momento útil (copiar um comando, terminar uma medição). A linha some sozinha em segundos e o ✕ a esconde até a próxima visita. Nada é rastreado.

## Dados e licença

O código é distribuído sob Apache-2.0 (`LICENSE`). O catálogo de hardware e os metadados dos modelos vêm das fontes originais indicadas no app. Modelos e conjuntos de dados de terceiros (MMLU-Pro, IFEval, BFCL, HumanEval, GSM8K e outros em `download/LocalIntelligence/data/`) mantêm suas próprias licenças; a licença do código não altera esses termos.
