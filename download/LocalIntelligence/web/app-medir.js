'use strict';
/* Página "Medir": diz o que vale rodar AGORA (com motivo e minutos), oferece o duelo entre dois modelos (A × B) e o formulário completo. */

const NIVEL_NOME = { minimo: 'Ultra rápido', rapido: 'Rápido', padrao: 'Médio', profundo: 'Avançado' };
const NIVEL_TITULO = { minimo: 'Teste ultra rápido', rapido: 'Teste rápido', padrao: 'Teste médio', profundo: 'Teste avançado' };
const NIVEL_DESC = {
  minimo: 'Para PCs sem placa de vídeo: sinal rápido de que o modelo funciona.',
  rapido: 'Triagem rápida para ter uma primeira ideia do modelo.',
  padrao: 'Equilíbrio ideal entre tempo e precisão para decidir qual manter.',
  profundo: 'Mais perguntas para máxima precisão e desempate entre modelos parecidos.'
};
const fmtMin = m => m >= 90 ? `~${fmtN(m / 60, 1)} h` : `~${m} min`;

function chaveSugestoesMedir(passos) {
  return (passos || []).map(p => p.id + ':' + (p.modelos || []).join(',')).join('|');
}
function sugestoesMedirOcultas(passos) {
  try { return localStorage.getItem('li-medir-sug-ocultas') === chaveSugestoesMedir(passos); } catch (e) { return false; }
}
function definirSugestoesMedirOcultas(passos, ocultar) {
  try {
    if (ocultar) localStorage.setItem('li-medir-sug-ocultas', chaveSugestoesMedir(passos));
    else localStorage.removeItem('li-medir-sug-ocultas');
  } catch (e) {}
  pMedir();
}

async function pMedir() {
  const raiz = $('#p-medir');
  if (window.LI_PUBLIC_MODE) { paginaPrevia('medir', raiz); return; }
  if (!S.mesa) return;
  const topoBase = (extra) => h('div', { class: 'pagina-topo' },
    h('div', { class: 'linha topo' },
      h('div', {},
        h('span', { class: 'guia-kicker' }, 'BENCHMARKS LOCAIS'),
        h('h1', {}, 'Medir e testar'),
        h('p', { class: 'sub' }, 'Avalie os modelos instalados no seu computador. Ao terminar, as notas aparecem na tabela abaixo, no comparativo de Meus modelos e nas recomendações de Decidir.')),
      extra || null));
  raiz.replaceChildren(topoBase(), h('div', { class: 'sub' }, 'Calculando o que vale medir…'));
  let pl;
  try { pl = await api('/api/lab/plano'); } catch (e) { raiz.append(h('div', { class: 'aviso-caixa' }, e.message)); return; }
  if (S.aba !== 'medir') return;
  let cfg = {};
  try { cfg = await api('/api/config'); } catch (e) { /* segue sem */ }
  if (!pl.modelos.length) {
    raiz.replaceChildren(topoBase(),
      h('div', { class: 'public-empty', style: 'margin:24px auto' },
        h('div', { class: 'public-empty-icon' }, '🧪'),
        h('h2', {}, 'Nenhum modelo instalado para medir ainda'),
        h('p', {}, 'Instale seu primeiro modelo pelo Radar (1 clique) e volte aqui para medir velocidade, limite de memória e qualidade real no seu PC.'),
        h('div', { class: 'linha', style: 'justify-content:center;gap:10px' },
          h('button', { class: 'btn primario', onclick: () => irPara('radar') }, 'Escolher meu primeiro modelo no Radar →'),
          h('button', { class: 'btn', onclick: () => { S.guiasSub = 'usar'; irPara('guias'); } }, 'Ver como começar'))));
    return;
  }

  const ocultas = sugestoesMedirOcultas(pl.passos);
  const barraSugestoes = pl.passos.length && !ocultas ? h('details', { class: 'decidir-avisos-compacto', style: 'margin-top:0;margin-bottom:20px' },
    h('summary', {},
      h('span', { class: 'decidir-avisos-txt' }, h('b', {}, 'Sugestão: '), pl.passos.length === 1 ? pl.passos[0].titulo : `${pl.passos.length} passos sugeridos para completar suas medições`),
      h('span', { class: 'decidir-avisos-ctrl' },
        h('span', { class: 'colapsavel-dica' }, 'Ver detalhes'),
        h('button', { type: 'button', class: 'btn mini fantasma', title: 'Dispensar sugestões', onclick: ev => {
          ev.preventDefault(); ev.stopPropagation();
          definirSugestoesMedirOcultas(pl.passos, true);
        } }, '✕'))),
    h('div', { class: 'decidir-avisos-corpo' }, pl.passos.map(cartaoPasso))) : null;

  raiz.replaceChildren(
    topoBase(ocultas && pl.passos.length ? h('button', { class: 'btn mini fantasma', onclick: () => definirSugestoesMedirOcultas(pl.passos, false) }, `Sugestões (${pl.passos.length})`) : null),
    barraSugestoes,
    titulo('Rodar benchmark', 'Escolha o nível e os modelos. Se algum modelo tiver visão, as provas de imagem entram automaticamente.'),
    formularioMedir(pl),
    titulo('Seus modelos medidos', 'Notas, velocidade e contexto medidos até agora.',
      h('button', { class: 'btn mini', onclick: () => irPara('modelos') }, 'Ver gráficos em Meus modelos'),
      h('button', { class: 'btn mini primario', onclick: () => irPara('decidir') }, 'Ir para Decidir →')),
    tabelaModelos(pl),
    typeof cartaoComunidade === 'function' ? cartaoComunidade() : null,
    titulo('Tarefas em andamento'), h('div', { id: 'lab-jobs' }),
    h('details', { class: 'painel-colapsavel', style: 'margin-top:22px' },
      h('summary', {},
        h('h2', {}, 'O que cada prova mede (Catálogo de Suítes)'),
        h('span', { class: 'colapsavel-dica' }, 'Ver critérios e itens')),
      h('div', { class: 'painel-conteudo' }, tabelaTestes(pl))),
    h('details', { class: 'painel-colapsavel' },
      h('summary', {},
        h('h2', {}, '⚙ Ajustes do sistema'),
        h('span', { class: 'colapsavel-dica' }, 'VRAM reservada e cache do radar')),
      h('div', { class: 'painel-conteudo' }, cartaoConfig(cfg))));
  desenharJobsMedir();
}

function cartaoPasso(p) {
  const rodar = async () => {
    try {
      if (p.tipo === 'sonda') { await api('/api/sonda', { modelos: p.modelos, ate_ctx: 1048576 }); toast('Teste de memória (sonda) iniciado: acompanhe na barra de baixo.'); await carregarJobs(); }
      else await iniciarBench(p.modelos, p.nivel, p.modo, p.suites);
    } catch (e) { toast(e.message, 8000); }
  };
  const chipsModelos = p.modelos.map(mid => {
    const nomeL = nomeAmigavelModelo(mid);
    const qL = tagQuantModelo(mid);
    return chip(`${nomeL}${qL ? ' (' + qL + ')' : ''}`, 'neutro', mid);
  });
  return h('div', { class: 'cartao' + (p.recomendado ? ' destaque' : ''), style: 'border-left:3px solid ' + (p.recomendado ? 'var(--ok, #10b981)' : 'var(--line-strong)') },
    h('div', { class: 'linha topo' },
      h('div', { class: 'grow' },
        h('div', { class: 'linha', style: 'justify-content:flex-start;gap:8px;margin-bottom:4px' },
          h('h3', { style: 'font-size:1.02rem;margin:0' }, p.titulo),
          p.recomendado ? chip('Recomendado', 'ok') : null,
          p.minutos ? chip('⏱ ' + fmtMin(p.minutos), 'neutro') : null),
        h('p', { class: 'sub', style: 'margin:4px 0 10px;line-height:1.45' }, p.porque),
        h('div', { class: 'linha', style: 'justify-content:flex-start;gap:6px;align-items:center' },
          h('span', { class: 'sub', style: 'font-weight:600' }, 'Modelos:'),
          h('div', { class: 'chips' }, ...chipsModelos),
          p.nivel ? chip('Nível ' + NIVEL_NOME[p.nivel], 'neutro') : null,
          p.modo === 'think' ? chip('Raciocínio ligado', 'warn') : null)),
      h('button', { class: 'btn' + (p.recomendado ? ' primario' : ''), style: 'margin-left:12px;align-self:center', onclick: rodar }, p.tipo === 'sonda' ? 'Testar memória' : 'Rodar Teste')));
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
        h('button', { class: 'btn mini', onclick: () => iniciarBench([m.id], 'padrao', 'base', undefined, true, !!m.n_itens) }, m.n_itens ? 'Remedir' : 'Medir'),
        h('button', { class: 'btn mini', title: 'Sondar limite real de memória (VRAM) e contexto na GPU', onclick: async () => { try { await api('/api/sonda', { modelos: [m.id], ate_ctx: 1048576 }); toast('Teste de memória (sonda) iniciado.'); await carregarJobs(); } catch (e) { toast(e.message, 8000); } } }, 'Testar memória'))));
  });
  return h('div', { class: 'tabela-wrap' }, h('table', { class: 'tabela-compacta' }, h('thead', {}, h('tr', {}, ['Modelo', 'Nível medido', 'Última', 'Contexto GPU', 'Thinking', 'tok/s', 'Tempo/item', ''].map((t, i) => h('th', { class: i === 5 || i === 6 ? 'num' : '' }, t)))), h('tbody', {}, linhas)));
}

function formularioMedir(pl) {
  if (!pl.modelos.length) return h('div', { class: 'vazio' }, 'Instale pelo menos um modelo no Radar para rodar benchmarks.');
  const ordem = { minimo: 0, rapido: 1, padrao: 2, profundo: 3 };
  const checks = pl.modelos.map(m => {
    const nomeL = nomeAmigavelModelo(m.id);
    const qL = tagQuantModelo(m.id);
    return h('label', { class: 'chk', title: m.id },
      h('input', { type: 'checkbox', value: m.id, checked: true, onchange: () => atualizarResumo() }),
      h('span', {}, h('b', {}, nomeL), qL ? [' ', chip(qL, 'neutro')] : '', m.tem_visao ? [' ', chip('👁 visão', 'neutro')] : '', ` (${fmtGB(m.bytes)})`));
  });
  const mediaLat = pl.modelos.length ? pl.modelos.reduce((a, m) => a + m.lat_s, 0) / pl.modelos.length : 3;
  const temAlgumVisao = pl.modelos.some(m => m.tem_visao);
  const niveisVisiveis = pl.niveis.filter(n => n.id !== 'minimo' || pl.maquina?.nivel_recomendado === 'minimo');
  let nivelSel = (niveisVisiveis.find(n => n.recomendado) || niveisVisiveis[1] || niveisVisiveis[0]).id;

  const cardsWrap = h('div', { class: 'bench-niveis' });
  const resumoStatus = h('div', { class: 'sub' });
  const chkRefazer = h('input', { type: 'checkbox', onchange: () => atualizarResumo() });
  const modo = h('select', {}, [['base', 'Base — uso normal do dia a dia'], ['think', 'Raciocínio — pensamento ligado (modelos compatíveis)']].map(([v, t]) => h('option', { value: v }, t)));
  const testes = pl.testes.map(t => h('label', { class: 'chk' }, h('input', { type: 'checkbox', value: t.id, checked: true }), t.nome));

  const escolhidos = () => checks.map(l => l.firstChild).filter(c => c.checked).map(c => c.value);
  const suites = () => { const s = testes.map(l => l.firstChild).filter(c => c.checked).map(c => c.value); return s.length === testes.length ? undefined : s; };

  function desenharCards() {
    cardsWrap.replaceChildren(...niveisVisiveis.map(n => {
      const ativo = n.id === nivelSel;
      const mins = Math.max(1, Math.round(n.itens * mediaLat / 60));
      return h('button', {
        type: 'button',
        class: 'bench-nivel-card' + (ativo ? ' ativo' : ''),
        'aria-pressed': String(ativo),
        onclick: () => { nivelSel = n.id; desenharCards(); atualizarResumo(); }
      },
        h('div', { class: 'linha' },
          h('b', {}, NIVEL_TITULO[n.id] || NIVEL_NOME[n.id]),
          n.recomendado ? chip('Recomendado', 'ok') : null),
        h('div', { class: 'bench-nivel-meta' }, `${n.itens} itens${temAlgumVisao && n.imagens ? ` + ${n.imagens} imagens` : ''} · ${fmtMin(mins)}/modelo`),
        h('p', { class: 'sub' }, NIVEL_DESC[n.id] || n.para));
    }));
  }

  function atualizarResumo() {
    const ids = escolhidos();
    if (!ids.length) { resumoStatus.textContent = 'Selecione pelo menos um modelo.'; return; }
    const jaNoNivel = ids.filter(id => {
      const m = pl.modelos.find(x => x.id === id);
      return m && m.nivel && (ordem[m.nivel] ?? -1) >= (ordem[nivelSel] ?? 0);
    });
    if (jaNoNivel.length === ids.length && !chkRefazer.checked) {
      resumoStatus.textContent = `Todos os modelos selecionados já foram medidos no ${NIVEL_TITULO[nivelSel] || nivelSel}. Escolha um nível maior ou marque "Refazer do zero".`;
    } else if (jaNoNivel.length > 0 && !chkRefazer.checked) {
      resumoStatus.textContent = `${jaNoNivel.length} modelo(s) já medido(s) neste nível serão reaproveitados; os demais serão medidos agora.`;
    } else {
      resumoStatus.textContent = chkRefazer.checked
        ? `Vai rodar o ${NIVEL_TITULO[nivelSel]} do zero em ${ids.length} modelo(s). Ao terminar, os resultados atualizam a tabela abaixo, Meus modelos e Decidir.`
        : `Vai medir ${ids.length} modelo(s) no ${NIVEL_TITULO[nivelSel]}. Ao terminar, os resultados atualizam a tabela abaixo, Meus modelos e Decidir.`;
    }
  }

  desenharCards();
  atualizarResumo();

  return h('div', { class: 'cartao empilha', style: 'gap:16px' },
    h('div', { class: 'empilha', style: 'gap:8px' },
      h('h4', {}, '1. Escolha o nível do teste'),
      cardsWrap),
    h('div', { class: 'empilha', style: 'gap:8px' },
      h('h4', {}, '2. Quais modelos medir'),
      h('div', { class: 'linha', style: 'justify-content:flex-start;gap:12px 18px;flex-wrap:wrap' }, checks)),
    h('details', { class: 'dica-clean' },
      h('summary', {}, '⚙ Opções técnicas (refazer do zero, modo raciocínio, escolher provas)'),
      h('div', { class: 'empilha', style: 'gap:10px;margin-top:10px' },
        h('label', { class: 'chk' }, chkRefazer, 'Refazer do zero (ignorar medições anteriores deste nível)'),
        h('label', { class: 'campo' }, 'Modo de execução', modo),
        h('div', { class: 'empilha', style: 'gap:6px' }, h('span', { class: 'sub' }, 'Provas incluídas:'), h('div', { class: 'linha', style: 'justify-content:flex-start;gap:8px 16px;flex-wrap:wrap' }, testes)))),
    h('div', { class: 'linha', style: 'gap:12px;flex-wrap:wrap' },
      resumoStatus,
      h('button', { class: 'btn primario', onclick: () => {
        const ids = escolhidos();
        if (!ids.length) { toast('Marque pelo menos um modelo.'); return; }
        iniciarBench(ids, nivelSel, modo.value, suites(), true, chkRefazer.checked);
      } }, 'Rodar benchmark')));
}

function tabelaTestes(pl) {
  return h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Teste', 'O que mede', 'Usado em', 'Itens (R / M / A)'].map(t => h('th', {}, t)))),
    h('tbody', {}, pl.testes.map(t => h('tr', {}, h('td', {}, h('b', {}, t.nome)), h('td', { class: 'sub' }, t.mede), h('td', { class: 'sub' }, t.usado_em.join(', ') || '—'),
      h('td', { class: 'num mono' }, `${t.itens.rapido} / ${t.itens.padrao} / ${t.itens.profundo}`))))));
}

function cartaoConfig(cfg) {
  const campo = (rot, chave, dica) => { const i = h('input', { type: 'text', value: cfg[chave] ?? '', inputmode: 'decimal', style: 'width:100px' }); return [h('label', { class: 'campo' }, rot, h('div', { class: 'linha', style: 'justify-content:flex-start' }, i, h('button', { class: 'btn mini', onclick: async () => {
    try { await api('/api/config', { [chave]: Number(String(i.value).replace(',', '.')) }); toast('Salvo.'); S.calcT = 0; } catch (e) { toast(e.message, 8000); } } }, 'Salvar'))), dica ? h('div', { class: 'sub' }, dica) : null]; };
  return h('div', { class: 'empilha' },
    h('p', { class: 'sub', style: 'margin:0' }, `Contexto do benchmark: ${cfg.ctx_bench ?? 8192} (cai para ${(cfg.ctx_fallback || [4096, 2048]).join('/')} se o modelo não ficar 100% na GPU).`),
    campo('VRAM reservada ao sistema (GB)', 'reserva_vram_gb', 'Windows, navegador e jogos usam parte da placa. Entra em todas as contas de “cabe?”.'),
    campo('Validade do cache do radar (horas)', 'radar_validade_h'), campo('“Novo” = lançado há menos de (dias)', 'radar_dias_novo'));
}

function desenharJobsMedir() {
  const el = $('#lab-jobs');
  if (!el) return;
  el.replaceChildren(...(S.jobs.length ? S.jobs.slice(0, 10).map(j => h('div', { class: 'acao' }, h('div', {}, h('b', {}, j.titulo), h('span', {}, `${j.estado} · ${j.msg || ''}`)),
    j.estado === 'rodando' ? h('button', { class: 'btn mini', onclick: () => api('/api/cancelar', { job: j.id }) }, 'Cancelar') : chip(j.estado, j.estado === 'concluido' ? 'ok' : j.estado === 'erro' ? 'bad' : 'neutro'))) : [h('div', { class: 'sub' }, 'Nenhuma tarefa ainda.')]));
}
