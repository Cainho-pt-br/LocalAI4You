'use strict';
/* Páginas "Decidir" e "Meus modelos" (titulares, desafiantes, o que dá para liberar, aposentados, duelo direto e fixar contexto). */

// ---------------------------------------------------------------- DECIDIR
function chaveManchete(m) {
  return (m.manchete?.nivel || '') + '|' + (m.manchete?.texto || '') + '|' + (m.acoes || []).map(a => a.tipo + ':' + a.titulo).join(',');
}
function mancheteOculta(m) {
  try { return localStorage.getItem('li-manchete-oculta') === chaveManchete(m); } catch (x) { return false; }
}
function definirMancheteOculta(m, ocultar) {
  try {
    if (ocultar) localStorage.setItem('li-manchete-oculta', chaveManchete(m));
    else localStorage.removeItem('li-manchete-oculta');
  } catch (x) {}
  pDecidir();
}

function alertaOculto(alerta) {
  try { return localStorage.getItem('li-alerta-oculto') === (alerta?.texto || ''); } catch (x) { return false; }
}
function definirAlertaOculto(alerta, ocultar) {
  try {
    if (ocultar) localStorage.setItem('li-alerta-oculto', alerta?.texto || '');
    else localStorage.removeItem('li-alerta-oculto');
  } catch (x) {}
  pDecidir();
}

function obterModelosDispensados() {
  try { return new Set(JSON.parse(localStorage.getItem('li-modelos-dispensados') || '[]')); } catch (e) { return new Set(); }
}
function alternarDispensarModelo(id) {
  const s = obterModelosDispensados();
  if (s.has(id)) s.delete(id); else s.add(id);
  try { localStorage.setItem('li-modelos-dispensados', JSON.stringify([...s])); } catch (e) {}
}

function obterModelosMantidos() {
  try { return new Set(JSON.parse(localStorage.getItem('li-modelos-mantidos') || '[]')); } catch (e) { return new Set(); }
}
function alternarManterModelo(id) {
  const s = obterModelosMantidos();
  if (s.has(id)) s.delete(id); else s.add(id);
  try { localStorage.setItem('li-modelos-mantidos', JSON.stringify([...s])); } catch (e) {}
}

function pDecidir() {
  const m = S.mesa, raiz = $('#p-decidir');
  if (window.LI_PUBLIC_MODE) { paginaPrevia('decidir', raiz); return; }
  if (!m) { raiz.replaceChildren(h('div', { class: 'vazio' }, 'Carregando…')); return; }
  const pend = (m.vereditos || []).filter(v => v.pendente);
  const oculto = mancheteOculta(m);
  const papeisNota = m.papeis.filter(p => !p.sem_nota);
  const inst = m.instalados || [];

  // Campeão geral por Índice Prático Multicritério
  const campeao = [...inst].sort((a, b) => (b.indice_pratico?.total ?? -1) - (a.indice_pratico?.total ?? -1))[0] || null;
  const mantidos = obterModelosMantidos();
  const dispAtivos = (m.dispensaveis || []).filter(d => !mantidos.has(d.modelo));
  const dispMantidos = (m.dispensaveis || []).filter(d => mantidos.has(d.modelo));
  const espacoLiberavel = dispAtivos.reduce((acc, d) => acc + (d.bytes || 0), 0);

  // Melhor desafiante global não dispensado
  const dispensados = obterModelosDispensados();
  let topDesaf = null;
  for (const lst of Object.values(m.desafiantes || {})) {
    for (const c of lst || []) {
      if (dispensados.has(c.id) || dispensados.has(c.nome)) continue;
      if (!topDesaf || (c.prioridade?.pontos || 0) > (topDesaf.prioridade?.pontos || 0)) topDesaf = c;
    }
  }

  const comandoBar = h('div', { class: 'decidir-cmd-grid' },
    h('div', { class: 'decidir-kpi-card kpi-campeao', onclick: () => campeao && detalheModelo(campeao.id), style: 'cursor:pointer', title: 'Clique para inspecionar métricas completas do líder atual' },
      h('div', { class: 'kpi-top' }, h('span', { class: 'kpi-tag' }, '👑 Melhor modelo no geral'), campeao?.indice_pratico ? chip(`⚡ Índice ${fmtN(campeao.indice_pratico.total, 1)}`, 'ok') : null),
      h('div', { class: 'kpi-main' }, campeao ? nomeAmigavelModelo(campeao.id) : '—'),
      h('div', { class: 'kpi-sub' }, campeao ? `${campeao.medido?.tps_mediana ? fmtN(campeao.medido.tps_mediana, 0) + ' tok/s · ' : ''}${fmtGB(campeao.bytes)} · ${fmtCtx(campeao.sonda?.ctx_max_gpu || campeao.ctx_por_kv?.q8_0?.ctx_max)} GPU` : 'Nenhum modelo medido')),
    h('div', { class: 'decidir-kpi-card kpi-liberar', onclick: () => {
      const el = document.getElementById('sec-substituir');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, style: dispAtivos.length ? 'cursor:pointer' : '' },
      h('div', { class: 'kpi-top' }, h('span', { class: 'kpi-tag' }, '🧹 Otimização & Espaço'), dispAtivos.length ? chip(`${dispAtivos.length} substituível(is)`, 'warn') : chip('Sem sobras', 'ok')),
      h('div', { class: 'kpi-main' }, dispAtivos.length ? `Liberar ${fmtGB(espacoLiberavel)}` : '0 GB redundantes'),
      h('div', { class: 'kpi-sub' }, dispAtivos.length ? `Cobertos com vantagem por ${nomeAmigavelModelo(dispAtivos[0].substituto || campeao?.id)}` : (dispMantidos.length ? `${dispMantidos.length} modelo(s) mantido(s) por você` : 'Nenhum modelo superado no disco'))),
    h('div', { class: 'decidir-kpi-card kpi-desaf', onclick: () => topDesaf ? abrirTeste(topDesaf.id, topDesaf.papel) : irPara('radar'), style: 'cursor:pointer' },
      h('div', { class: 'kpi-top' }, h('span', { class: 'kpi-tag' }, '🔭 Desafiante no Radar'), topDesaf ? chip(`prio ${topDesaf.prioridade.pontos}/100`, 'prioridade') : chip('Em dia', 'neutro')),
      h('div', { class: 'kpi-main' }, topDesaf ? nomeAmigavelModelo(topDesaf.nome) : 'Explorar Radar'),
      h('div', { class: 'kpi-sub' }, topDesaf ? `${topDesaf.encaixe?.variante?.quant || ''} · ${fmtGB(topDesaf.encaixe?.variante?.bytes || 0)} · Testar contra o atual ▸` : 'Ver lançamentos dos últimos 9 meses ▸')),
    h('div', { class: 'decidir-kpi-card kpi-update' },
      h('div', { class: 'kpi-top' }, h('span', { class: 'kpi-tag' }, '🔄 Manutenção Contínua'), chip(`${inst.length} instalados`, 'neutro')),
      h('div', { class: 'kpi-main' }, 'Atualizar & Varrer'),
      h('div', { class: 'linha', style: 'justify-content:flex-start;gap:6px;margin-top:4px' },
        h('button', { class: 'btn mini primario', title: 'Executa ollama pull em todos os modelos instalados para buscar pesos atualizados', onclick: () => atualizarModelosInstalados() }, '↻ Atualizar atuais'),
        h('button', { class: 'btn mini', title: 'Varre Ollama e Hugging Face por novos modelos', onclick: () => varrer(true) }, '🔭 Varrer Radar'),
        h('button', { class: 'btn mini fantasma', onclick: () => { irPara('modelos'); setTimeout(() => document.getElementById('sec-arena')?.scrollIntoView({ behavior: 'smooth' }), 80); } }, '⚔ Duelo A×B'))));

  const acoesVisiveis = (m.acoes || []).filter(a => !(a.tipo === 'limpar' && !dispAtivos.length));

  raiz.replaceChildren(
    h('div', { class: 'pagina-topo' },
      h('div', { class: 'linha topo' },
        h('div', {},
          h('div', { class: 'eyebrow-tech' }, 'LOCAL AI SEARCH · SEUS MODELOS'),
          h('h1', {}, 'Decidir'),
          h('p', { class: 'sub' }, 'O resumo dos seus modelos: qual é o melhor para cada uso, qual pode ser apagado sem perda e qual modelo novo vale testar.')),
        oculto ? h('button', { class: 'btn mini', onclick: () => definirMancheteOculta(m, false) }, `Mostrar avisos (${acoesVisiveis.length})`) : null)),
    comandoBar,
    !oculto && acoesVisiveis.length ? h('div', { class: 'hero n-' + m.manchete.nivel, style: 'position:relative;margin-top:16px' },
      h('div', { class: 'linha topo' },
        h('div', { class: 'grow' }, h('div', { class: 'sub' }, 'Diagnóstico imediato'), h('h2', {}, m.manchete.texto)),
        h('button', { class: 'btn mini fantasma', title: 'Dispensar este cartão de aviso', onclick: () => definirMancheteOculta(m, true) }, '✕ Dispensar')),
      acoesVisiveis.length ? h('div', { class: 'acoes' }, acoesVisiveis.map(a => h('div', { class: 'acao' },
        h('div', {}, h('b', {}, a.titulo), h('span', {}, a.detalhe)),
        h('button', { class: 'btn' + (a.prioridade <= 2 ? ' primario' : ''), onclick: () => executarAcao(a) }, a.botao)))) : null) : null,
    m.alerta && m.alerta.destaques?.length && !alertaOculto(m.alerta) ? h('div', { class: 'aviso-caixa', style: 'margin-top:14px' },
      h('div', { class: 'linha' },
        h('div', {}, h('b', {}, `Vigia (${fmtIdade(m.alerta.idade_dias)}): `), m.alerta.texto),
        h('div', { class: 'linha', style: 'gap:6px' },
          h('button', { class: 'btn mini primario', onclick: () => { definirAlertaOculto(m.alerta, true); irPara('radar'); } }, 'Ver no radar'),
          h('button', { class: 'btn mini fantasma', onclick: () => definirAlertaOculto(m.alerta, true) }, '✕ Dispensar')))) : null,
    pend.length ? [titulo('Vereditos concluídos aguardando decisão', 'Compare os números medidos antes de promover ou descartar.'), h('div', { class: 'grade g2' }, pend.map(cartaoVeredito))] : null,
    titulo('1. O melhor modelo para cada uso', 'Clique em um uso para ver as notas do modelo atual ou testar um modelo novo contra ele.',
      h('button', { class: 'btn mini', onclick: () => { irPara('modelos'); setTimeout(() => document.getElementById('sec-arena')?.scrollIntoView({ behavior: 'smooth' }), 80); } }, '⚔ Fazer um duelo (A × B)')),
    h('div', { class: 'grade g3' }, m.papeis.map(p => cartaoPapel(p, m))),
    dispAtivos.length ? [
       h('div', { id: 'sec-substituir' }, titulo('2. Sugestões de Aposentadoria e Substituição', 'Modelos que empatam ou perdem em nota para outro já instalado, mas são mais lentos ou ocupam mais VRAM/disco.')),
      h('div', { class: 'grade g2' }, dispAtivos.map(d => cartaoSubstituicao(d, m, papeisNota)))
    ] : null,
    dispMantidos.length ? h('details', { class: 'dica-clean', style: 'margin-top:14px' },
      h('summary', {}, `✓ Você escolheu manter ${dispMantidos.length} modelo(s) que você quis guardar (${dispMantidos.map(d => nomeAmigavelModelo(d.modelo)).join(', ')})`),
      h('div', { class: 'linha', style: 'justify-content:flex-start;gap:8px;margin-top:8px;flex-wrap:wrap' },
        dispMantidos.map(d => h('div', { class: 'chip neutro', style: 'display:inline-flex;align-items:center;gap:6px;padding:4px 10px' },
          h('b', {}, nomeAmigavelModelo(d.modelo)),
          `(${fmtGB(d.bytes)})`,
          h('button', { class: 'btn mini fantasma', style: 'padding:2px 6px;font-size:.72rem', onclick: () => { alternarManterModelo(d.modelo); pDecidir(); } }, 'Reavaliar sugestão'))))) : null,
    h('details', { class: 'dica-clean', style: 'margin-top:26px' },
      h('summary', {}, 'Legenda dos selos de evidência (MEDIDO, ESTIMADO, PRIORIDADE) e Histórico de Trocas'),
      legendaSelos(),
      (m.historico || []).length ? h('div', { style: 'margin-top:12px;padding-top:10px;border-top:1px solid var(--line)' },
        h('b', { style: 'font-size:.82rem;color:var(--text)' }, 'Últimas trocas de modelo:'),
        [...m.historico].reverse().slice(0, 8).map(x =>
          h('div', { class: 'sub', style: 'font-size:.8rem;margin-top:3px' }, `${x.quando.slice(0, 10)} · ${papelPorId(x.papel)?.rotulo || x.papel}: ${nomeAmigavelModelo(x.de) || '—'} → ${nomeAmigavelModelo(x.para)} (${x.motivo || ''})`))) : null));
}

function cartaoSubstituicao(d, m, papeisNota) {
  const modAntigo = (m.instalados || []).find(x => x.id === d.modelo);
  const modSub = d.substituto ? (m.instalados || []).find(x => x.id === d.substituto) : null;
  const nomeAnt = nomeAmigavelModelo(d.modelo);
  const qAnt = tagQuantModelo(d.modelo);
  const nomeSub = d.substituto ? nomeAmigavelModelo(d.substituto) : null;
  const qSub = d.substituto ? tagQuantModelo(d.substituto) : null;

  const mediaAnt = modAntigo ? mediaGeralModelo(modAntigo, papeisNota) : null;
  const mediaSub = modSub ? mediaGeralModelo(modSub, papeisNota) : null;
  const tpsAnt = modAntigo?.medido?.tps_mediana;
  const tpsSub = modSub?.medido?.tps_mediana;
  const ratioVel = (tpsAnt && tpsSub && tpsSub > tpsAnt) ? (tpsSub / tpsAnt) : null;

  return h('div', { class: 'cartao sub-card-tech' },
    h('div', { class: 'linha topo' },
      h('div', {},
        h('span', { class: 'kpi-tag', style: 'color:var(--warn)' }, 'Candidato à Aposentadoria'),
        h('h3', { style: 'margin-top:2px;display:flex;align-items:center;gap:6px;flex-wrap:wrap' },
          nomeAnt, qAnt ? chip(qAnt, 'neutro') : null, chip('libera ' + d.liberaria, 'warn'))),
      h('div', { class: 'linha', style: 'gap:6px' },
        h('button', {
          class: 'btn mini',
          title: 'Quero continuar com este modelo e ocultar esta sugestão de aposentadoria',
          onclick: () => { alternarManterModelo(d.modelo); toast(`✔ ${nomeAnt} mantido (sugestão ocultada).`); pDecidir(); }
        }, '✓ Manter modelo'),
        h('button', { class: 'btn perigo mini', onclick: () => confirmarAposentar(d) }, 'Aposentar…'))),
    modSub ? h('div', { class: 'sub-vs-box' },
      h('div', { class: 'sub-vs-col' },
        h('small', {}, 'Saindo'),
        h('b', {}, nomeAnt),
        h('span', {}, `${mediaAnt != null ? fmtN(mediaAnt, 1) + ' pts' : '—'} · ${tpsAnt ? fmtN(tpsAnt, 0) + ' tok/s' : '—'} · ${fmtGB(d.bytes)}`)),
      h('div', { class: 'sub-vs-arrow' }, ratioVel && ratioVel >= 1.2 ? `⚡ ${fmtN(ratioVel, 1)}×` : '➔'),
      h('div', { class: 'sub-vs-col ok' },
        h('small', {}, 'Substituto melhor entre os seus'),
        h('b', {}, '👑 ' + nomeSub, qSub ? ` (${qSub})` : ''),
        h('span', {}, `${mediaSub != null ? fmtN(mediaSub, 1) + ' pts' : '—'} · ${tpsSub ? fmtN(tpsSub, 0) + ' tok/s' : '—'} · ${fmtGB(modSub.bytes)}`))) : null,
    h('p', { class: 'sub', style: 'font-size:.81rem;margin:6px 0 0;line-height:1.45' },
      d.motivo.replaceAll(d.substituto || '__none__', nomeSub || '')));
}

async function atualizarModelosInstalados(modelos) {
  try {
    await api('/api/atualizar', { modelos: modelos || [] });
    toast('↻ Verificação e atualização dos modelos iniciada. Acompanhe na barra inferior.');
    await carregarJobs();
  } catch (e) { toast(e.message, 8000); }
}

function cartaoPapel(p, m) {
  const mid = m.titulares[p.id];
  const inst = m.instalados.find(x => x.id === mid);
  const med = inst?.medido?.papeis?.[p.id];
  const dispensados = obterModelosDispensados();

  // Buscar desafiante: primeiro que NÃO estiver dispensado pelo usuário
  const desafLista = m.desafiantes[p.id] || [];
  let desaf = desafLista.find(d => !dispensados.has(d.id) && !dispensados.has(d.nome));
  let ehDesafDispensado = false;
  if (!desaf && desafLista.length) {
    desaf = desafLista[0];
    ehDesafDispensado = true;
  }

  let notaEl = null;
  let subMetricas = 'Ainda não medido';
  let badgeTitular = chip('Sem modelo', 'neutro');

  if (p.sem_nota) {
    const comVisao = m.instalados.filter(x => (x.caps || []).includes('vision'));
    subMetricas = comVisao.length ? `${comVisao.length} modelo(s) com visão` : 'Nenhum instalado';
    badgeTitular = comVisao.length ? chip('Visão instalada', 'ok') : chip('Sem visão', 'neutro');
  } else if (inst && med && med.nota != null) {
    notaEl = h('div', { class: 'nota ' + notaClasse(med.nota) },
      h('b', {}, fmtN(med.nota, 0)),
      h('small', {}, '/100'));
    const sonda = inst.sonda;
    const ctxGpu = sonda?.ctx_max_gpu ? fmtCtx(sonda.ctx_max_gpu) : (inst.ctx_por_kv?.q8_0?.ctx_max ? '~' + fmtCtx(inst.ctx_por_kv.q8_0.ctx_max) : null);
    const partes = [];
    if (inst.medido?.tps_mediana) partes.push(fmtN(inst.medido.tps_mediana, 0) + ' tok/s');
    if (ctxGpu) partes.push(ctxGpu + ' GPU');
    partes.push(fmtGB(inst.bytes));
    subMetricas = partes.join(' · ');
    const nomeLimpo = nomeAmigavelModelo(inst.id);
    badgeTitular = chip('👑 ' + nomeLimpo, 'ok', inst.id);
  } else if (inst) {
    badgeTitular = chip(nomeAmigavelModelo(inst.id), 'neutro', inst.id);
    subMetricas = 'Instalado, sem teste nesta função';
  }

  let desafEl = null;
  if (desaf) {
    const nomeDesaf = nomeAmigavelModelo(desaf.id || desaf.nome);
    desafEl = h('div', {
      class: 'papel-desaf-pill' + (ehDesafDispensado ? ' modelo-dispensado' : ''),
      title: desaf.prioridade.razoes.join('\n') + (ehDesafDispensado ? '\n(Dispensado por você)' : '')
    },
      h('span', { class: 'txt-desaf' }, ehDesafDispensado ? '⚪ ' : '⚡ ', h('b', {}, nomeDesaf), ehDesafDispensado ? ' (dispensado)' : ''),
      chip(`prio ${desaf.prioridade.pontos}`, ehDesafDispensado ? 'neutro' : 'prioridade'));
  } else {
    desafEl = h('div', { class: 'sub', style: 'font-size:.78rem;color:var(--muted)' }, '✓ Nada novo para testar');
  }

  return h('div', {
    class: 'cartao papel-clean',
    role: 'button',
    tabindex: 0,
    title: 'Clique para ver o ranking completo, desafiantes e evidências',
    onclick: () => abrirPainelPapel(p, m),
    onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrirPainelPapel(p, m); } }
  },
    h('div', { class: 'papel-clean-head' },
      h('div', { class: 'papel-clean-tit' },
        h('span', { class: 'papel-clean-ic' }, p.icone),
        h('h3', {}, p.rotulo)),
      badgeTitular),
    notaEl ? h('div', { class: 'papel-clean-nota' },
               notaEl,
               h('div', { class: 'papel-clean-met' }, subMetricas))
           : h('div', { class: 'papel-clean-vazio' }, subMetricas),
    desafEl,
    h('div', { class: 'papel-clean-foot' },
      h('span', {}, 'Ver evidências e ranking ▸'),
      h('span', { style: 'font-size:.75rem;opacity:.7' }, 'Clique p/ abrir')));
}

function abrirPainelPapel(p, m) {
  const mid = m.titulares[p.id];
  const inst = m.instalados.find(x => x.id === mid);
  const med = inst?.medido?.papeis?.[p.id];
  const desaf = (m.desafiantes[p.id] || [])[0];
  const rank = (m.ranking || {})[p.id] || [];

  const blocos = [];

  // Topo do modal
  blocos.push(
    h('div', { class: 'linha topo' },
      h('div', { class: 'grow' },
        h('h2', { style: 'display:flex;align-items:center;gap:10px' },
          h('span', { style: 'font-size:1.6rem' }, p.icone),
          p.rotulo),
        h('p', { class: 'sub', style: 'margin-top:6px' }, p.descricao)),
      h('button', { class: 'btn mini fantasma', onclick: fecharDialogo }, '✕ Fechar'))
  );

  if (p.onde || p.nota) {
    blocos.push(
      h('div', { class: 'sub', style: 'font-size:.84rem;margin:2px 0 10px;display:flex;gap:12px;flex-wrap:wrap' },
        p.onde ? h('span', {}, h('b', {}, 'Onde usar: '), p.onde) : null,
        p.nota ? h('span', { style: 'color:var(--muted)' }, 'ℹ ' + p.nota) : null));
  }

  // Bloco Titular
  let cartaoTitular = null;
  if (p.sem_nota) {
    const comVisao = m.instalados.filter(x => (x.caps || []).includes('vision'));
    cartaoTitular = h('div', { class: 'cartao' },
      h('h3', {}, 'Modelos com Visão instalados'),
      comVisao.length
        ? h('p', {}, comVisao.map(x => nomeAmigavelModelo(x.id)).join(', ') + ' — suporte a visão declarado pelo Ollama.')
        : h('p', { class: 'sub' }, 'Nenhum modelo instalado com capacidade visual.'));
  } else if (inst && med && med.nota != null) {
    const ic = med.ic ? Math.round((med.ic[1] - med.ic[0]) / 2) : null;
    const sonda = inst.sonda;
    const ctxAlvo = sonda?.ctx_max_gpu || inst.ctx_por_kv?.q8_0?.ctx_max || p.ctx_alvo || 16384;
    const nomeLimpo = nomeAmigavelModelo(inst.id);
    const quantLimpa = tagQuantModelo(inst.id);
    cartaoTitular = h('div', { class: 'cartao', style: 'border-left:4px solid var(--ok);display:flex;flex-direction:column;gap:8px' },
      h('div', { class: 'linha' },
        h('div', {},
          h('span', { class: 'sub', style: 'font-size:.76rem;text-transform:uppercase;font-weight:700' }, 'Modelo atual'),
          h('h3', {}, '👑 ' + nomeLimpo, quantLimpa ? [' ', chip(quantLimpa, 'neutro')] : null)),
        CHIP_MEDIDO()),
      h('div', { class: 'nota ' + notaClasse(med.nota), style: 'margin:2px 0' },
        h('b', {}, fmtN(med.nota, 0)),
        h('small', {}, ic != null ? `± ${ic} pts (IC 90%)` : 'pts (0–100)'),
        m.titulares_sugeridos[p.id]?.indice_pratico != null
          ? h('span', { class: 'chip ok', style: 'margin-left:8px;font-size:.76rem', title: 'Índice Prático nesta função (Conhecimento + Velocidade + Tamanho + Contexto GPU)' }, `⚡ Índice ${fmtN(m.titulares_sugeridos[p.id].indice_pratico, 1)}`)
          : null),
      h('div', { class: 'metricas' },
        inst.medido.tps_mediana ? h('span', {}, h('b', {}, fmtN(inst.medido.tps_mediana, 0)), ' tok/s') : null,
        h('span', {}, h('b', {}, fmtGB(inst.bytes)), ' disco'),
        sonda?.ctx_max_gpu ? h('span', {}, 'contexto ', h('b', {}, fmtCtx(sonda.ctx_max_gpu)), ' GPU') : h('span', {}, 'contexto ~est.'),
        h('span', {}, 'cobertura ', h('b', {}, Math.round(med.cobertura * 100) + '%'))),
      m.titulares_sugeridos[p.id]?.motivo?.startsWith('empate')
        ? h('div', { class: 'info-caixa', style: 'font-size:.8rem;padding:6px 9px' }, '⚖ ' + m.titulares_sugeridos[p.id].motivo)
        : null,
      h('div', { class: 'linha', style: 'justify-content:flex-start;margin-top:auto;padding-top:8px;gap:6px' },
        h('button', { class: 'btn primario mini', onclick: () => fixarContextoDialogo(inst.id, ctxAlvo) }, `Fixar (${fmtCtx(ctxAlvo)})`),
        h('button', { class: 'btn mini', onclick: () => detalheModelo(inst.id) }, 'Detalhes'),
        h('button', { class: 'btn mini fantasma', onclick: () => iniciarBench([inst.id], 'padrao') }, 'Remedir')));
  } else if (inst) {
    cartaoTitular = h('div', { class: 'cartao' },
      h('h3', {}, 'Modelo atual: ' + nomeAmigavelModelo(inst.id)),
      h('p', { class: 'sub' }, 'Instalado, sem medição neste protocolo.'),
      h('button', { class: 'btn mini primario', onclick: () => iniciarBench([inst.id], 'padrao') }, 'Medir agora'));
  } else {
    cartaoTitular = h('div', { class: 'vazio' }, 'Nenhum modelo instalado para esta função.');
  }

  // Bloco Desafiante
  let cartaoDesafiante = null;
  const dispensados = obterModelosDispensados();
  if (desaf) {
    const v = desaf.encaixe.variante, pr = desaf.prioridade.pontos;
    const nomeDesaf = nomeAmigavelModelo(desaf.id || desaf.nome);
    const ehDispensado = dispensados.has(desaf.id) || dispensados.has(desaf.nome);
    cartaoDesafiante = h('div', { class: 'cartao' + (ehDispensado ? ' modelo-dispensado' : ''), style: 'border:1px dashed var(--line-strong);display:flex;flex-direction:column;gap:8px' },
      h('div', { class: 'linha' },
        h('div', {},
          h('span', { class: 'sub', style: 'font-size:.76rem;text-transform:uppercase;font-weight:700' }, 'Melhor desafiante que cabe na GPU'),
          h('h3', {}, (ehDispensado ? '⚪ ' : '⚡ ') + nomeDesaf, desaf.novo ? [' ', chip('NOVO', 'novo')] : null, ehDispensado ? [' ', chip('dispensado', 'neutro')] : null)),
        h('span', { class: 'prio', title: desaf.prioridade.razoes.join('\n') }, CHIP_PRIO(), h('span', {}, pr + '/100'))),
      h('div', { class: 'metricas' },
        CHIP_ESTIMADO(),
        h('span', {}, h('b', {}, v.quant), ' · ', fmtGB(v.bytes)),
        h('span', {}, 'contexto até ', h('b', {}, fmtCtx(desaf.encaixe.encaixe.ctx_max))),
        desaf.encaixe.tps_est ? h('span', {}, '~', h('b', {}, fmtTps(desaf.encaixe.tps_est)), ' tok/s') : null),
      h('p', { class: 'sub', style: 'font-size:.82rem;margin:2px 0' }, desaf.prioridade.razoes.slice(0, 2).join(' · ')),
      h('div', { class: 'linha', style: 'justify-content:space-between;margin-top:auto;padding-top:8px;gap:6px;flex-wrap:wrap' },
        h('div', { class: 'linha', style: 'gap:6px' },
          h('button', { class: 'btn primario mini', onclick: () => abrirTeste(desaf.id, p.id) }, 'Testar contra o atual'),
          h('button', { class: 'btn mini', onclick: () => abrirQuants(desaf.id, p.id, S.mesa?.boss?.id) }, 'Outras quants'),
          ...linksDoCandidato(desaf).slice(0, 1)),
        h('button', {
          class: 'btn mini fantasma',
          style: 'color:var(--muted);font-size:.76rem',
          title: ehDispensado ? 'Reativar recomendação deste modelo' : 'Dispensar este modelo (deixar acinzentado)',
          onclick: () => { alternarDispensarModelo(desaf.id); fecharDialogo(); pDecidir(); }
        }, ehDispensado ? '↩ Reativar' : '✕ Dispensar modelo')));
  }

  // Grade lado a lado se ambos existirem
  if (cartaoTitular && cartaoDesafiante) {
    blocos.push(h('div', { class: 'grade g2', style: 'align-items:stretch;margin-bottom:14px' }, cartaoTitular, cartaoDesafiante));
  } else if (cartaoTitular) {
    blocos.push(cartaoTitular);
  } else if (cartaoDesafiante) {
    blocos.push(cartaoDesafiante);
  }

  // Ranking completo
  if (rank.length > 0) {
    blocos.push(h('div', { class: 'cartao flat', style: 'margin-top:6px;padding:0' },
      h('h3', { style: 'margin-bottom:4px' }, `Ranking comparativo (${rank.length} modelos medidos)`),
      h('p', { class: 'sub', style: 'font-size:.8rem' }, 'Margem de erro (IC 90%). Barras que se sobrepõem indicam empate técnico.'),
      h('div', { class: 'empilha', style: 'gap:4px;margin-top:8px' },
        rank.map((x, i) => {
          const nomeL = nomeAmigavelModelo(x.modelo);
          const qL = tagQuantModelo(x.modelo);
          const ehDisp = dispensados.has(x.modelo);
          const titRow = rank.find(r => r.titular);
          let chipVs = null;
          if (x.vs_titular) {
            let txtV = { superior: 'melhor que o atual', inferior: 'pior', empate: 'empate técnico' }[x.vs_titular.veredito];
            let corV = { superior: 'ok', inferior: 'bad', empate: 'neutro' }[x.vs_titular.veredito];
            if (x.vs_titular.veredito === 'empate' && titRow && titRow.tps && x.tps && titRow.tps >= x.tps * 1.35) {
              txtV = `empate em nota (o atual é ${fmtN(titRow.tps / x.tps, 1)}× mais veloz)`;
            }
            chipVs = chip(txtV, corV);
          }
          return h('div', { class: 'rk' + (ehDisp ? ' modelo-dispensado' : ''), title: x.modelo },
            h('div', { class: 'rk-nome' }, i < 3 ? h('span', { class: 'medalha m' + (i + 1), title: (i + 1) + 'º lugar nesta função' }, i + 1) : null, x.titular ? '👑 ' : '', h('b', {}, nomeL), qL ? [' ', h('small', { class: 'sub' }, qL)] : null, x.tps ? [' ', h('small', { class: 'sub', style: 'margin-left:4px' }, `· ${fmtN(x.tps, 0)} t/s`)] : null, ehDisp ? [' ', chip('dispensado', 'neutro')] : null, !x.atende ? chip('sem ' + (p.exige || []).join('/'), 'bad') : null),
            h('div', { class: 'minibarra', title: `nota ${x.nota}` + (x.ic ? ` (IC ${x.ic[0]}–${x.ic[1]})` : '') },
              x.ic ? h('i', { style: `left:${x.ic[0]}%;width:${Math.max(x.ic[1] - x.ic[0], 1)}%` }) : null,
              h('b', { style: `left:calc(${x.nota}% - 1px)` })),
            h('div', { class: 'rk-nota', title: x.indice_pratico ? `Nota: ${x.nota} · Índice Prático (c/ velocidade): ${x.indice_pratico}` : '' }, fmtN(x.nota, 0)),
            chipVs);
        }))));
  }

  abrirDialogo(h('div', { class: 'dlg-in', style: 'max-width:840px' }, ...blocos));
}

// ---------------------------------------------------------------- fixar contexto no Ollama (1 clique)
function fixarContextoDialogo(baseId, ctxSugerido = 16384) {
  const ctxs = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576];
  if (!ctxs.includes(ctxSugerido)) { ctxs.push(ctxSugerido); ctxs.sort((a, b) => a - b); }
  const prefixo = String(baseId).split(':')[0].replace(/[^a-zA-Z0-9._-]+/g, '-');
  const selCtx = h('select', {}, ctxs.map(c => h('option', { value: c, selected: c === ctxSugerido }, `${fmtCtx(c)} (${c} tokens)`)));
  const inpAlias = h('input', { type: 'text', value: `${prefixo}-ctx${fmtCtx(ctxSugerido)}` });
  selCtx.addEventListener('change', () => { inpAlias.value = `${prefixo}-ctx${fmtCtx(Number(selCtx.value))}`; });
  const aviso = h('div');
  const bt = h('button', { class: 'btn primario', onclick: async () => {
    bt.disabled = true;
    try {
      const r = await api('/api/fixar-ctx', { base: baseId, alias: inpAlias.value.trim(), num_ctx: Number(selCtx.value) });
      toast(`✅ Variante criada: ${r.alias} (num_ctx=${r.num_ctx})`);
      fecharDialogo();
      await carregarMesa(); desenhar();
    } catch (e) { bt.disabled = false; aviso.replaceChildren(h('div', { class: 'aviso-caixa' }, e.message)); }
  } }, 'Criar variante no Ollama');
  abrirDialogo(h('div', { class: 'dlg-in' },
    h('h2', {}, 'Fixar contexto seguro no Ollama'),
    h('p', { class: 'sub' }, 'Cria instantaneamente uma tag derivada (sem duplicar os GB do modelo no disco) com o teto de contexto travado para nunca vazar para a RAM do PC.'),
    h('div', { class: 'campos' },
      h('label', { class: 'campo' }, 'Modelo base', h('input', { type: 'text', value: baseId, disabled: true })),
      h('label', { class: 'campo' }, 'Teto de contexto (num_ctx)', selCtx),
      h('label', { class: 'campo' }, 'Nome da nova variante no Ollama', inpAlias)),
    aviso,
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Cancelar'), bt)));
}

function cartaoVeredito(v) {
  const ehDuelo = v.tipo === 'duelo' || !!v.adversario || String(v.id || '').startsWith('duelo-');
  const rec = { promover: ['Vantagem clara', 'ok'], eficiencia: ['Vantagem por eficiência', 'ok'], descartar: ['Inferior', 'bad'], manter: ['Empate técnico', 'warn'] }[v.recomendacao] || ['—', 'neutro'];
  const nomeA = nomeAmigavelModelo(v.candidato?.id || v.candidato?.nome);
  const nomeB = ehDuelo ? nomeAmigavelModelo(v.adversario?.id) : 'Modelos atuais';
  return h('div', { class: 'cartao' },
    h('div', { class: 'linha topo' },
      h('div', { class: 'quebra' },
        h('span', { class: 'kpi-tag' }, ehDuelo ? '⚔ Resultado de Batalha A × B' : '🎯 Testar contra os atuais'),
        h('h3', { style: 'margin-top:2px' }, ehDuelo ? `${nomeA} × ${nomeB}` : v.candidato.nome)),
      chip(rec[0], rec[1])),
    h('p', { style: 'margin-top:8px;font-size:.9rem' }, (v.resumo || '').replaceAll(v.candidato?.id || '__none__', nomeA).replaceAll(v.adversario?.id || '__none__', nomeB)),
    h('div', { class: 'sub' }, `${v.quando.slice(0, 16).replace('T', ' ')} · nível ${v.nivel} · ${fmtGB(v.candidato.bytes)}`),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn primario', onclick: () => abrirVeredito(v) }, ehDuelo ? 'Ver placar A × B' : 'Ver comparação e decidir')));
}

function abrirVeredito(v) {
  const ehDuelo = v.tipo === 'duelo' || !!v.adversario || String(v.id || '').startsWith('duelo-');
  const idA = v.candidato?.id || v.candidato?.nome || 'Modelo A';
  const idB = v.adversario?.id || null;
  const nomeA = nomeAmigavelModelo(idA);
  const nomeB = idB ? nomeAmigavelModelo(idB) : 'Modelo atual';

  const instA = (S.mesa?.instalados || []).find(x => x.id === idA);
  const instB = idB ? (S.mesa?.instalados || []).find(x => x.id === idB) : null;
  const tpsA = v.candidato?.tps || instA?.medido?.tps_mediana;
  const tpsB = v.adversario?.tps || instB?.medido?.tps_mediana;
  const bytesA = v.candidato?.bytes || instA?.bytes;
  const bytesB = v.adversario?.bytes || instB?.bytes;
  const indA = v.candidato?.indice_pratico || instA?.indice_pratico?.total;
  const indB = v.adversario?.indice_pratico || instB?.indice_pratico?.total;

  const linhas = Object.entries(v.por_papel).map(([pid, r]) => {
    const p = papelPorId(pid);
    if (r.nota_novo == null) return h('tr', {}, h('td', {}, p?.icone + ' ' + (p?.rotulo || pid)), h('td', { colspan: 4 }, h('span', { class: 'sub' }, r.motivo || r.veredito)));
    const cor = { superior: 'ok', inferior: 'bad', empate: 'neutro' }[r.veredito];
    const txt = ehDuelo
      ? ({ superior: `${nomeA} venceu`, inferior: `${nomeB} venceu`, empate: 'empate técnico' }[r.veredito] + (r.veredito === 'empate' && r.eficiencia ? ` (${nomeA} mais veloz/leve)` : ''))
      : ({ superior: 'melhor que o atual', inferior: 'pior que o atual', empate: 'empate técnico' }[r.veredito] + (r.eficiencia ? ' (mas menor/mais rápido)' : ''));
    const rotB = ehDuelo ? '' : h('span', { class: 'sub' }, ' (' + nomeAmigavelModelo(r.titular) + ')');
    return h('tr', {},
      h('td', {}, p?.icone + ' ' + (p?.rotulo || pid)),
      h('td', { class: 'num' }, h('b', {}, fmtN(r.nota_novo, 1))),
      h('td', { class: 'num' }, fmtN(r.nota_titular, 1), rotB),
      h('td', { class: 'num' }, (r.dif > 0 ? '+' : '') + fmtN(r.dif, 1), h('div', { class: 'sub' }, `IC ${fmtN(r.ic[0], 1)} a ${fmtN(r.ic[1], 1)}`)),
      h('td', {}, chip(txt, cor), h('div', { class: 'sub' }, `só ${nomeA}: ${r.so_novo} · só ${ehDuelo ? nomeB : 'o atual'}: ${r.so_titular}`)));
  });

  const painelFisicoDuelo = ehDuelo ? h('div', { class: 'duelo-head-vs' },
    h('div', { class: 'duelo-fighter f-a' },
      h('span', { class: 'kpi-tag' }, 'Lutador A'),
      h('h3', {}, nomeA, tagQuantModelo(idA) ? [' ', chip(tagQuantModelo(idA), 'neutro')] : null),
      h('div', { class: 'metricas' },
        indA ? h('span', {}, '⚡ Índice ', h('b', {}, fmtN(indA, 1))) : null,
        tpsA ? h('span', {}, h('b', {}, fmtN(tpsA, 0)), ' tok/s') : null,
        bytesA ? h('span', {}, h('b', {}, fmtGB(bytesA))) : null)),
    h('div', { class: 'duelo-vs-badge' },
      tpsA && tpsB && Math.max(tpsA, tpsB) / Math.min(tpsA, tpsB) >= 1.25
        ? h('div', { style: 'text-align:center' }, h('b', { style: 'font-size:1.1rem;color:var(--ink)' }, 'VS'), h('div', { class: 'chip ok', style: 'margin-top:4px' }, `⚡ ${tpsA > tpsB ? nomeA : nomeB} é ${fmtN(Math.max(tpsA, tpsB) / Math.min(tpsA, tpsB), 1)}× mais rápido`))
        : h('b', { style: 'font-size:1.2rem;color:var(--muted)' }, 'VS')),
    h('div', { class: 'duelo-fighter f-b' },
      h('span', { class: 'kpi-tag' }, 'Lutador B'),
      h('h3', {}, nomeB, tagQuantModelo(idB) ? [' ', chip(tagQuantModelo(idB), 'neutro')] : null),
      h('div', { class: 'metricas' },
        indB ? h('span', {}, '⚡ Índice ', h('b', {}, fmtN(indB, 1))) : null,
        tpsB ? h('span', {}, h('b', {}, fmtN(tpsB, 0)), ' tok/s') : null,
        bytesB ? h('span', {}, h('b', {}, fmtGB(bytesB))) : null))) : null;

  const venceu = Object.values(v.por_papel).some(r => r.veredito === 'superior' || (r.veredito === 'empate' && r.eficiencia));
  const colsCab = ehDuelo ? ['Função', nomeA, nomeB, 'Diferença (A − B)', 'Resultado Pareado'] : ['Função', nomeA + ' (Novo)', 'Modelo atual', 'Diferença', 'Veredito'];

  abrirDialogo(h('div', { class: 'dlg-in', style: 'max-width:860px' },
    h('div', { class: 'linha topo' },
      h('div', {},
        h('span', { class: 'eyebrow-tech' }, ehDuelo ? 'ARENA // BATALHA DIRETA A × B' : 'DESAFIO // CONTRA ESQUADRA TITULAR'),
        h('h2', {}, ehDuelo ? `${nomeA} × ${nomeB}` : `${nomeA} contra os modelos atuais`)),
      h('button', { class: 'btn mini fantasma', onclick: fecharDialogo }, '✕ Fechar')),
    painelFisicoDuelo,
    h('p', {}, (v.resumo || '').replaceAll(idA, nomeA).replaceAll(idB || '__none__', nomeB)),
    h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, colsCab.map((t, i) => h('th', { class: i >= 1 && i <= 3 ? 'num' : '' }, t)))), h('tbody', {}, linhas))),
    h('div', { class: 'info-caixa' }, 'Critério estatístico: uma vitória só é declarada quando o Intervalo de Confiança (IC 90%) da diferença não cruza zero e supera 3 pontos. Quando há empate técnico em conhecimento, a velocidade (tok/s), o tamanho em GB e o teto de contexto na GPU definem o vencedor prático.'),
    v.pendente ? h('div', { class: 'dlg-acoes' },
      h('button', { class: 'btn', onclick: () => resolver(v, 'manter') }, ehDuelo ? 'Concluir e arquivar batalha' : 'Manter os modelos atuais (guardar resultado)'),
      venceu ? h('button', { class: 'btn primario', onclick: () => resolver(v, 'promover') }, ehDuelo ? `Promover ${nomeA} onde venceu` : 'Promover nas funções em que ganhou') : null,
      !ehDuelo ? h('button', { class: 'btn perigo', onclick: () => { if (confirm(`Apagar ${v.candidato.id} do disco (${fmtGB(v.candidato.bytes)})?`)) resolver(v, 'descartar', true); } }, 'Descartar e apagar') : null)
      : h('div', { class: 'sub' }, 'Veredito arquivado (' + (v.resolvido?.acao || 'concluído') + ')'),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
}
async function resolver(v, acao, apagar) {
  try {
    await api('/api/veredito', { id: v.id, acao, confirmar_remocao: !!apagar });
    toast('Feito: ' + acao); fecharDialogo(); await carregarMesa(); desenhar();
  } catch (e) { toast(e.message, 8000); }
}

async function executarAcao(a) {
  try {
    definirMancheteOculta(S.mesa, true);
    if (a.tipo === 'medir') return iniciarBench(a.dados.modelos, 'padrao');
    if (a.tipo === 'testar') return abrirTeste(a.dados.candidato, a.dados.papel);
    if (a.tipo === 'decidir') { const v = S.mesa.vereditos.find(x => x.id === a.dados.veredito); if (v) abrirVeredito(v); return; }
    if (a.tipo === 'radar') return varrer(false);
    if (a.tipo === 'limpar') { document.querySelector('#p-decidir .sec-titulo + .cartao')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  } catch (e) { toast(e.message, 8000); }
}
/* <select> de profundidade com o tempo estimado NA MÁQUINA CONTROLADA; vem marcado o nível que ela aguenta. `pesos` = bytes dos modelos que serão medidos. */
const NOME_NIVEL = { minimo: 'Mínimo', rapido: 'Rápido', padrao: 'Padrão', profundo: 'Profundo' };
const fmtDur = min => min >= 120 ? `~${fmtN(min / 60, 1)} h` : `~${min} min`;
function seletorNivel(pesos) {
  const sel = h('select', {});
  const aviso = h('div', { class: 'sub', style: 'margin-top:4px' });
  let r = null, lista = [], mudou = false;
  const montar = () => {
    const atual = sel.value;
    lista = r?.niveis || ['minimo', 'rapido', 'padrao', 'profundo'].map(id => ({ id }));
    const rec = r?.recomendado || 'padrao';
    sel.replaceChildren(...lista.map(n => h('option', { value: n.id, selected: n.id === (mudou ? atual : rec) },
      `${NOME_NIVEL[n.id]}${n.itens ? ` (${n.itens} itens${n.imagens ? ` + ${n.imagens} imagens` : ''})` : ''}${n.minutos ? ` — ${fmtDur(n.minutos)} estimado` : ''}${n.id === rec && r ? ' · recomendado aqui' : ''}`)));
    atualizar();
  };
  const atualizar = () => {
    const n = lista.find(x => x.id === sel.value);
    aviso.textContent = !r ? '' : (r.sem_gpu ? 'Máquina sem GPU: a CPU gera poucos tokens por segundo, então o tempo cresce rápido com o nível. ' : '')
      + (n && n.minutos > 180 ? '⚠ Mais de 3 h nesta máquina (e ela esquenta): só escolha este nível se for mesmo o que você quer. ' : '')
      + (sel.value === 'minimo' ? 'Poucos itens: serve como sinal de que o modelo funciona, a margem de erro é grande (o painel mostra).' : '');
  };
  sel.addEventListener('change', () => { mudou = true; atualizar(); });
  montar();
  api('/api/bench/niveis?bytes=' + (pesos || []).filter(Boolean).join(',')).then(x => { r = x; montar(); }).catch(() => { /* sem estimativa */ });
  return { sel, aviso };
}
async function iniciarBench(modelos, nivel, modo = 'base', suites, forcado) {
  try { await api('/api/bench', { modelos, nivel, modo, suites, nivel_forcado: forcado || undefined }); toast('Benchmark iniciado: acompanhe na barra de baixo.'); await carregarJobs(); } catch (e) { toast(e.message, 8000); }
}
async function varrer(forcar) {
  try { await api('/api/radar/varrer', { forcar }); toast('Varredura iniciada.'); await carregarJobs(); } catch (e) { toast(e.message, 8000); }
}

// ---------------------------------------------------------------- testar desafiante (com a quantização que a pessoa escolher)
async function abrirTeste(candId, papel, pull, maquinaId) {
  let pl;
  try { pl = await api(`/api/plano?candidato=${encodeURIComponent(candId)}&papel=${encodeURIComponent(papel || '')}` + (pull ? `&pull=${encodeURIComponent(pull)}` : '')); } catch (e) { toast(e.message, 9000); return; }
  const sn = seletorNivel([pl.bytes, pl.bytes]);   // candidato + titular
  const nivel = sn.sel;

  const ok = h('input', { type: 'checkbox', id: 'ck-ok' });
  const ir = h('button', { class: 'btn primario', disabled: true, onclick: async () => {
    try {
      await api('/api/desafio', {
        candidato: candId,
        papel: pl.papel,
        nivel: nivel.value,
        nivel_forcado: true,
        confirmo_download: true,
        pull: pull || undefined
      });
      fecharDialogo();
      toast(`Teste iniciado em ${nomeAlvo()}: acompanhe na barra de tarefas.`);
      await carregarJobs();
    } catch (e) { toast(e.message, 9000); }
  } }, 'Baixar e testar');
  ok.addEventListener('change', () => { ir.disabled = !ok.checked || !pl.cabe_no_disco; });

  abrirDialogo(h('div', { class: 'dlg-in' },
    h('h2', {}, 'Testar ' + pl.candidato), h('p', { class: 'sub' }, 'O teste NÃO troca nada sozinho: no fim você vê a comparação com o modelo atual e decide.'),
    h('dl', { class: 'kv' },
      h('dt', {}, 'Download'), h('dd', {}, `${pl.tamanho} (${pl.quant}) via ${pl.origem}` + (pull ? ' — quantização escolhida por você' : '') + (pl.ja_instalado ? ' — já instalado, só mede' : '')),
      h('dt', {}, 'Comando'), h('dd', {}, h('code', {}, 'ollama pull ' + pl.pull)),
      h('dt', {}, 'Disco livre'), h('dd', {}, (pl.espaco_livre_gb ?? '?') + ' GB ' + (pl.cabe_no_disco ? '✔' : '✖ insuficiente')),
      h('dt', {}, 'Cabe na GPU?'), h('dd', {}, `sim, contexto até ${fmtCtx(pl.encaixe.ctx_max)} (estimado) · usa ~${pl.encaixe.usado_ctx_alvo_gb} GB com ${fmtCtx(pl.encaixe.ctx_alvo)} de contexto`),
      h('dt', {}, 'Função alvo'), h('dd', {}, papelPorId(pl.papel)?.rotulo || pl.papel)),
    pl.aviso ? h('div', { class: 'aviso-caixa' }, pl.aviso) : null,
    h('div', { class: 'info-caixa' }, h('b', {}, 'Roda em: ' + nomeAlvo() + '.'), ' O hardware e o disco dessa máquina é que contam; durante o teste ela fica ocupada. Para testar em outra, troque em “Controlando”.'),
    h('label', { class: 'campo', style: 'margin-top:8px' }, 'Profundidade do teste', nivel), sn.aviso,
    h('label', { class: 'chk' }, ok, ` Entendo: vai baixar ${pl.tamanho} e executar o benchmark.`),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Cancelar'), ir)));
}

/* Instalar = só baixar (sem medir): para quem já decidiu ter o modelo. Mostra tamanho, disco livre e se cabe ANTES, na máquina controlada. */
const nomeAlvo = () => (LI.alvo ? ((S.maquinas?.remotas || []).find(m => m.id === LI.alvo)?.nome || LI.alvo) : 'esta máquina');
async function abrirInstalar(candId, papel, pull) {
  let pl;
  try { pl = await api(`/api/plano?candidato=${encodeURIComponent(candId)}&papel=${encodeURIComponent(papel || '')}` + (pull ? `&pull=${encodeURIComponent(pull)}` : '')); } catch (e) { toast(e.message, 9000); return; }
  const ok = h('input', { type: 'checkbox' });
  const ir = h('button', { class: 'btn primario', disabled: true, onclick: async () => {
    try {
      await api('/api/baixar', { pull: pl.pull, confirmo_download: true, bytes_esperados: pl.bytes });
      fecharDialogo(); toast(`Download iniciado em ${nomeAlvo()}: acompanhe na barra de tarefas. Depois, use “Medir” para dar nota.`, 8000); await carregarJobs();
    } catch (e) { toast(e.message, 9000); }
  } }, 'Baixar');
  ok.addEventListener('change', () => { ir.disabled = !ok.checked || !pl.cabe_no_disco || pl.ja_instalado; });
  abrirDialogo(h('div', { class: 'dlg-in' },
    h('h2', {}, 'Instalar ' + pl.candidato), h('p', { class: 'sub' }, 'Só baixa o modelo. Nada é medido nem trocado: quando quiser saber se ele é melhor, use “Testar contra o modelo atual”.'),
    h('dl', { class: 'kv' },
      h('dt', {}, 'Máquina'), h('dd', {}, nomeAlvo()),
      h('dt', {}, 'Download'), h('dd', {}, `${pl.tamanho} (${pl.quant}) via ${pl.origem}` + (pl.ja_instalado ? ' — já está instalado' : '')),
      h('dt', {}, 'Comando'), h('dd', {}, h('code', {}, 'ollama pull ' + pl.pull)),
      h('dt', {}, 'Disco livre'), h('dd', {}, (pl.espaco_livre_gb ?? '?') + ' GB ' + (pl.cabe_no_disco ? '✔' : '✖ insuficiente')),
      h('dt', {}, 'Cabe na memória?'), h('dd', {}, `sim, contexto até ${fmtCtx(pl.encaixe.ctx_max)} (estimado) · ~${pl.encaixe.usado_ctx_alvo_gb} GB com ${fmtCtx(pl.encaixe.ctx_alvo)} de contexto`)),
    pl.aviso ? h('div', { class: 'aviso-caixa' }, pl.aviso) : null,
    h('label', { class: 'chk' }, ok, ` Entendo: vai baixar ${pl.tamanho} para ${nomeAlvo()}.`),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Cancelar'), ir)));
}

// ---------------------------------------------------------------- aposentar (apagar com registro e herdeiros)
function confirmarAposentar(d) {
  const ok = h('input', { type: 'checkbox' });
  const aviso = h('div');
  const herd = Object.entries(d.herdeiros || {});
  const titDe = S.mesa ? Object.entries(S.mesa.titulares).filter(([, mid]) => mid === d.modelo).map(([pid]) => papelPorId(pid)?.rotulo || pid) : [];
  const bt = h('button', { class: 'btn perigo', disabled: true, onclick: async () => {
    bt.disabled = true;
    try {
      const r = await api('/api/aposentar', { modelo: d.modelo, confirmo: true, herdeiros: d.herdeiros || {}, motivo: d.motivo || 'escolha manual' });
      await carregarMesa(); desenhar();
      abrirDialogo(h('div', { class: 'dlg-in' }, h('h2', {}, '✔ ' + d.modelo + ' aposentado'),
        h('p', {}, `Liberou ${fmtGB(r.liberou_bytes)} do disco.` + (Object.keys(r.herdeiros || {}).length ? ' Usos que mudaram de modelo: ' + Object.entries(r.herdeiros).map(([pid, mid]) => `${papelPorId(pid)?.rotulo} → ${mid}`).join('; ') + '.' : '')),
        h('div', { class: 'info-caixa' }, 'As notas medidas ficam guardadas em ', h('b', {}, 'Meus modelos → Aposentados'), '. Se você baixar o mesmo arquivo de novo, elas voltam a valer sem medir outra vez.'),
        h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: () => { fecharDialogo(); irPara('modelos'); } }, 'Ver em Aposentados'), h('button', { class: 'btn primario', onclick: fecharDialogo }, 'Fechar'))));
    } catch (e) { bt.disabled = false; aviso.replaceChildren(h('div', { class: 'aviso-caixa' }, e.message)); }
  } }, 'Apagar do disco');
  ok.addEventListener('change', () => { bt.disabled = !ok.checked; });
  abrirDialogo(h('div', { class: 'dlg-in' }, h('h2', {}, `Aposentar ${d.modelo}?`),
    d.motivo ? h('p', {}, d.motivo) : null,
    h('dl', { class: 'kv' }, h('dt', {}, 'Libera'), h('dd', {}, d.liberaria || fmtGB(d.bytes)),
      h('dt', {}, 'É o modelo atual de'), h('dd', {}, titDe.length ? titDe.join(', ') : 'nenhuma função'),
      herd.length ? [h('dt', {}, 'Quem assume'), h('dd', {}, herd.map(([pid, mid]) => `${papelPorId(pid)?.rotulo}: ${mid}`).join(' · '))] : null),
    titDe.length && !herd.length ? h('div', { class: 'aviso-caixa' }, 'Sem herdeiro indicado: o painel volta a sugerir o modelo atual pela melhor nota medida entre os que ficam.') : null,
    h('div', { class: 'info-caixa' }, 'Fica registrado (data, tamanho, motivo) e as notas medidas continuam guardadas. Para ter o modelo de volta é preciso baixar de novo — com internet. Se a sua preparação offline depende dele, exporte um kit antes (aba Offline).'),
    h('label', { class: 'chk' }, ok, ' Sei que isso apaga os arquivos do modelo do disco.'), aviso,
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Cancelar'), bt)));
}

// ---------------------------------------------------------------- MEUS MODELOS
function barraSuite(v) {
  return h('div', { class: 'minibarra', title: `${v.acc}% (IC 90%: ${v.ic[0]}–${v.ic[1]}%, n=${v.n})` },
    h('i', { style: `left:${v.ic[0]}%;width:${Math.max(v.ic[1] - v.ic[0], 1)}%` }), h('b', { style: `left:calc(${v.acc}% - 1px)` }));
}

function mediaGeralModelo(x, papeisNota) {
  const med = x.medido?.papeis || {};
  const todos = papeisNota.filter(p => p.id !== 'visao' || (x.caps || []).includes('vision')).map(p => med[p.id]?.nota).filter(v => v != null);
  return todos.length ? todos.reduce((a, b) => a + b, 0) / todos.length : null;
}
function scoreMediaVelocidade(x, papeisNota) {
  if (x.indice_pratico?.total != null) return x.indice_pratico.total;
  const m = mediaGeralModelo(x, papeisNota);
  if (m == null) return -1;
  const tps = x.medido?.tps_mediana || (x.tps_est ? (x.tps_est[0] + x.tps_est[1]) / 2 : 0);
  return m + (tps * 0.04);
}
function pNotaId(med, v) { return v; }
function pNotaAtende() { return true; }

function painelSweetSpot(m, papeisNota) {
  const inst = m.instalados || [];
  if (!inst.length) return h('div', { class: 'vazio' }, 'Instale ao menos um modelo para usar o Mapa de Equilíbrio.');
  const KVS = [
    ['q8_0', 'KV q8_0 (recomendado — metade da VRAM)'],
    ['q4_0', 'KV q4_0 (máximo contexto — 1/4 da VRAM)'],
    ['f16', 'KV f16 (sem quantizar cache)'],
  ];
  const DEGRAUS = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576];
  const E = S.sweetSpot || (S.sweetSpot = { papel: 'geral', kv: 'q8_0', ctxSim: 32768, ord: 'nota', dir: -1 });
  if (!DEGRAUS.includes(E.ctxSim)) E.ctxSim = 32768;
  if (!E.ord) { E.ord = 'nota'; E.dir = -1; }
  const zona = h('div', { class: 'empilha' });
  /* Memória que o modelo pode ocupar NA MÁQUINA CONTROLADA: VRAM se tem GPU; senão RAM menos a reserva do sistema (e o teto por modelo). Nunca 16 GB fixos. */
  const maqMapa = m.boss || {};
  const semGpuMapa = !maqMapa.gpu?.vram_gb;
  const reservaMapa = (S.mesa?.reserva_vram_gb != null && Math.abs(S.mesa.reserva_vram_gb - 1.3) > 1e-9) ? S.mesa.reserva_vram_gb : (maqMapa.reserva_so_gb ?? 1.5);   // “memória livre” definida no painel vale também sem GPU
  const vramTotal = !semGpuMapa ? maqMapa.gpu.vram_gb
    : (maqMapa.ram_gb ? Math.max(0.5, Math.round(Math.min(maqMapa.ram_gb - reservaMapa, maqMapa.max_modelo_gb || 1e9) * 10) / 10) : 16);

  function notaDoModelo(x) {
    if (E.papel === 'geral') return mediaGeralModelo(x, papeisNota);
    return x.medido?.papeis?.[E.papel]?.nota ?? null;
  }

  function dadosNoCtx(x, ctx, kv) {
    const listaKv = x.sonda?.por_kv?.[kv]?.pontos || (kv === 'q8_0' ? (x.sonda?.pontos || []) : []);
    const listaQ8 = x.sonda?.por_kv?.q8_0?.pontos || x.sonda?.pontos || [];
    let pSonda = listaKv.find(p => p.ctx === ctx);
    let interpolado = false;
    // Se pediu 8k e a sonda mediu 4k e 16k, interpola exatamente entre os dois pontos reais
    if (!pSonda && ctx === 8192) {
      const p4 = listaKv.find(p => p.ctx === 4096 && p.ok !== false);
      const p16 = listaKv.find(p => p.ctx === 16384 && p.ok !== false);
      if (p4 && p16) {
        const frac = (8192 - 4096) / (16384 - 4096);
        pSonda = {
          ctx: 8192,
          ok: true,
          total_bytes: p4.total_bytes + frac * (p16.total_bytes - p4.total_bytes),
          vram_gpu_real_bytes: (p4.vram_gpu_real_bytes && p16.vram_gpu_real_bytes)
            ? p4.vram_gpu_real_bytes + frac * (p16.vram_gpu_real_bytes - p4.vram_gpu_real_bytes)
            : null,
          gpu_integral: p4.gpu_integral && p16.gpu_integral,
          tps: p4.tps && p16.tps ? Math.round((p4.tps + p16.tps) / 2 * 10) / 10 : (p4.tps || p16.tps)
        };
        interpolado = true;
      }
    }

    // Se algum contexto menor ou igual na sonda deste KV já vazou para a RAM / deu timeout, contextos maiores também vazam!
    const pontoEstourouAntes = listaKv.find(p => p.ctx <= ctx && (
      p.ok === false || p.estourou_ram ||
      (!semGpuMapa && (p.ram_wddm || p.gpu_integral === false || (p.vram_gpu_real_bytes && p.vram_gpu_real_bytes / 1e9 >= vramTotal - 0.10)))
    ));
    const p4kKv = listaKv.find(p => p.ctx === 4096 && p.ok !== false);
    const pQ8MesmoCtx = listaQ8.find(p => p.ctx === ctx && p.ok !== false && p.gpu_integral);
    const tpsBase4k = p4kKv?.tps || listaQ8.find(p => p.ctx === 4096)?.tps || x.medido?.tps_mediana || null;

    const est = x.ctx_por_kv?.[kv]?.por_ctx?.[String(ctx)];
    const orc = x.ctx_por_kv?.[kv]?.orcamento_gb || (vramTotal - 1.3);
    const pesoDiscoGb = x.bytes / 1e9;
    let pesoGb = pesoDiscoGb;
    let modeloKvGb, totalGpuGb, sysGb, folgaGpuGb, cabe, medido = false;
    let ramWddm = false, erroSonda = null;
    let tps = x.medido?.tps_mediana || (x.tps_est ? (x.tps_est[0] + x.tps_est[1]) / 2 : null);

    const resVramGb = S.mesa?.reserva_vram_gb != null ? S.mesa.reserva_vram_gb : 1.3;
    const cudaOverheadGb = S.mesa?.overhead_cuda_gb != null ? S.mesa.overhead_cuda_gb : 0.85;
    const sysBaseGb = semGpuMapa ? 0.3 : resVramGb + cudaOverheadGb;

    if (pSonda && pSonda.ok !== false && pSonda.total_bytes) {
      cabe = semGpuMapa ? (pSonda.total_bytes / 1e9 <= vramTotal + 0.1) : (!!pSonda.gpu_integral && !pSonda.ram_wddm);   // sem GPU: cabe = coube na RAM reservada
      ramWddm = !!pSonda.ram_wddm;
      medido = true;
      if (pSonda.tps) tps = pSonda.tps;
      if (listaKv.length && listaKv[0].total_bytes) {
        pesoGb = Math.min(pesoDiscoGb, (listaKv[0].total_bytes / 1e9) - 0.15);
      }
      modeloKvGb = pSonda.vram_modelo_bytes ? (pSonda.vram_modelo_bytes / 1e9) : (pSonda.total_bytes / 1e9);
      if (pSonda.vram_gpu_real_bytes) {
        totalGpuGb = pSonda.vram_gpu_real_bytes / 1e9;
        sysGb = Math.max(0, totalGpuGb - modeloKvGb);
        folgaGpuGb = pSonda.vram_gpu_livre_bytes != null ? (pSonda.vram_gpu_livre_bytes / 1e9) : Math.max(0, vramTotal - totalGpuGb);
      } else {
        sysGb = sysBaseGb;
        totalGpuGb = Math.min(vramTotal, modeloKvGb + sysGb);
        folgaGpuGb = Math.max(0, vramTotal - totalGpuGb);
      }

      // Detecção de estouro físico e paginação WDDM na RAM:
      // 1. Total físico medido na placa iguala ou supera o teto de VRAM do hardware (ex.: 16,2G em placa de 16G!)
      // 2. Saturação crítica (>= 97% da VRAM) com folga física exígua (< 0.70 GB)
      // 3. Queda severa de velocidade / leitura típica de paginação WDDM via PCIe
      const estourouCapacidade = totalGpuGb >= (vramTotal - 0.10);
      const saturacaoCritica = totalGpuGb >= (vramTotal * 0.97) && folgaGpuGb < 0.70;
      const quedaSevera = tpsBase4k && tps && (tps < tpsBase4k * 0.56 || (tpsBase4k >= 25 && tps <= 14)) && (folgaGpuGb < 0.7 || ctx >= 65536);

      if (!semGpuMapa && cabe && ctx > 4096 && (estourouCapacidade || saturacaoCritica || quedaSevera)) {
        cabe = false;
        ramWddm = true;
      }
    } else if ((pSonda && pSonda.ok === false) || pontoEstourouAntes) {
      medido = true;
      cabe = false;
      ramWddm = true;
      erroSonda = pSonda?.erro || pontoEstourouAntes?.erro || 'Estourou VRAM e paginou na RAM do sistema';
      modeloKvGb = est?.total_gb || (pesoGb + 2.5);
      sysGb = sysBaseGb;
      totalGpuGb = Math.max(vramTotal, est?.vram_gpu_est_gb || (modeloKvGb + sysGb));
      folgaGpuGb = 0;
      if (pontoEstourouAntes?.tps) tps = pontoEstourouAntes.tps;
    } else if (est) {
      modeloKvGb = est.total_gb;
      sysGb = sysBaseGb;
      totalGpuGb = semGpuMapa ? modeloKvGb + sysGb : (est.vram_gpu_est_gb || (modeloKvGb + sysGb));
      folgaGpuGb = semGpuMapa ? Math.max(0, vramTotal - totalGpuGb) : (est.folga_gpu_real_gb != null ? est.folga_gpu_real_gb : Math.max(0, vramTotal - totalGpuGb));
      cabe = est.cabe;
    } else {
      modeloKvGb = pesoGb + 0.5;
      sysGb = sysBaseGb;
      totalGpuGb = modeloKvGb + sysGb;
      folgaGpuGb = Math.max(0, vramTotal - totalGpuGb);
      cabe = modeloKvGb <= orc;
    }

    // Alerta quando o KV (especialmente q4_0 ou contexto alto) derruba muito a velocidade e não compensa
    let lentoNaoCompensa = false;
    let motivoLento = null;
    if (medido && cabe && tps) {
      const tpsQ8 = pQ8MesmoCtx?.tps;
      if (kv === 'q4_0' && tpsQ8 && tps < tpsQ8 * 0.80) {
        lentoNaoCompensa = true;
        const pctQueda = Math.round((1 - tps / tpsQ8) * 100);
        motivoLento = `KV q4_0 ficou ${pctQueda}% mais lento que q8_0 neste contexto (${fmtN(tps, 0)} vs ${fmtN(tpsQ8, 0)} tok/s) — como q8_0 já cabe na GPU, q4_0 não compensa aqui.`;
      } else if (tpsBase4k && tps < tpsBase4k * 0.68) {
        lentoNaoCompensa = true;
        const pctQueda = Math.round((1 - tps / tpsBase4k) * 100);
        motivoLento = `Velocidade caiu ${pctQueda}% em relação ao contexto base (${fmtN(tps, 0)} vs ${fmtN(tpsBase4k, 0)} tok/s) — talvez não compense o uso mais lento nesta janela.`;
      }
    }

    const kvGb = Math.max(0.1, modeloKvGb - pesoGb);
    const noLimite = medido && cabe && folgaGpuGb < (semGpuMapa ? 0.15 : 1.0);
    const totalGb = totalGpuGb;
    const folgaGb = folgaGpuGb;

    return {
      totalGb, totalGpuGb, modeloKvGb, pesoGb, kvGb, sysGb, folgaGb, folgaGpuGb,
      orc, cabe, medido, interpolado, noLimite, tps, tpsBase4k,
      ramWddm, erroSonda, lentoNaoCompensa, motivoLento
    };
  }

  function escolherPerfis(avaliados) {
    const cabem = avaliados.filter(a => a.sim.cabe);
    const base = cabem.length ? cabem : avaliados;
    // 1. Mais Capaz no contexto escolhido: maior nota (desempate por porte)
    const maisCapaz = [...base].sort((a, b) => ((b.nota ?? 0) - (a.nota ?? 0)) || (b.x.bytes - a.x.bytes))[0] || null;
    // 2. Melhor Equilíbrio (Sweet Spot): ocupa <= 82% da VRAM total real na placa (ex.: <= 13.1 GB em 16 GB, como gemma4:12b ou qwen3.5:9b),
    // deixando folga segura na GPU para o sistema e tarefas, mantendo nota alta (>= 90% da melhor nota).
    const maxNota = maisCapaz?.nota || 85;
    const candidatosEquil = base.filter(a => a.sim.totalGpuGb <= vramTotal * 0.82 && (a.nota == null || a.nota >= maxNota - 10));
    const equilibrado = candidatosEquil.length
      ? [...candidatosEquil].sort((a, b) => {
          const scoreA = (a.nota ?? 75) + (a.sim.folgaGpuGb * 1.5);
          const scoreB = (b.nota ?? 75) + (b.sim.folgaGpuGb * 1.5);
          return scoreB - scoreA;
        })[0]
      : [...base].filter(a => !maisCapaz || a.x.id !== maisCapaz.x.id).sort((a, b) => (b.sim.tps || 0) - (a.sim.tps || 0))[0] || maisCapaz;
    // 3. Mais Veloz / Leve: menor uso de VRAM ou maior tok/s
    const maisVeloz = [...base].filter(a => a.x.id !== maisCapaz?.x.id && a.x.id !== equilibrado?.x.id)
      .sort((a, b) => ((b.sim.tps || 0) - (a.sim.tps || 0)) || (a.x.bytes - b.x.bytes))[0]
      || [...base].sort((a, b) => (b.sim.tps || 0) - (a.sim.tps || 0))[0] || null;
    return { maisCapaz, equilibrado, maisVeloz };
  }

  function desenhar() {
    const avaliados = inst.map(x => {
      const nota = notaDoModelo(x);
      const sim = dadosNoCtx(x, E.ctxSim, E.kv);
      const ctxMaxEst = x.ctx_por_kv?.[E.kv]?.ctx_max || 32768;
      const ctxMaxSonda = x.sonda?.por_kv?.[E.kv]?.ctx_max_gpu ?? (E.kv === 'q8_0' ? (x.sonda?.ctx_max_gpu || 0) : 0);
      return { x, nota, sim, ctxMax: Math.max(ctxMaxEst, ctxMaxSonda), ctxMaxSonda };
    }).sort((a, b) => {
      let va, vb;
      if (E.ord === 'nome') return E.dir * a.x.id.localeCompare(b.x.id);
      if (E.ord === 'vram') { va = a.sim.totalGpuGb; vb = b.sim.totalGpuGb; }
      else if (E.ord === 'tps') { va = a.sim.tps ?? -1; vb = b.sim.tps ?? -1; }
      else { va = a.nota ?? -1; vb = b.nota ?? -1; }
      return E.dir * (va - vb);
    });

    const { maisCapaz, equilibrado, maisVeloz } = escolherPerfis(avaliados);
    const ordenarMatriz = col => {
      if (E.ord === col) E.dir = -E.dir;
      else { E.ord = col; E.dir = col === 'vram' ? 1 : -1; }
      desenhar();
    };
    const setaM = col => E.ord === col ? (E.dir === -1 ? ' ↓' : ' ↑') : '';

    // Simulador de Ocupação de VRAM em tempo real + Matriz de Contexto (4k -> 256k)
    const linhasMatriz = avaliados.map(item => {
      const x = item.x, s = item.sim;
      const pctPeso = Math.min(100, (s.pesoGb / vramTotal) * 100);
      const pctKv = Math.min(100 - pctPeso, (s.kvGb / vramTotal) * 100);
      const pctSys = Math.min(100 - pctPeso - pctKv, (s.sysGb / vramTotal) * 100);
      const ehEquil = equilibrado && equilibrado.x.id === x.id;
      const ehCapaz = maisCapaz && maisCapaz.x.id === x.id && (!ehEquil);

      const tetoNativo = x.sonda?.teto_nativo || x.ctx_max || x.arch?.ctx_max || 262144;
      const celulasCtx = DEGRAUS.map(c => {
        const d = dadosNoCtx(x, c, E.kv);
        const sel = c === E.ctxSim ? ' sel' : '';
        const clicarCtx = () => { E.ctxSim = c; atualizarTudo(); };
        if (c > tetoNativo && !d.medido) {
          return h('td', {
            class: 'sw-cell' + sel,
            style: 'cursor:pointer;opacity:0.62;border-style:dashed',
            onclick: clicarCtx,
            title: `Acima do Teto Nativo GGUF (${fmtCtx(tetoNativo)}):\n` +
              `• O Ollama trava num_ctx em ${fmtCtx(tetoNativo)} por padrão (por isso a VRAM não muda acima de ${fmtCtx(tetoNativo)}).\n` +
              `• Projeção teórica (caso extrapolado via YaRN no LM Studio/llama.cpp): ~${fmtN(d.totalGpuGb, 1)} GB na placa (${d.cabe ? 'caberia na GPU' : 'vazaria para RAM'}).`
          },
            h('b', { style: 'font-size:0.74rem;color:var(--muted)' }, `Teto ${fmtCtx(tetoNativo)}`),
            h('small', {}, `~${fmtN(d.totalGpuGb, 1)}G est`));
        }
        if (!d.cabe) {
          const ttlRam = d.medido
            ? `ESTOURO DE VRAM (Uso de RAM detectado em ${fmtCtx(c)}):\n` +
              (d.ramWddm
                ? `• Consumo físico total de ${fmtN(d.totalGpuGb, 1)} GB atingiu ou excedeu a capacidade física da GPU (${vramTotal} GB) e o driver paginou na Memória RAM compartilhada (WDDM).\n` +
                  (d.tps && d.tpsBase4k && d.tps < d.tpsBase4k * 0.7 ? `• Queda drástica de velocidade: despencou de ${fmtN(d.tpsBase4k, 0)} tok/s para ${fmtN(d.tps, 1)} tok/s!\n` : '') +
                  (d.erroSonda ? `• Detalhe: ${d.erroSonda}\n` : '')
                : `• ${semGpuMapa ? 'Não cabe na memória reservada a modelos' : 'Parte do modelo/contexto vazou para a RAM do sistema'} (${fmtN(d.totalGpuGb, 1)} GB exigidos para ${vramTotal} GB disponíveis).\n`) +
              `• Recomendação: reduza o contexto ou use KV q8_0 / q4_0.`
            : (semGpuMapa ? `Em ${fmtCtx(c)} precisaria de ~${fmtN(d.totalGpuGb, 1)} GB de RAM, e esta máquina reserva ${vramTotal} GB para modelo: não cabe (o sistema usaria swap e travaria).` : `Em ${fmtCtx(c)} precisaria de ~${fmtN(d.totalGpuGb, 1)} GB na placa (estoura os ${vramTotal} GB e usa RAM do PC, ficando muito lento).`);
          return h('td', {
            class: 'sw-cell out' + sel,
            style: 'cursor:pointer',
            onclick: clicarCtx,
            title: ttlRam
          },
            h('b', {}, semGpuMapa ? '✖ não cabe' : '⚠ RAM'),
            d.medido && d.tps ? h('small', { style: 'display:block;font-size:.66rem;opacity:.9' }, `${fmtN(d.tps, 0)} t/s`) : null);
        }
        return h('td', {
          class: 'sw-cell ' + (d.medido ? 'med' : 'est') + (d.lentoNaoCompensa ? ' sw-lento' : '') + sel,
          style: 'cursor:pointer' + (d.lentoNaoCompensa ? ';border-color:rgba(217,119,6,.75);background:rgba(245,158,11,.10)' : (d.noLimite ? ';border-color:rgba(217,119,6,.45)' : '')),
          onclick: clicarCtx,
          title: d.medido
            ? `MEDIDO na GPU (igual Gerenciador de Tarefas) em ${fmtCtx(c)}:\n` +
              `• Total na Placa: ${fmtN(d.totalGpuGb, 1)} GB de ${vramTotal} GB\n` +
              `• Modelo + KV: ${fmtN(d.modeloKvGb, 1)} GB (${fmtN(d.pesoGb, 1)}G pesos + ${fmtN(d.kvGb, 1)}G KV)\n` +
              `• Windows + CUDA: ${fmtN(d.sysGb, 1)} GB\n` +
              `• Velocidade: ${d.tps} tok/s\n` +
              `• Folga física: ${fmtN(d.folgaGpuGb, 1)} GB livres` + (d.noLimite ? ' (⚠ no limite físico da VRAM!)' : '') +
              (d.lentoNaoCompensa ? `\n\n🐢 ALERTA DE LENTIDÃO:\n• ${d.motivoLento}` : '')
            : `ESTIMADO na GPU em ${fmtCtx(c)}:\n` +
              `• Total na Placa: ~${fmtN(d.totalGpuGb, 1)} GB\n` +
              `• Modelo + KV: ~${fmtN(d.modeloKvGb, 1)} GB`
        },
          h('b', {}, fmtN(d.totalGpuGb, 1) + 'G'),
          h('small', { style: d.lentoNaoCompensa ? 'color:var(--warn);font-weight:700' : '' },
            d.medido
              ? (d.tps ? fmtN(d.tps, 0) + ' t/s ' + (d.lentoNaoCompensa ? '🐢' : (d.noLimite ? '⚠' : '✔')) : '✔ GPU')
              : '~est'));
      });

      const nomeL = nomeAmigavelModelo(x.id);
      const qL = tagQuantModelo(x.id);
      return h('tr', { class: ehEquil ? 'destaque' : '' },
        h('td', {},
          h('div', { class: 'linha', style: 'justify-content:flex-start;gap:6px' },
            h('b', { title: x.id }, nomeL),
            ehEquil ? chip('⚖ Equilíbrio', 'ok') : null,
            ehCapaz ? chip('🧠 Mais Capaz', 'estimado') : null),
          h('div', { class: 'sub' }, `${qL ? qL + ' · ' : ''}${fmtGB(x.bytes)} · ${s.tps ? fmtN(s.tps, 0) + ' tok/s' : ''}`)),
        h('td', { class: 'num' }, item.nota != null ? h('span', { class: 'nota ' + notaClasse(item.nota) }, h('b', { style: 'font-size:1.02rem' }, fmtN(item.nota, 1))) : '—'),
        h('td', { style: 'width:140px;min-width:110px' },
          h('div', { class: 'sw-vram-bar', title: `${semGpuMapa ? 'Na RAM reservada a modelos' : 'Na Placa (Gerenciador de Tarefas)'}: ${fmtN(s.totalGpuGb, 1)} GB de ${vramTotal} GB\n· Pesos do modelo: ${fmtN(s.pesoGb, 1)} GB\n· Contexto/KV (${fmtCtx(E.ctxSim)}, ${E.kv}): ${fmtN(s.kvGb, 1)} GB\n· ${semGpuMapa ? 'Runtime do Ollama' : 'Windows + CUDA runtime'}: ${fmtN(s.sysGb, 1)} GB\n· Folga ${semGpuMapa ? 'na RAM' : 'física real na GPU'}: ${fmtN(s.folgaGpuGb, 1)} GB livres` },
            h('span', { class: 'p-peso', style: `width:${pctPeso.toFixed(1)}%` }),
            h('span', { class: 'p-kv' + (s.cabe ? '' : ' p-over'), style: `width:${pctKv.toFixed(1)}%` }),
            h('span', { class: 'p-sys', style: `width:${pctSys.toFixed(1)}%` })),
          h('div', { class: 'sw-vram-leg' },
            h('span', {}, h('b', {}, fmtN(s.totalGpuGb, 1) + 'G'), ` / ${vramTotal}G`),
            h('span', { class: s.cabe ? (s.noLimite ? 'sub' : 'ok-txt') : 'bad-txt' }, s.cabe ? (s.noLimite ? `⚠ ${fmtN(s.folgaGpuGb, 1)}G` : `livre ${fmtN(s.folgaGpuGb, 1)}G`) : (semGpuMapa ? 'não cabe' : 'RAM'))),
          h('div', { class: 'sub', style: 'font-size:0.68rem;text-align:right;margin-top:1px;opacity:0.75' }, `${fmtN(s.modeloKvGb, 1)}G mod+kv`)),
        ...celulasCtx,
        h('td', {},
          h('div', { class: 'linha', style: 'justify-content:flex-end;gap:4px;flex-wrap:nowrap' },
            h('button', { class: 'btn mini', title: `Sondar na prática na GPU com KV ${E.kv} até 512k / 1M`, onclick: async () => {
              try { await api('/api/sonda', { modelos: [x.id], ate_ctx: 1048576, kv_cache: E.kv }); toast(`Sonda (${E.kv}) até 1M iniciada para ${nomeAmigavelModelo(x.id)}.`); await carregarJobs(); } catch (e) { toast(e.message, 8000); }
            } }, item.ctxMaxSonda >= 65536 ? `Ressondar` : `Sondar`),
            h('button', { class: 'btn mini', onclick: () => fixarContextoDialogo(x.id, E.ctxSim) }, `Fixar`))));
    });

    const segCtx = h('div', { class: 'seg', role: 'group' }, DEGRAUS.map(c =>
      h('button', { 'aria-pressed': String(E.ctxSim === c), onclick: () => { E.ctxSim = c; desenhar(); } }, fmtCtx(c))));

    zona.replaceChildren(
      semGpuMapa && maqMapa.ram_gb ? h('div', { class: 'info-caixa', style: 'margin-bottom:8px' },
        h('b', {}, `${vramTotal} GB para modelo`), ` = RAM total ${maqMapa.ram_gb} GB − ${reservaMapa} GB reservados ao sistema e aos outros serviços da máquina` +
        (maqMapa.max_modelo_gb && maqMapa.max_modelo_gb < maqMapa.ram_gb - reservaMapa + 0.01 ? `, limitado ao teto de ${maqMapa.max_modelo_gb} GB por modelo (regra do parque contra swap). ` : '. ') +
        'Os números da máquina ficam em parque/parque.json.') : null,
      h('div', { class: 'tabela-wrap' },
        h('table', { class: 'sw-matrix tabela-compacta' },
          h('thead', {}, h('tr', {},
            h('th', { style: 'cursor:pointer;user-select:none', onclick: () => ordenarMatriz('nome'), title: 'Clique para ordenar por nome' }, 'Modelo instalado' + setaM('nome')),
            h('th', { class: 'num', style: 'cursor:pointer;user-select:none', onclick: () => ordenarMatriz('nota'), title: 'Clique para ordenar pela nota' }, (E.papel === 'geral' ? 'Nota Média' : (papelPorId(E.papel)?.rotulo || 'Nota')) + setaM('nota')),
            h('th', { style: 'cursor:pointer;user-select:none;width:140px', onclick: () => ordenarMatriz('vram'), title: 'Uso total de VRAM na placa física (idêntico ao Gerenciador de Tarefas do Windows: Modelo + KV + CUDA + Sistema)' }, `${semGpuMapa ? 'Uso RAM' : 'Uso GPU'} (${vramTotal}G)` + setaM('vram')),
            ...DEGRAUS.map(c => h('th', { class: 'sw-th-ctx' + (c === E.ctxSim ? ' sel' : ''), onclick: () => { E.ctxSim = c; atualizarTudo(); }, title: 'Clique para simular este contexto' }, fmtCtx(c))),
            h('th', {}, ''))),
          h('tbody', {}, linhasMatriz))),
      h('div', { class: 'legenda' },
        h('span', {}, h('span', { style: 'color:#3b66e6' }, '■ '), 'Pesos do modelo (GB)'),
        h('span', {}, h('span', { style: 'color:#8b5cf6' }, '■ '), `Cache de contexto KV (${E.kv})`),
        h('span', {}, h('span', { style: 'color:rgba(148,163,184,0.7)' }, '■ '), 'Windows + CUDA runtime'),
        h('span', {}, h('b', {}, '✔ '), 'Medido na Sonda física na GPU'),
        h('span', {}, h('b', { style: 'color:var(--warn)' }, '🐢 '), 'Velocidade caiu muito (não compensa usar este KV/contexto)'),
        h('span', {}, h('b', { style: 'color:var(--bad)' }, '⚠ RAM '), 'Estourou a VRAM (paginou na RAM do Windows / muito lento)'),
        h('span', {}, h('b', {}, '~est '), 'Estimado pela arquitetura do modelo')));
  }

  const selPapel = h('select', { onchange: ev => { E.papel = ev.target.value; desenhar(); } },
    h('option', { value: 'geral', selected: E.papel === 'geral' }, '⭐ Média geral de todas as funções'),
    papeisNota.map(p => h('option', { value: p.id, selected: p.id === E.papel }, `${p.icone} ${p.rotulo}`)));
  const selKv = h('select', { onchange: ev => { E.kv = ev.target.value; desenhar(); } },
    KVS.map(([id, rot]) => h('option', { value: id, selected: id === E.kv }, rot)));

  const barraTopo = () => {
    const segCtx = h('div', { class: 'seg' }, DEGRAUS.map(c =>
      h('button', { 'aria-pressed': String(E.ctxSim === c), onclick: () => { E.ctxSim = c; atualizarTudo(); } }, fmtCtx(c))));
    return h('div', { class: 'filtros', style: 'margin:0;justify-content:space-between' },
      h('div', { class: 'linha', style: 'gap:12px' },
        h('label', { class: 'campo' }, 'Função avaliada', selPapel),
        h('label', { class: 'campo' }, 'Quantização do Cache KV', selKv)),
      h('div', { class: 'campo', style: 'display:flex;flex-direction:column;gap:3px;font-size:.76rem;color:var(--muted);font-weight:600' }, 'Simular janela de contexto na GPU', segCtx));
  };

  const wrapTopo = h('div');
  function atualizarTudo() {
    wrapTopo.replaceChildren(barraTopo());
    desenhar();
  }
  atualizarTudo();
  return h('div', { class: 'cartao empilha' }, wrapTopo, zona);
}

async function iniciarDueloRapido(va, vb, papel = 'chat_pt', nivel = 'padrao') {
  try {
    await api('/api/duelo', { a: va, b: vb, papel, nivel, confirmo_download: true });
    toast(`⚔ Duelo iniciado: ${va} × ${vb}. Acompanhe na barra inferior.`);
    await carregarJobs();
  } catch (e) { toast(e.message, 9000); }
}

async function pModelos() {
  const m = S.mesa, raiz = $('#p-modelos');
  if (window.LI_PUBLIC_MODE) { paginaPrevia('modelos', raiz); return; }
  if (!m) return;
  const papeisNota = m.papeis.filter(p => !p.sem_nota);
  const ordPlacar = S.ordPlacar || (S.ordPlacar = { col: 'indice', dir: -1 });
  const ordenarPlacar = col => {
    if (ordPlacar.col === col) ordPlacar.dir = -ordPlacar.dir;
    else { ordPlacar.col = col; ordPlacar.dir = col === 'bytes' || col === 'nome' ? 1 : -1; }
    pModelos();
  };
  const setaP = col => ordPlacar.col === col ? (ordPlacar.dir === -1 ? ' ↓' : ' ↑') : '';

  const listaInstalados = [...(m.instalados || [])];
  listaInstalados.sort((a, b) => {
    if (ordPlacar.col === 'nome') return ordPlacar.dir * a.id.localeCompare(b.id);
    let va, vb;
    if (ordPlacar.col === 'bytes') { va = a.bytes || 0; vb = b.bytes || 0; }
    else if (ordPlacar.col === 'ctx') {
      va = a.sonda?.ctx_max_gpu || a.ctx_por_kv?.q8_0?.ctx_max || 0;
      vb = b.sonda?.ctx_max_gpu || b.ctx_por_kv?.q8_0?.ctx_max || 0;
    } else if (ordPlacar.col === 'tps') {
      va = a.medido?.tps_mediana ?? -1;
      vb = b.medido?.tps_mediana ?? -1;
    } else if (ordPlacar.col === 'indice' || ordPlacar.col === 'padrao') {
      va = scoreMediaVelocidade(a, papeisNota);
      vb = scoreMediaVelocidade(b, papeisNota);
    } else if (ordPlacar.col === 'media') {
      va = mediaGeralModelo(a, papeisNota) ?? -1;
      vb = mediaGeralModelo(b, papeisNota) ?? -1;
    } else {
      va = a.medido?.papeis?.[ordPlacar.col]?.nota ?? -1;
      vb = b.medido?.papeis?.[ordPlacar.col]?.nota ?? -1;
    }
    return ordPlacar.dir * (va - vb);
  });

  const mantidosPlacar = obterModelosMantidos();
  const linhas = [];
  for (const x of listaInstalados) {
    const med = x.medido;
    const disp = m.dispensaveis.find(d => d.modelo === x.id);
    const ehMantido = mantidosPlacar.has(x.id);
    const ctxQ8 = x.ctx_por_kv?.q8_0?.ctx_max;
    const nomeLimpo = nomeAmigavelModelo(x.id);
    const quantLimpa = tagQuantModelo(x.id);
    const media = mediaGeralModelo(x, papeisNota);
    const ip = x.indice_pratico;
    const scorePond = ip?.total ?? scoreMediaVelocidade(x, papeisNota);
    const tpsMed = x.medido?.tps_mediana || (x.tps_est ? (x.tps_est[0] + x.tps_est[1]) / 2 : null);
    const nomeSub = disp?.substituto ? nomeAmigavelModelo(disp.substituto) : null;
    linhas.push(h('tr', {},
      h('td', {},
        h('b', { title: x.id }, nomeLimpo),
        disp && !ehMantido ? [' ', chip(nomeSub ? `coberto por ${nomeSub}` : 'pode sair', 'warn', disp.motivo)] : null,
        disp && ehMantido ? [' ', chip('✓ mantido por você', 'ok', 'Você optou por continuar com este modelo')] : null,
        h('div', { class: 'sub' }, `${quantLimpa || x.quant || ''} ${x.params ? '· ' + x.params : ''}`)),
      h('td', { class: 'num' }, fmtGB(x.bytes)),
      h('td', {}, h('div', { class: 'chips' }, (x.caps || []).filter(c => c !== 'completion').map(c => chip(c, 'neutro')))),
      h('td', { class: 'num' }, x.sonda?.ctx_max_gpu ? h('span', { title: 'Medido na Sonda 100% na GPU' }, fmtCtx(x.sonda.ctx_max_gpu), ' ✔') : (ctxQ8 ? h('span', { class: 'sub', title: 'Estimado com KV q8_0' }, '~' + fmtCtx(ctxQ8)) : '—')),
      h('td', { class: 'num' }, med?.tps_mediana ? fmtN(med.tps_mediana, 0) : '—'),
      h('td', { class: 'num' }, scorePond < 0 ? '—' : h('span', {
        class: 'nota ' + notaClasse(scorePond),
        title: ip
          ? `Índice Global Multicritério: ${fmtN(ip.total, 1)} / 100\n` +
            `• Conhecimento (64%): ${fmtN(ip.conhecimento, 1)} pts\n` +
            `• Velocidade (18%): ${fmtN(ip.velocidade, 0)} pts (${ip.tps} tok/s)\n` +
            `• Eficiência de Tamanho (9%): ${fmtN(ip.tamanho, 0)} pts (${ip.peso_gb} GB)\n` +
            `• Contexto GPU (9%): ${fmtN(ip.contexto, 0)} pts (${fmtCtx(ip.ctx_gpu)})`
          : `Score combinado: ${fmtN(scorePond, 1)}`
      }, h('b', { style: 'font-size:1.04rem' }, fmtN(scorePond, 1)))),
      h('td', { class: 'num' }, media == null ? '—' : h('span', {
        class: 'sub',
        style: 'font-weight:700;color:var(--ink)',
        title: `Média pura de conhecimento: ${fmtN(media, 1)} de 100`
      }, fmtN(media, 1))),
      ...papeisNota.map(p => { const n = med?.papeis?.[p.id]?.nota; return h('td', { class: 'num' }, n == null ? '—' : h('span', { class: 'nota ' + notaClasse(n) }, h('b', { style: 'font-size:1rem' }, fmtN(n, 0)))); }),
      h('td', {}, h('div', { class: 'linha', style: 'justify-content:flex-end;gap:4px;flex-wrap:nowrap' },
        h('button', { class: 'btn mini', title: 'Ver detalhes e medições completas', onclick: () => detalheModelo(x.id) }, 'Detalhes'),
        h('button', { class: 'btn mini', title: 'Executar ollama pull para verificar e baixar versão mais nova desta tag', onclick: () => atualizarModelosInstalados([x.id]) }, '↻'),
        h('button', { class: 'btn mini', title: 'Sondar VRAM e contexto até 1M', onclick: async () => { try { await api('/api/sonda', { modelos: [x.id], ate_ctx: 1048576, kv_cache: S.sweetSpot?.kv || 'q8_0' }); toast('Sonda iniciada até 1M.'); await carregarJobs(); } catch (e) { toast(e.message, 8000); } } }, 'Sonda'),
        h('button', { class: 'btn mini', title: 'Fixar contexto no Ollama', onclick: () => fixarContextoDialogo(x.id, x.sonda?.ctx_max_gpu || ctxQ8 || 16384) }, 'Fixar'),
        h('button', { class: 'btn mini perigo', title: 'Aposentar e apagar do disco', onclick: () => confirmarAposentar({ modelo: x.id, bytes: x.bytes, liberaria: fmtGB(x.bytes), herdeiros: disp?.herdeiros || {}, motivo: disp?.motivo || 'escolha manual' }) }, '✕')))));
  }
  const colsPlacar = [
    { rot: 'Modelo', col: 'nome', num: false, tit: 'Ordenar por nome' },
    { rot: 'Tamanho', col: 'bytes', num: true, tit: 'Ordenar por tamanho no disco' },
    { rot: 'Capacidades', col: null, num: false },
    { rot: 'Ctx GPU', col: 'ctx', num: true, tit: 'Ordenar por teto de contexto 100% GPU' },
    { rot: 'tok/s', col: 'tps', num: true, tit: 'Ordenar por velocidade (tok/s)' },
    { rot: '⚡ Índice', col: 'indice', num: true, tit: 'Índice Global Multicritério: Conhecimento (64%) + Velocidade (18%) + Tamanho (9%) + Contexto GPU (9%)' },
    { rot: 'Média', col: 'media', num: true, tit: 'Média pura de acertos de conhecimento' },
    ...papeisNota.map(p => ({ rot: p.icone, col: p.id, num: true, tit: `Ordenar por ${p.rotulo}` })),
    { rot: '', col: null, num: false }
  ];
  const abertoIni = localStorage.getItem('li-instalados-aberto') !== '0';
  const totalDisco = m.instalados.reduce((a, b) => a + (b.bytes || 0), 0);
  const mediasValidas = (m.instalados || []).map(x => mediaGeralModelo(x, papeisNota)).filter(v => v != null);
  const mediaEsquadra = mediasValidas.length ? (mediasValidas.reduce((a, b) => a + b, 0) / mediasValidas.length) : null;
  const maiorTps = (m.instalados || []).reduce((max, x) => Math.max(max, x.medido?.tps_mediana || 0), 0);
  const listaAposentados = m.aposentados || [];

  const heroStats = h('div', { class: 'meus-stats-grid' },
    h('div', { class: 'meus-stat-card' },
      h('small', {}, 'Modelos instalados'),
      h('b', {}, `${m.instalados.length} instalados`)),
    h('div', { class: 'meus-stat-card' },
      h('small', {}, 'Espaço Ocupado'),
      h('b', {}, fmtGB(totalDisco))),
    h('div', { class: 'meus-stat-card' },
      h('small', {}, 'Velocidade Máxima'),
      h('b', {}, maiorTps ? `${fmtN(maiorTps, 0)} tok/s` : '—')),
    h('div', { class: 'meus-stat-card' },
      h('small', {}, 'Média geral dos seus modelos'),
      h('b', {}, mediaEsquadra ? `${fmtN(mediaEsquadra, 1)} pts` : '—')),
    h('div', {
      class: 'meus-stat-card',
      style: 'cursor:pointer',
      title: 'Clique para ver o histórico e notas dos modelos que já foram testados e apagados',
      onclick: () => {
        const d = document.querySelector('#p-modelos details:last-of-type');
        if (d) { d.open = true; d.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      }
    },
      h('small', {}, 'Histórico & Aposentados'),
      h('b', { style: 'color:var(--muted)' }, `${listaAposentados.length} modelos ▾`)));

  const blocoInstalados = h('details', {
    class: 'painel-colapsavel',
    open: abertoIni,
    ontoggle: e => { try { localStorage.setItem('li-instalados-aberto', e.target.open ? '1' : '0'); } catch(x){} }
  },
    h('summary', {},
      h('div', { class: 'linha', style: 'gap:10px' },
        h('h2', {}, `Modelos Instalados (${m.instalados.length})`),
        chip(`${fmtGB(totalDisco)} no disco`, 'neutro')),
      h('div', { class: 'linha', style: 'gap:8px' },
        h('button', { class: 'btn mini primario', onclick: e => { e.preventDefault(); e.stopPropagation(); atualizarModelosInstalados(); } }, '↻ Atualizar modelos atuais'),
        h('span', { class: 'colapsavel-dica' }, 'Clique para recolher/expandir'))),
    h('div', { class: 'painel-conteudo' },
      h('p', { class: 'sub', style: 'margin:4px 0 12px' }, 'Modelos ordenados pelo Índice Prático (Conhecimento + Velocidade + Tamanho + Contexto GPU). Clique nas colunas para mudar a ordenação.'),
      m.instalados.length ? h('div', { class: 'tabela-wrap' }, h('table', { class: 'tabela-compacta' }, h('thead', {}, h('tr', {}, colsPlacar.map(c => h('th', {
        class: c.num ? 'num' : '',
        style: c.col ? 'cursor:pointer;user-select:none' : '',
        title: c.tit || '',
        onclick: c.col ? () => ordenarPlacar(c.col) : undefined
      }, c.rot + (c.col ? setaP(c.col) : ''))))), h('tbody', {}, linhas)))
        : h('div', { class: 'vazio' }, m.ollama_no_ar ? 'Nenhum modelo instalado.' : 'Ollama desligado.')));

  const abertoApos = localStorage.getItem('li-aposentados-aberto') === '1';
  const blocoAposentados = h('details', {
    class: 'painel-colapsavel',
    open: abertoApos,
    ontoggle: e => { try { localStorage.setItem('li-aposentados-aberto', e.target.open ? '1' : '0'); } catch(x){} }
  },
    h('summary', {},
      h('div', { class: 'linha', style: 'gap:10px' },
        h('h2', {}, `Modelos Aposentados (${listaAposentados.length})`),
        listaAposentados.length ? chip('Notas salvas', 'neutro') : null),
      h('span', { class: 'colapsavel-dica' }, 'Clique para recolher/expandir')),
    h('div', { class: 'painel-conteudo' },
      h('p', { class: 'sub', style: 'margin:4px 0 14px' }, 'Modelos removidos do disco. As notas continuam salvas no histórico.'),
      cartoesAposentados(m)));

  raiz.replaceChildren(
    h('div', { class: 'pagina-topo' },
      h('div', { class: 'eyebrow-tech' }, 'LOCAL AI SEARCH · PLACAR E DUELOS'),
      h('h1', {}, 'Meus modelos'),
      h('p', { class: 'sub' }, 'Placar dos modelos instalados, mapa de equilíbrio entre nota e velocidade e duelo entre dois modelos (A × B).')),
    heroStats,
    blocoInstalados,
    titulo('Mapa de Equilíbrio & VRAM (Sweet Spot)', 'Simule o consumo físico real na GPU entre 4k e 1M e compare folgas e velocidades.'),
    painelSweetSpot(m, papeisNota),
    h('div', { id: 'sec-arena' }, titulo('Duelo: compare dois modelos (A × B)', 'Compare dois modelos escolhidos lado a lado — sem misturar com os modelos de outros usos.')),
    comparador(m, papeisNota),
    blocoAposentados,
    h('div', { id: 'hist-v1' }));
  carregarHistoricoV1();
}
function cartoesAposentados(m) {
  const lista = m.aposentados || [];
  if (!lista.length) return h('div', { class: 'vazio' }, 'Nenhum modelo aposentado ainda. Quando você apagar um modelo pelo painel, ele aparece aqui com as notas que tinha.');
  return h('div', { class: 'grade g2' }, lista.map(a => {
    const notas = Object.entries(a.papeis || {}).map(([pid, v]) => h('span', { class: 'chip neutro', title: `${papelPorId(pid)?.rotulo || pid}: ${fmtN(v.nota, 1)}` + (v.ic ? ` (IC ${v.ic[0]}–${v.ic[1]})` : '') }, `${papelPorId(pid)?.icone || ''} ${fmtN(v.nota, 0)}`));
    const herd = Object.entries(a.herdeiros || {});
    return h('div', { class: 'cartao' },
      h('div', { class: 'linha topo' }, h('div', { class: 'quebra' }, h('h3', {}, a.modelo), h('div', { class: 'sub' }, a.quando ? `Aposentado em ${fmtData(a.quando)}` : 'Removido fora do painel (data não registrada)', a.bytes ? ` · liberou ${fmtGB(a.bytes)}` : '')),
        a.versao_antiga ? chip('versão antiga do arquivo', 'warn', 'O arquivo desta tag mudou desde a medição') : null),
      a.motivo ? h('p', { class: 'sub', style: 'margin:8px 0 0' }, a.motivo) : null,
      notas.length ? h('div', { style: 'margin-top:12px' }, h('div', { class: 'sub', style: 'margin-bottom:5px' }, CHIP_MEDIDO(), ` nota por função (${a.n_itens} itens${a.tps ? ' · ' + fmtN(a.tps, 0) + ' tok/s' : ''})`), h('div', { class: 'chips' }, notas)) : h('div', { class: 'sub', style: 'margin-top:10px' }, 'Nunca foi medido neste protocolo.'),
      herd.length ? h('div', { class: 'sub', style: 'margin-top:10px' }, 'Funções que passaram a: ' + herd.map(([pid, mid]) => `${papelPorId(pid)?.rotulo} → ${mid}`).join('; ')) : null,
      h('div', { style: 'margin-top:12px' }, h('div', { class: 'sub', style: 'margin-bottom:4px' }, 'Para trazer de volta (precisa de internet):'), cmd('ollama pull ' + a.modelo)));
  }));
}
function comparador(m, papeisNota) {
  const instIds = (m.instalados || []).map(x => x.id);
  const desafMap = new Map();
  for (const lista of Object.values(m.desafiantes || {})) {
    for (const c of lista || []) {
      const pull = c.encaixe?.variante?.pull || c.id;
      if (!instIds.includes(pull) && !desafMap.has(pull)) desafMap.set(pull, `${c.nome} (${pull}) — baixa no duelo`);
    }
  }
  const sugs = [
    ['hf.co/unsloth/Qwen3.8-27B-GGUF:Q3_K_M', 'Qwen 3.8 27B Q3_K_M (13,5 GB) — outra quantização p/ comparar'],
    ['hf.co/unsloth/Qwen3.8-27B-GGUF:IQ3_M', 'Qwen 3.8 27B IQ3_M (12,5 GB) — outra quantização p/ comparar'],
    ['hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:Q4_K_M', 'Gemma 4 26B-A4B Q4_K_M — outra quantização p/ comparar'],
    ['qwen3:8b', 'Qwen 3 8B (qwen3:8b) — baixa no duelo'],
    ['moondream:latest', 'Moondream Visão (moondream:latest) — baixa no duelo'],
  ];
  for (const sug of sugs) {
    if (!instIds.includes(sug[0]) && !desafMap.has(sug[0])) desafMap.set(sug[0], sug[1]);
  }
  function criarSeletor(padraoIdx, rotulo) {
    const sel = h('select', {},
      instIds.length ? h('optgroup', { label: 'Instalados nesta máquina (comparação imediata)' }, instIds.map(id => h('option', { value: id }, `${nomeAmigavelModelo(id)}${tagQuantModelo(id) ? ' (' + tagQuantModelo(id) + ')' : ''}`))) : null,
      desafMap.size ? h('optgroup', { label: 'Não instalados / Outras quants (baixa na batalha)' }, [...desafMap].map(([val, rot]) => h('option', { value: val }, rot))) : null,
      h('option', { value: '__custom__' }, 'Outro modelo ou quantização (digitar tag)…'));
    if (sel.options.length > padraoIdx) sel.selectedIndex = padraoIdx;
    const inp = h('input', { type: 'text', placeholder: 'ex.: hf.co/unsloth/Qwen3.8-27B-GGUF:Q3_K_M', style: 'display:none;width:100%;margin-top:6px' });
    sel.addEventListener('change', () => { inp.style.display = sel.value === '__custom__' ? '' : 'none'; if (sel.value === '__custom__') inp.focus(); });
    return { el: h('label', { class: 'campo' }, rotulo, sel, inp), valor: () => (sel.value === '__custom__' ? inp.value.trim() : sel.value), sel };
  }
  const selA = criarSeletor(0, 'Lutador A (Modelo 1)'), selB = criarSeletor(1, 'Lutador B (Modelo 2)');
  const p = h('select', {},
    h('option', { value: 'todas' }, '🌐 Todas as funções (Visão completa A × B)'),
    papeisNota.map(x => h('option', { value: x.id }, `${x.icone || ''} Somente ${x.rotulo}`)));
  const snDuelo = seletorNivel((m.instalados || []).slice(0, 2).map(x => x.bytes));
  const nv = snDuelo.sel;
  const saida = h('div', { style: 'margin-top:16px' });

  async function renderizarComparacaoConhecida() {
    const va = selA.valor(), vb = selB.valor();
    if (!va || !vb || va === vb) {
      saida.replaceChildren(h('div', { class: 'aviso-caixa' }, 'Escolha dois modelos diferentes para comparar.'));
      return;
    }
    const instA = (m.instalados || []).find(x => x.id === va);
    const instB = (m.instalados || []).find(x => x.id === vb);
    if (!instA || !instB) {
      saida.replaceChildren(h('div', { class: 'info-caixa' },
        h('b', {}, 'Um dos modelos ainda não está instalado/medido localmente. '),
        'Clique em ', h('b', {}, '“⚔ Rodar Batalha (Baixar & Medir)”'), ' para baixar automaticamente e testar os dois nos mesmos itens.'));
      return;
    }
    saida.replaceChildren(h('div', { class: 'sub' }, 'Calculando confronto direto com os números já conhecidos…'));
    try {
      const r = await api(`/api/comparar?a=${encodeURIComponent(va)}&b=${encodeURIComponent(vb)}&papel=${encodeURIComponent(p.value)}`);
      if (!r.ok) {
        saida.replaceChildren(h('div', { class: 'aviso-caixa' }, r.motivo + ' — clique em “⚔ Rodar Batalha” para medir os dois nos mesmos itens.'));
        return;
      }
      const nomeA = nomeAmigavelModelo(va), nomeB = nomeAmigavelModelo(vb);
      const ma = r.modelo_a || {}, mb = r.modelo_b || {};
      const tpsA = ma.tps || instA.medido?.tps_mediana, tpsB = mb.tps || instB.medido?.tps_mediana;
      const indA = ma.indice_pratico?.total ?? instA.indice_pratico?.total;
      const indB = mb.indice_pratico?.total ?? instB.indice_pratico?.total;
      const ctxA = ma.ctx_gpu || instA.sonda?.ctx_max_gpu, ctxB = mb.ctx_gpu || instB.sonda?.ctx_max_gpu;

      const porPapel = r.por_papel || { [p.value]: r };
      const linhasTab = Object.entries(porPapel).map(([pid, d]) => {
        const pap = papelPorId(pid);
        const cor = { superior: 'ok', inferior: 'bad', empate: 'neutro' }[d.veredito];
        let txtV = { superior: `${nomeA} vence`, inferior: `${nomeB} vence`, empate: 'Empate técnico' }[d.veredito];
        if (d.veredito === 'empate' && tpsA && tpsB && Math.max(tpsA, tpsB) / Math.min(tpsA, tpsB) >= 1.3) {
          txtV = `Empate em nota (${tpsA > tpsB ? nomeA : nomeB} é ${fmtN(Math.max(tpsA, tpsB) / Math.min(tpsA, tpsB), 1)}× mais rápido)`;
        }
        return h('tr', {},
          h('td', {}, `${pap?.icone || ''} `, h('b', {}, pap?.rotulo || pid)),
          h('td', { class: 'num' }, h('b', { style: d.a >= d.b ? 'color:var(--ok)' : '' }, fmtN(d.a, 1))),
          h('td', { class: 'num' }, h('b', { style: d.b > d.a ? 'color:var(--ok)' : '' }, fmtN(d.b, 1))),
          h('td', { class: 'num' }, `${d.dif > 0 ? '+' : ''}${fmtN(d.dif, 1)}`, h('div', { class: 'sub', style: 'font-size:.72rem' }, `IC ${fmtN(d.ic[0], 1)}..${fmtN(d.ic[1], 1)}`)),
          h('td', {}, chip(txtV, cor), h('div', { class: 'sub', style: 'font-size:.73rem' }, `só ${nomeA}: ${d.so_a} · só ${nomeB}: ${d.so_b} (${d.itens} itens)`)));
      });

      saida.replaceChildren(
        h('div', { class: 'duelo-head-vs', style: 'margin-bottom:12px' },
          h('div', { class: 'duelo-fighter f-a' },
            h('span', { class: 'kpi-tag' }, 'Lutador A'),
            h('h3', {}, nomeA, tagQuantModelo(va) ? [' ', chip(tagQuantModelo(va), 'neutro')] : null),
            h('div', { class: 'metricas' },
              indA != null ? h('span', {}, '⚡ Índice ', h('b', {}, fmtN(indA, 1))) : null,
              tpsA ? h('span', {}, h('b', {}, fmtN(tpsA, 0)), ' tok/s') : null,
              ctxA ? h('span', {}, h('b', {}, fmtCtx(ctxA)), ' GPU') : null,
              h('span', {}, h('b', {}, fmtGB(instA.bytes))))),
          h('div', { class: 'duelo-vs-badge' },
            tpsA && tpsB && Math.max(tpsA, tpsB) / Math.min(tpsA, tpsB) >= 1.25
              ? h('div', { style: 'text-align:center' },
                  h('b', { style: 'font-size:1.1rem;color:var(--ink)' }, 'A × B'),
                  h('div', { class: 'chip ok', style: 'margin-top:4px' }, `⚡ ${tpsA > tpsB ? nomeA : nomeB}: ${fmtN(Math.max(tpsA, tpsB) / Math.min(tpsA, tpsB), 1)}× mais veloz`))
              : h('b', { style: 'font-size:1.1rem;color:var(--muted)' }, 'A × B')),
          h('div', { class: 'duelo-fighter f-b' },
            h('span', { class: 'kpi-tag' }, 'Lutador B'),
            h('h3', {}, nomeB, tagQuantModelo(vb) ? [' ', chip(tagQuantModelo(vb), 'neutro')] : null),
            h('div', { class: 'metricas' },
              indB != null ? h('span', {}, '⚡ Índice ', h('b', {}, fmtN(indB, 1))) : null,
              tpsB ? h('span', {}, h('b', {}, fmtN(tpsB, 0)), ' tok/s') : null,
              ctxB ? h('span', {}, h('b', {}, fmtCtx(ctxB)), ' GPU') : null,
              h('span', {}, h('b', {}, fmtGB(instB.bytes)))))),
        h('div', { class: 'tabela-wrap' },
          h('table', { class: 'tabela-compacta' },
            h('thead', {}, h('tr', {},
              h('th', {}, 'Função avaliada'),
              h('th', { class: 'num' }, nomeA),
              h('th', { class: 'num' }, nomeB),
              h('th', { class: 'num' }, 'Diferença (A − B)'),
              h('th', {}, 'Diagnóstico A × B (sem terceiros)'))),
            h('tbody', {}, linhasTab))));
    } catch (e) {
      saida.replaceChildren(h('div', { class: 'aviso-caixa' }, e.message));
    }
  }

  const btInstantaneo = h('button', { class: 'btn primario', onclick: renderizarComparacaoConhecida }, '📊 Comparar números já conhecidos');
  const btDuelo = h('button', { class: 'btn', onclick: async () => {
    const va = selA.valor(), vb = selB.valor();
    if (!va || !vb || va === vb) { saida.replaceChildren(h('div', { class: 'aviso-caixa' }, 'Escolha dois modelos ou quantizações diferentes para a batalha.')); return; }
    try {
      await api('/api/duelo', { a: va, b: vb, papel: p.value, nivel: nv.value, nivel_forcado: true, confirmo_download: true });
      saida.replaceChildren(h('div', { class: 'info-caixa' }, h('b', {}, `⚔ Batalha iniciada: ${nomeAmigavelModelo(va)} × ${nomeAmigavelModelo(vb)}`), ' — se algum ainda não estiver instalado, o painel baixa automaticamente, mede os dois nos mesmos itens e abre o placar A × B ao terminar.'));
      await carregarJobs();
    } catch (e) { saida.replaceChildren(h('div', { class: 'aviso-caixa' }, e.message)); }
  } }, '⚔ Rodar Batalha no Hardware (Baixar & Medir)');

  // Se ambos já estão instalados na abertura, mostra o comparativo instantaneamente!
  if (instIds.length >= 2) setTimeout(renderizarComparacaoConhecida, 10);

  return h('div', { class: 'cartao' },
    h('div', { class: 'campos', style: 'margin-top:0;align-items:flex-end' },
      selA.el,
      selB.el,
      h('label', { class: 'campo' }, 'Escopo da comparação', p),
      h('label', { class: 'campo' }, 'Profundidade (se rodar batalha)', nv, snDuelo.aviso)),
    h('div', { class: 'linha', style: 'justify-content:flex-start;gap:10px;margin-top:14px' }, btInstantaneo, btDuelo),
    saida);
}
async function detalheModelo(id) {
  let d;
  try { d = await api('/api/modelo/' + encodeURIComponent(id)); } catch (e) { toast(e.message); return; }
  const nomes = S.mesa.suites;
  const linhas = Object.entries(d.resumo.suites).map(([s, v]) => h('tr', {}, h('td', {}, nomes[s] || s), h('td', { class: 'num' }, v.acc + '%'), h('td', { class: 'num' }, v.n), h('td', {}, barraSuite(v), h('span', { class: 'sub' }, `${v.ic[0]}–${v.ic[1]}%`))));
  const porKv = d.sonda?.por_kv || (d.sonda?.pontos?.length ? { q8_0: d.sonda } : {});
  const tabelasSonda = Object.entries(porKv).filter(([, v]) => v.pontos?.length).map(([kvt, v]) =>
    h('div', { style: 'margin-top:8px' },
      h('h4', { style: 'margin-bottom:6px' }, `Cache KV: ${kvt}`),
      h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Contexto', 'Memória', '% na GPU', 'tok/s (geração)', 'tok/s (leitura)'].map(t => h('th', {}, t)))),
        h('tbody', {}, v.pontos.map(p => h('tr', {}, h('td', {}, fmtCtx(p.ctx)), h('td', { class: 'num' }, fmtGB(p.total_bytes)), h('td', { class: 'num' }, p.pct_gpu + '%'), h('td', { class: 'num' }, p.tps), h('td', { class: 'num' }, p.leitura_tps))))))));
  abrirDialogo(h('div', { class: 'dlg-in' }, h('h2', {}, id), h('div', { class: 'sub' }, `${d.resumo.n_itens} itens medidos · protocolo ${S.mesa.protocolo} · última medição ${d.resumo.ultima.slice(0, 16).replace('T', ' ')}`),
    h('h3', {}, 'Acertos por teste'), h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Teste', 'Acerto', 'n', 'Intervalo 90%'].map(t => h('th', {}, t)))), h('tbody', {}, linhas))),
    tabelasSonda.length ? [h('h3', {}, 'Memória e velocidade por contexto (medido)'), ...tabelasSonda] : h('div', { class: 'sub' }, 'Sem sonda de contexto: use “Medir VRAM e velocidade” na aba Medir.'),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
}
async function carregarHistoricoV1() {
  try {
    const h1 = await api('/api/historico');
    if (!h1.modelos) return;
    const conhecidos = new Set([...(S.mesa?.instalados || []).map(x => x.id), ...(S.mesa?.aposentados || []).map(x => x.modelo)]);
    const ap = Object.entries(h1.modelos).filter(([k]) => !conhecidos.has(k));
    if (!ap.length) return;
    $('#hist-v1').replaceChildren(titulo('Histórico do protocolo antigo (v1)', 'Contexto 2048, respostas cortadas em 512 tokens e corretores antigos: NÃO comparável com as notas acima. Serve só como memória do que já foi testado.'),
      h('details', {}, h('summary', {}, `Ver ${ap.length} modelo(s) do v1`), h('div', { class: 'cartao flat' }, ap.map(([k, v]) => h('div', {}, h('b', {}, k), ' ', h('span', { class: 'sub' }, Object.entries(v).map(([s, x]) => `${s} ${x.acc}% (n=${x.n})`).join(' · ')))))));
  } catch (e) { /* sem histórico */ }
}
