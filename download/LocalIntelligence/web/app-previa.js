'use strict';
/* No site, as abas que só funcionam no app baixado mostram uma PRÉVIA do recurso: o que ele responde, um exemplo
   ilustrativo (marcado como tal, com nomes genéricos) e como começar. No app local estas funções não são usadas. */

const exemploMarcado = (...conteudo) => h('div', { class: 'previa-exemplo' }, h('span', { class: 'previa-selo' }, 'Exemplo ilustrativo'), ...conteudo);
const medalha = n => h('span', { class: 'medalha m' + n }, n);
const barraNota = (nota, ic, cor) => h('span', { class: 'previa-barra' }, h('i', { class: 'ic', style: `left:${nota - ic}%;width:${2 * ic}%` }), h('b', { style: `left:calc(${nota}% - 1px);background:${cor || 'var(--ink)'}` }));

const PREVIAS = {
  decidir: {
    kicker: 'NO APP BAIXADO · DECIDIR',
    titulo: 'Qual modelo usar para cada coisa, com nota medida no seu PC',
    sub: 'O app junta os modelos instalados, as notas medidas e o catálogo do dia, e responde três perguntas: qual é o melhor para cada uso, o que vale testar e o que dá para apagar sem perder nada.',
    exemplo: () => exemploMarcado(
      h('div', { class: 'previa-linhas' },
        [['💬', 'Conversa', 'Modelo A 12B', 82, 4], ['💻', 'Código', 'Modelo B 9B', 77, 5], ['👁', 'Imagens', 'Modelo A 12B', 71, 6], ['⚡', 'Rápido', 'Modelo C 4B', 68, 5]].map(([ic, uso, nome, nota, ic2]) =>
          h('div', { class: 'previa-linha' }, h('span', { class: 'previa-uso' }, ic + ' ' + uso), h('b', {}, nome), barraNota(nota, ic2), h('span', { class: 'previa-nota' }, `${nota} ±${ic2}`), chip('MEDIDO', 'medido')))),
      h('div', { class: 'previa-aviso' }, '🧹 ', h('b', {}, 'Pode apagar o Modelo D 14B: '), 'o Modelo B 9B empata nas mesmas tarefas, ocupa 4 GB a menos e é 1,6× mais rápido.')),
    destaques: [
      ['📏', 'Nota de verdade', 'Benchmarks públicos rodando no seu hardware, com margem de erro. Nada de “parece melhor”.'],
      ['⚖', 'Empate é resposta', 'Se a diferença não passa da margem, o app diz “empate técnico” e você não troca por impulso.'],
      ['🧹', 'Espaço de volta', 'Mostra quem foi superado por um modelo menor e mais rápido, e apaga guardando o histórico.'],
    ],
  },
  modelos: {
    kicker: 'NO APP BAIXADO · MEUS MODELOS',
    titulo: 'Todos os seus modelos num placar',
    sub: 'Cada modelo instalado com nota por função, velocidade medida, memória e contexto que cabe 100% na placa. Ordene pelo que importa para você.',
    exemplo: () => exemploMarcado(
      h('div', { class: 'previa-linhas' },
        [[1, 'Modelo A 12B', 81, 3, '48 t/s', '8,0 GB'], [2, 'Modelo B 9B', 79, 4, '58 t/s', '6,6 GB'], [3, 'Modelo E 27B', 78, 5, '21 t/s', '17 GB'], [4, 'Modelo C 4B', 66, 5, '96 t/s', '3,3 GB']].map(([pos, nome, nota, ic, tps, gb]) =>
          h('div', { class: 'previa-linha' }, pos <= 3 ? medalha(pos) : h('span', { class: 'previa-pos' }, '#' + pos), h('b', {}, nome), barraNota(nota, ic, pos === 1 ? '#f59e0b' : null), h('span', { class: 'previa-nota' }, nota), h('span', { class: 'sub' }, tps + ' · ' + gb)))),
      h('div', { class: 'previa-aviso' }, '📉 Barras que se sobrepõem são empate técnico: os três primeiros acima estão praticamente empatados, e o mais rápido ganha no dia a dia.')),
    destaques: [
      ['🏅', 'Placar por função', 'Conversa, código, agentes, extração, raciocínio, imagens e documentos longos, cada um com o seu líder.'],
      ['±', 'Margem visível', 'A barra mostra a incerteza de cada nota. Com poucos itens, 78 e 81 podem ser o mesmo resultado.'],
      ['🗂', 'Histórico guardado', 'Modelos aposentados guardam as notas: dá para comparar com o que vier depois.'],
    ],
  },
  medir: {
    kicker: 'NO APP BAIXADO · MEDIR E DUELOS',
    titulo: 'Duelo: dois modelos, as mesmas perguntas, um vencedor (ou empate)',
    sub: 'Na dúvida entre dois candidatos do Radar, o duelo mede os dois no seu computador, nos mesmos itens de testes públicos, e mostra onde cada um vence.',
    exemplo: () => exemploMarcado(
      h('div', { class: 'duelo-topo' }, h('span', { class: 'duelo-a' }, 'Modelo A 12B'), h('b', { class: 'duelo-x' }, '×'), h('span', { class: 'duelo-b' }, 'Modelo B 9B')),
      h('div', { class: 'previa-linhas' },
        [['Conversa em português', 74, 71], ['Código (HumanEval)', 61, 68], ['Seguir regras (IFEval)', 80, 79], ['Matemática (GSM8K)', 72, 64]].map(([teste, a, b]) =>
          h('div', { class: 'duelo-linha' }, h('span', { class: 'sub' }, teste),
            h('span', { class: 'duelo-barras' }, h('i', { class: 'da', style: `width:${a}%` }), h('i', { class: 'db', style: `width:${b}%` })),
            h('span', { class: 'previa-nota' }, `${a} × ${b}`),
            Math.abs(a - b) <= 3 ? chip('empate', 'neutro') : chip((a > b ? 'A' : 'B') + ' vence', a > b ? 'ok' : 'estimado')))),
      h('div', { class: 'previa-aviso' }, '🏁 Veredito: A para conversa e matemática, B para código. Em “seguir regras”, empate técnico.')),
    destaques: [
      ['🧪', 'Testes públicos', 'MMLU-Pro, MMLU em português, CAPITU, IFEval, BFCL, HumanEval, GSM8K e visão, com os mesmos itens para todos.'],
      ['⏯', 'Retoma de onde parou', 'Fecha o app e continua depois. Em máquinas modestas, ele sugere um nível mais curto.'],
      ['🎯', 'Mede o que importa', 'Velocidade real e quanto contexto cabe 100% na placa, além da nota.'],
    ],
    passos: true,
  },
  offline: {
    kicker: 'NO APP BAIXADO · OFFLINE',
    titulo: 'IA que continua funcionando sem internet',
    sub: 'Modelos locais rodam sem rede, mas só se você se preparar antes. O app confere o que falta e monta um kit de cópia para outro disco.',
    exemplo: () => exemploMarcado(
      h('ul', { class: 'previa-check' },
        h('li', { class: 'ok' }, 'Ollama instalado e abrindo sem internet'),
        h('li', { class: 'ok' }, '3 modelos baixados por completo (verificação SHA-256)'),
        h('li', { class: 'ok' }, 'Calculadora salva como arquivo HTML único'),
        h('li', { class: 'pendente' }, 'Segunda cópia dos modelos em outro disco'),
        h('li', { class: 'ok' }, 'Teste com a rede desligada: passou'))),
    destaques: [
      ['⬇', 'Baixe antes de precisar', 'Escolha no Radar o que cabe e deixe o download terminar enquanto há internet.'],
      ['💾', 'Segunda cópia', 'Exporte um kit com os modelos e as instruções de restauração para um HD externo.'],
      ['📴', 'Teste sem rede', 'Desligue a internet e confirme: runtime, modelos e interface abrindo localmente.'],
    ],
  },
};

function paginaPrevia(id, raiz) {
  const P = PREVIAS[id];
  raiz.replaceChildren(
    h('div', { class: 'pagina-topo previa-topo' }, h('span', { class: 'guia-kicker' }, P.kicker), h('h1', {}, P.titulo), h('p', { class: 'sub' }, P.sub)),
    h('div', { class: 'previa-grade' }, P.exemplo(),
      h('div', { class: 'previa-destaques' }, P.destaques.map(([ic, t, d], i) => h('article', { class: 'previa-destaque d' + (i + 1) }, h('span', { class: 'previa-ic' }, ic), h('div', {}, h('h3', {}, t), h('p', {}, d)))))),
    P.passos ? h('div', { class: 'previa-passos' },
      h('h2', {}, 'Como começar'),
      h('ol', { class: 'passos-linha' },
        h('li', {}, h('b', {}, 'Baixe e abra o instalador'), h('span', { class: 'sub' }, '. Extraia o ZIP e dê dois cliques em “Instalar Local AI 4 You” (Windows) ou “Abrir Local AI 4 You” (Mac e Linux). No Windows já vem tudo, até o Python.')),
        h('li', {}, h('b', {}, 'Siga os primeiros passos'), h('span', { class: 'sub' }, ': o app abre no navegador e mostra o que falta, como instalar o Ollama (gratuito).')),
        h('li', {}, h('b', {}, 'Instale dois candidatos pelo Radar'), h('span', { class: 'sub' }, ' e clique em Duelo. O resultado fica salvo no seu PC.')))) : null,
    h('div', { class: 'previa-cta' },
      h('div', {}, h('b', {}, 'Grátis, código aberto, roda tudo no seu computador.'), h('div', { class: 'sub' }, 'Windows, macOS e Linux · nada é enviado sem você pedir.')),
      h('div', { class: 'linha', style: 'gap:8px;flex-wrap:wrap' },
        h('a', { class: 'btn primario', href: LINK_DOWNLOAD, onclick: () => { if (typeof registrarEvento === 'function') registrarEvento('download', { origem: 'previa-' + id }); } }, 'Baixar o app local'),
        h('a', { class: 'btn', href: LINK_REPO, target: '_blank', rel: 'noopener' }, 'Ver no GitHub ↗'))));
}
