# LocalAISearch

Site estático com a interface e os efeitos visuais do painel Local Intelligence, além da calculadora pública de hardware. O catálogo no site é estimado e fica congelado na data da varredura indicada na tela.

## Publicar o site

No Vercel, importe este repositório e configure `site` como **Root Directory**. Não há build nem variáveis de ambiente; o site serve os arquivos estáticos dessa pasta. A pasta `download/LocalIntelligence` contém o aplicativo para executar no computador.

## Catálogo atualizado

O GitHub Actions executa o radar diariamente às 08:17 UTC e também pode ser iniciado manualmente em **Actions → Atualizar catálogo público → Run workflow**. Ele consulta as fontes em sequência conforme o radar do projeto, atualiza `site/dados.js` somente quando a varredura completa é válida e preserva o último catálogo bom em caso de falha. O fluxo não usa token do Hugging Face.

Para republicar automaticamente no Vercel quando o catálogo mudar, crie um Deploy Hook de produção no projeto Vercel e salve a URL como secret do repositório GitHub com o nome `VERCEL_DEPLOY_HOOK` (**Settings → Secrets and variables → Actions**). Sem esse secret, o catálogo é atualizado no GitHub, mas será necessário iniciar um deploy manual do Vercel.

## Rodar localmente

O painel completo precisa de Python 3.10+ e Ollama instalado. No Windows, extraia `download/LocalIntelligence`, instale/abra o Ollama, baixe um modelo e execute `1_ABRIR_PAINEL.bat`. Use `2_MEDIR_MODELOS.bat` para iniciar benchmarks. A detecção de hardware e as medições acontecem no PC; não são enviadas ao site.

## Limites do site

O site oferece a calculadora com dados públicos do catálogo. Benchmarks, leitura dos modelos instalados, radar dinâmico e ações do Ollama exigem o aplicativo local. Velocidades de CPU são estimadas.

## Dados e licença

O código deste repositório é distribuído sob Apache-2.0 (`LICENSE`). O catálogo de hardware e os metadados dos modelos vêm das fontes originais indicadas no aplicativo. Os modelos e conjuntos de dados de terceiros mantêm suas próprias licenças; a licença do código não altera esses termos.
