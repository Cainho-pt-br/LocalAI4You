'use strict';
/* Página "Medir": diz o que vale rodar AGORA (com motivo e minutos), oferece o duelo entre dois modelos (A × B) e o formulário completo. */

const NIVEL_NOME = { minimo: 'Mínimo', rapido: 'Rápido', padrao: 'Padrão', profundo: 'Profundo' };
const fmtMin = m => m >= 90 ? `~${fmtN(m / 60, 1)} h` : `~${m} min`;

async function pMedir() {
  const raiz = $('#p-medir');
  if (window.LI_PUBLIC_MODE) { const link=LINK_DOWNLOAD; raiz.replaceChildren(h('div',{class:'pagina-topo'},h('h1',{},'Medir modelos no seu computador'),h('p',{class:'sub'},'O site não inventa resultados nem mede a máquina de outra pessoa. Benchmarks só fazem sentido quando executados junto do modelo e do hardware que estão sendo avaliados.')),h('div',{class:'guia-grid'},h('article',{class:'guia-card'},h('span',{class:'guia-num'},'1'),h('h2',{},'Instale o Ollama'),h('p',{},'O aplicativo local usa o Ollama para carregar e conversar com os modelos.'),h('a',{href:'https://ollama.com/download',target:'_blank',rel:'noopener'},'Baixar Ollama ↗')),h('article',{class:'guia-card'},h('span',{class:'guia-num'},'2'),h('h2',{},'Baixe o painel'),h('p',{},'Extraia o ZIP, abra a pasta e siga o README. No Windows, inicie pelo arquivo 1_ABRIR_PAINEL.bat.'),h('a',{class:'btn primario',href:link},'Baixar Local AI Search')),h('article',{class:'guia-card'},h('span',{class:'guia-num'},'3'),h('h2',{},'Meça e compare'),h('p',{},'Use Medir para rodar o protocolo local. O app guarda resultados no seu PC e compara modelos nos mesmos testes.'))),h('div',{class:'guia-callout'},h('b',{},'O que significa uma medição?'),h('p',{},'MEDIDO significa que o modelo rodou no seu PC. ESTIMADO significa cálculo de encaixe/velocidade. PRIORIDADE só indica o que vale testar; não é uma nota.'))); return; }
  if (!S.mesa) return;
  const topo = h('div', { class: 'pagina-topo' }, h('h1', {}, 'Medir e testar'), h('p', { class: 'sub' }, 'Os testes que transformam “parece bom” em nota com margem de erro. Aqui você pode rodar um Duelo Direto (A × B), executar o que o painel recomenda agora ou escolher os testes manualmente.'));
  raiz.replaceChildren(topo, h('div', { class: 'sub' }, 'Calculando o que vale medir…'));
  let pl;
  try { pl = await api('/api/lab/plano'); } catch (e) { raiz.append(h('div', { class: 'aviso-caixa' }, e.message)); return; }
  if (S.aba !== 'medir') return;
  let cfg = {};
  try { cfg = await api('/api/config'); } catch (e) { /* segue sem */ }
  const papeisNota = (S.mesa.papeis || []).filter(p => !p.sem_nota);
  raiz.replaceChildren(topo,
    titulo('O que vale rodar agora', 'Passos prioritários para sua máquina.'),
    pl.passos.length ? h('div', { class: 'empilha' }, pl.passos.map(cartaoPasso)) : h('div', { class: 'ok-caixa' }, h('b', {}, 'Tudo em dia.'), ' Todos os modelos instalados têm nota no nível Padrão e sonda de contexto.'),
    titulo('Seus modelos', 'Status das medições de cada modelo.'),
    tabelaModelos(pl),
    h('div', { id: 'cartao-visao' }),
    h('details', { class: 'painel-colapsavel', style: 'margin-top:24px' },
      h('summary', {},
        h('h2', {}, 'Medição personalizada (Avançado)'),
        h('span', { class: 'colapsavel-dica' }, 'Escolher modelos e testes manualmente')),
      h('div', { class: 'painel-conteudo' }, formularioMedir(pl))),
    h('details', { class: 'painel-colapsavel' },
      h('summary', {},
        h('h2', {}, 'O que cada teste mede (Catálogo de Suítes)'),
        h('span', { class: 'colapsavel-dica' }, 'Ver critérios e itens')),
      h('div', { class: 'painel-conteudo' }, tabelaTestes(pl))),
    titulo('Tarefas em andamento'), h('div', { id: 'lab-jobs' }),
    titulo('Relatório e ajustes do sistema'),
    h('div', { class: 'grade g2' },
      h('div', { class: 'cartao empilha', style: 'gap:10px' },
        h('h3', {}, '📄 Relatório Completo'),
        h('p', { class: 'sub', style: 'margin:0;line-height:1.5' },
          'Compila os seus modelos, notas medidas com intervalo de confiança, desafiantes do radar, máquinas do parque e prontidão offline em um documento Markdown formatado.'),
        h('div', { class: 'dlg-acoes', style: 'justify-content:flex-start;margin-top:auto' },
          h('button', { class: 'btn primario', onclick: abrirRelatorioModal }, '👁️ Visualizar e exportar relatório'))),
      cartaoConfig(cfg)));
  desenharJobsMedir();
  desenharVisao(pl);
}

async function abrirRelatorioModal() {
  try {
    toast('Gerando relatório completo…');
    const [r, rSalvo] = await Promise.all([
      api('/api/relatorio'),
      api('/api/relatorio/gerar', {})
    ]);
    const md = r.markdown || '';

    const pre = h('pre', {
      class: 'bloco',
      style: 'max-height:55vh;overflow:auto;padding:14px;font-size:.82rem;white-space:pre-wrap;background:var(--surface-2);border-radius:10px;line-height:1.5'
    }, md);

    const btnCopiar = h('button', {
      class: 'btn primario',
      onclick: () => { copiar(md); toast('Markdown copiado para a área de transferência!'); }
    }, '📋 Copiar Markdown');

    const btnBaixar = h('button', {
      class: 'btn',
      onclick: () => {
        const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `relatorio-modelos-${new Date().toISOString().slice(0, 10)}.md`;
        a.click();
        URL.revokeObjectURL(url);
        toast('Download iniciado!');
      }
    }, '💾 Baixar arquivo (.md)');

    abrirDialogo(h('div', { class: 'dlg-in', style: 'max-width:880px' },
      h('div', { class: 'linha' },
        h('div', {},
          h('h2', {}, 'Relatório Executivo de Modelos Locais'),
          h('div', { class: 'sub', style: 'margin-top:2px' }, `Arquivo salvo em: ${rSalvo.arquivo}`)),
        h('button', { class: 'btn mini fantasma', onclick: fecharDialogo }, '✕ Fechar')),
      pre,
      h('div', { class: 'dlg-acoes' },
        btnBaixar,
        btnCopiar,
        h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
  } catch (e) {
    toast('Erro ao gerar relatório: ' + e.message, 8000);
  }
}

function cartaoPasso(p) {
  const rodar = async () => {
    try {
      if (p.tipo === 'sonda') { await api('/api/sonda', { modelos: p.modelos, ate_ctx: 1048576 }); toast('Sonda iniciada: acompanhe na barra de baixo.'); await carregarJobs(); }
      else await iniciarBench(p.modelos, p.nivel, p.modo, p.suites);
    } catch (e) { toast(e.message, 8000); }
  };
  const chipsModelos = p.modelos.map(mid => {
    const nomeL = nomeAmigavelModelo(mid);
    const qL = tagQuantModelo(mid);
    return chip(`${nomeL}${qL ? ' (' + qL + ')' : ''}`, 'neutro', mid);
  });
  return h('div', { class: 'cartao' + (p.recomendado ? ' destaque' : ''), style: 'border-left:4px solid ' + (p.recomendado ? 'var(--ok, #10b981)' : 'var(--line-strong)') },
    h('div', { class: 'linha topo' },
      h('div', { class: 'grow' },
        h('div', { class: 'linha', style: 'justify-content:flex-start;gap:8px;margin-bottom:4px' },
          h('h3', { style: 'font-size:1.05rem;margin:0' }, p.titulo),
          p.recomendado ? chip('Recomendado', 'ok') : null,
          p.minutos ? chip('⏱ ' + fmtMin(p.minutos), 'neutro') : null),
        h('p', { class: 'sub', style: 'margin:4px 0 10px;line-height:1.45' }, p.porque),
        h('div', { class: 'linha', style: 'justify-content:flex-start;gap:6px;align-items:center' },
          h('span', { class: 'sub', style: 'font-weight:600' }, 'Modelos:'),
          h('div', { class: 'chips' }, ...chipsModelos),
          p.nivel ? chip('Nível ' + NIVEL_NOME[p.nivel], 'prioridade') : null,
          p.modo === 'think' ? chip('Raciocínio ligado', 'warn') : null)),
      h('button', { class: 'btn' + (p.recomendado ? ' primario' : ''), style: 'margin-left:12px;align-self:center', onclick: rodar }, p.tipo === 'sonda' ? 'Sondar VRAM' : 'Rodar Teste')));
}

function tabelaModelos(pl) {
  if (!pl.modelos.length) return h('div', { class: 'vazio' }, 'Nenhum modelo instalado (ou o Ollama está desligado).');
  const linhas = pl.modelos.map(m => {
    const nomeL = nomeAmigavelModelo(m.id);
    const qL = tagQuantModelo(m.id);
    return h('tr', {},
      h('td', {}, h('b', { title: m.id }, nomeL), h('div', { class: 'sub' }, `${qL || m.quant || ''} · ${fmtGB(m.bytes)}`)),
      h('td', {}, m.n_itens ? [chip(NIVEL_NOME[m.nivel] || 'parcial', m.nivel === 'padrao' || m.nivel === 'profundo' ? 'ok' : 'warn'), ' ', h('span', { class: 'sub' }, `${m.n_itens} itens`)] : chip('sem nota', 'bad')),
      h('td', { class: 'sub' }, m.ultima ? m.ultima.slice(0, 10).split('-').reverse().join('/') : '—'),
      h('td', {}, m.sonda ? h('span', {}, '✔ ', m.ctx_max_gpu ? fmtCtx(m.ctx_max_gpu) + ' GPU' : '') : chip('não medida', 'neutro')),
      h('td', {}, m.tem_thinking ? (m.think ? '✔' : chip('não medido', 'neutro')) : h('span', { class: 'sub' }, 'n/a')),
      h('td', { class: 'num' }, m.tps ? fmtN(m.tps, 0) : '—'),
      h('td', { class: 'num', title: m.lat_estimada ? 'estimado pela média' : 'média medida' }, `${fmtN(m.lat_s, 1)} s`),
      h('td', {}, h('div', { class: 'linha', style: 'flex-wrap:nowrap;justify-content:flex-end;gap:4px' },
        h('button', { class: 'btn mini', onclick: () => iniciarBench([m.id], 'padrao') }, m.n_itens ? 'Remedir' : 'Medir'),
        h('button', { class: 'btn mini', title: 'Sondar VRAM real até 1M', onclick: async () => { try { await api('/api/sonda', { modelos: [m.id], ate_ctx: 1048576 }); toast('Sonda iniciada até 1M.'); await carregarJobs(); } catch (e) { toast(e.message, 8000); } } }, 'Sonda'))));
  });
  return h('div', { class: 'tabela-wrap' }, h('table', { class: 'tabela-compacta' }, h('thead', {}, h('tr', {}, ['Modelo', 'Nota (itens)', 'Última', 'Ctx GPU', 'Thinking', 'tok/s', 'Tempo/item', ''].map((t, i) => h('th', { class: i === 5 || i === 6 ? 'num' : '' }, t)))), h('tbody', {}, linhas)));
}

function formularioMedir(pl) {
  const checks = pl.modelos.map(m => {
    const nomeL = nomeAmigavelModelo(m.id);
    const qL = tagQuantModelo(m.id);
    return h('label', { class: 'chk', title: m.id },
      h('input', { type: 'checkbox', value: m.id, checked: true }),
      h('span', {}, h('b', {}, nomeL), qL ? [' ', chip(qL, 'neutro')] : '', ` (${fmtGB(m.bytes)})`));
  });
  const mediaLat = pl.modelos.length ? pl.modelos.reduce((a, m) => a + m.lat_s, 0) / pl.modelos.length : 3;
  const comVisao = pl.modelos.filter(m => m.lat_img_s);
  const latImg = comVisao.length ? comVisao.reduce((a, m) => a + m.lat_img_s, 0) / comVisao.length : 0;
  const niveis = pl.niveis.map(n => h('label', { class: 'chk', style: 'align-items:flex-start' }, h('input', { type: 'radio', name: 'nivel-med', value: n.id, checked: !!n.recomendado }),
    h('span', {}, h('b', { style: 'color:var(--text)' }, `${NIVEL_NOME[n.id]} — ${n.itens} itens`, n.imagens ? ` + ${n.imagens} imagens nos modelos com visão` : ''), n.recomendado ? [' ', chip('recomendado nesta máquina', 'ok')] : '',
      ` · ${fmtMin(Math.round(n.itens * mediaLat / 60))} por modelo`, n.imagens && latImg ? ` (+ ${fmtMin(Math.round(n.imagens * latImg / 60))} se tiver visão)` : '', '. ', n.para)));
  const modo = h('select', {}, [['base', 'Base — sem “pensar”, como você usa no dia a dia'], ['think', 'Raciocínio — pensamento ligado (só mmlu_pro, gsm8k, humaneval)']].map(([v, t]) => h('option', { value: v }, t)));
  const testes = pl.testes.map(t => h('label', { class: 'chk' }, h('input', { type: 'checkbox', value: t.id, checked: true }), t.nome));
  const escolhidos = () => checks.map(l => l.firstChild).filter(c => c.checked).map(c => c.value);
  const nivel = () => (niveis.map(l => l.firstChild).find(r => r.checked) || {}).value || 'padrao';
  const suites = () => { const s = testes.map(l => l.firstChild).filter(c => c.checked).map(c => c.value); return s.length === testes.length ? undefined : s; };
  return h('div', { class: 'cartao' }, h('div', { class: 'grade g2' },
    h('div', { class: 'empilha' }, h('h4', {}, 'Modelos'), h('div', { class: 'empilha', style: 'gap:6px' }, checks), h('h4', {}, 'Nível'), h('div', { class: 'empilha', style: 'gap:8px' }, niveis)),
    h('div', { class: 'empilha' }, h('h4', {}, 'Modo'), modo, h('details', {}, h('summary', {}, 'Escolher os testes (avançado)'), h('div', { class: 'empilha', style: 'gap:6px;margin-top:8px' }, testes)),
      h('div', { class: 'sub' }, 'Retoma de onde parou se for interrompido. Uma tarefa pesada por vez: a GPU ficará ocupada.'))),
    h('div', { class: 'dlg-acoes', style: 'margin-top:14px' }, h('button', { class: 'btn primario', onclick: () => iniciarBench(escolhidos(), nivel(), modo.value, suites(), true) }, 'Rodar benchmark')));
}

function tabelaTestes(pl) {
  return h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Teste', 'O que mede', 'Usado em', 'Itens (R / P / Pf)'].map(t => h('th', {}, t)))),
    h('tbody', {}, pl.testes.map(t => h('tr', {}, h('td', {}, h('b', {}, t.nome)), h('td', { class: 'sub' }, t.mede), h('td', { class: 'sub' }, t.usado_em.join(', ') || '—'),
      h('td', { class: 'num mono' }, `${t.itens.rapido} / ${t.itens.padrao} / ${t.itens.profundo}`))))));
}

function cartaoConfig(cfg) {
  const campo = (rot, chave, dica) => { const i = h('input', { type: 'text', value: cfg[chave] ?? '', inputmode: 'decimal', style: 'width:100px' }); return [h('label', { class: 'campo' }, rot, h('div', { class: 'linha', style: 'justify-content:flex-start' }, i, h('button', { class: 'btn mini', onclick: async () => {
    try { await api('/api/config', { [chave]: Number(String(i.value).replace(',', '.')) }); toast('Salvo.'); S.calcT = 0; } catch (e) { toast(e.message, 8000); } } }, 'Salvar'))), dica ? h('div', { class: 'sub' }, dica) : null]; };
  return h('div', { class: 'cartao empilha' }, h('h3', {}, 'Ajustes'),
    h('p', { class: 'sub', style: 'margin:0' }, `Contexto do benchmark: ${cfg.ctx_bench ?? 8192} (cai para ${(cfg.ctx_fallback || [4096, 2048]).join('/')} se o modelo não ficar 100% na GPU). Mudá-lo muda o protocolo — por isso não é editável aqui.`),
    campo('VRAM reservada ao sistema (GB)', 'reserva_vram_gb', 'Windows, navegador e jogos usam parte da placa. Entra em todas as contas de “cabe?”.'),
    campo('Validade do cache do radar (horas)', 'radar_validade_h'), campo('“Novo” = lançado há menos de (dias)', 'radar_dias_novo'));
}

function desenharJobsMedir() {
  const el = $('#lab-jobs');
  if (!el) return;
  el.replaceChildren(...(S.jobs.length ? S.jobs.slice(0, 10).map(j => h('div', { class: 'acao' }, h('div', {}, h('b', {}, j.titulo), h('span', {}, `${j.estado} · ${j.msg || ''}`)),
    j.estado === 'rodando' ? h('button', { class: 'btn mini', onclick: () => api('/api/cancelar', { job: j.id }) }, 'Cancelar') : chip(j.estado, j.estado === 'concluido' ? 'ok' : j.estado === 'erro' ? 'bad' : 'neutro'))) : [h('div', { class: 'sub' }, 'Nenhuma tarefa ainda.')]));
}


/* ---------------------------------------------------------------- Visão: modelos locais pequenos × o detector atual */
async function desenharVisao(pl) {
  const alvo = $('#cartao-visao');
  if (!alvo) return;
  let d;
  try { d = await api('/api/visao/comparar'); } catch (e) { alvo.replaceChildren(h('div', { class: 'aviso-caixa' }, e.message)); return; }
  const comVisao = (pl.modelos || []).filter(m => (m.caps || []).includes('vision'));
  const marcas = comVisao.map(m => h('label', { class: 'chk', title: m.id }, h('input', { type: 'checkbox', value: m.id, checked: true }), h('span', {}, h('b', {}, nomeAmigavelModelo(m.id)), ` (${fmtGB(m.bytes)})`)));
  const nivel = h('select', {}, ['minimo', 'rapido', 'padrao', 'profundo'].map(n => h('option', { value: n, selected: n === 'rapido' },
    `${NIVEL_NOME[n]} — ${d.niveis[n].leve} imagens sintéticas + ${Math.min(d.niveis[n].fotos, d.fotos_cadastradas)} fotos suas`)));
  const rodar = h('button', { class: 'btn primario', disabled: !comVisao.length, onclick: async () => {
    const ids = marcas.map(l => l.firstChild).filter(c => c.checked).map(c => c.value);
    if (!ids.length) { toast('Marque ao menos um modelo.'); return; }
    await iniciarBench(ids, nivel.value, 'base', d.suites, true);
  } }, 'Rodar teste de visão');
  const pct = x => x == null ? '—' : fmtN(x, 0) + '%';
  const linhas = d.modelos.map(m => h('tr', {},
    h('td', {}, h('b', { title: m.modelo }, nomeAmigavelModelo(m.modelo))),
    h('td', { class: 'num', title: m.leve.ic ? `IC 95%: ${fmtN(m.leve.ic[0], 0)}–${fmtN(m.leve.ic[1], 0)}%` : '' }, pct(m.leve.acc), h('div', { class: 'sub' }, `${m.leve.n} itens`)),
    h('td', { class: 'sub' }, Object.entries(m.leve.categorias).map(([c, v]) => `${c} ${v.k}/${v.n}`).join(' · ')),
    h('td', { class: 'num' }, m.fotos.n ? [pct(m.fotos.exato), h('div', { class: 'sub' }, `erro médio ${m.fotos.erro_medio ?? '—'} · ${m.fotos.n} fotos`)] : '—'),
    h('td', { class: 'num' }, m.lat_s != null ? fmtN(m.lat_s, 1) + ' s' : '—')));
  if (d.detector) linhas.push(h('tr', { class: 'destaque' }, h('td', {}, h('b', {}, '⚙ Detector atual (OpenCV)')), h('td', { class: 'num' }, '—'), h('td', { class: 'sub' }, 'contagem de sementes por área/regras'),
    h('td', { class: 'num' }, pct(d.detector.exato), h('div', { class: 'sub' }, `erro médio ${d.detector.erro_medio} · ${d.detector.n} fotos`)), h('td', { class: 'num' }, '—')));
  alvo.replaceChildren(
    titulo('Visão: modelos locais × detector atual', 'Teste justo para modelos pequenos (Moondream e afins): imagens simples, perguntas curtas, respostas de uma palavra ou número. Roda na máquina que você está controlando.'),
    h('div', { class: 'cartao empilha' },
      comVisao.length ? h('div', { class: 'empilha', style: 'gap:6px' }, h('h4', {}, 'Modelos instalados que declaram visão'), marcas)
        : h('div', { class: 'aviso-caixa' }, 'Nenhum modelo instalado declara visão nesta máquina. Instale um pelo Radar (filtro “Declara: 👁 Visão”).'),
      h('label', { class: 'campo' }, 'Profundidade', nivel),
      h('div', { class: 'sub' }, '30 imagens sintéticas em 5 tipos: contar sementes numa bandeja escura quadriculada (o seu caso), cor, forma, posição e ler um número. As mesmas para todos os modelos. Contagem só vale se o número for exato.'),
      h('div', { class: 'info-caixa' }, h('b', {}, 'Suas fotos reais: '), d.fotos_cadastradas ? `${d.fotos_cadastradas} cadastrada(s).` : 'nenhuma ainda. ',
        ` Coloque as fotos em ${d.pasta_fotos} com um gabarito.json: {"foto1.jpg": {"contagem": 23, "detector": 22}} (contagem = o número certo; detector = o que o sistema atual contou; opcional).`),
      h('div', { class: 'dlg-acoes', style: 'justify-content:flex-start' }, rodar),
      linhas.length ? h('div', { class: 'tabela-wrap' }, h('table', { class: 'tabela-compacta' },
        h('thead', {}, h('tr', {}, ['Modelo', 'Imagens simples', 'Por tipo', 'Fotos suas (contagem)', 'Tempo/imagem'].map(t => h('th', {}, t)))), h('tbody', {}, linhas)))
        : h('div', { class: 'sub' }, 'Ainda não há medições de visão leve.')));
}
