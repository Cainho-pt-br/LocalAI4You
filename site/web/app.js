'use strict';
/* Local Intelligence — painel. Sem dependências e sem rede externa: funciona offline.
   Estrutura: base.js (helpers) · calc.js (motor da calculadora) · calc-ui.js · app-*.js (uma página cada) · este arquivo (estado, tarefas, rotas). */

const ABAS = [['decidir', 'Decidir', 'Decisão'], ['modelos', 'Meus modelos'], ['radar', 'Radar', 'Explorar & Arena'], ['calculadora', 'Calculadora'], ['medir', 'Medir'],
              ['parque', 'Parque', 'Sistema'], ['offline', 'Offline'], ['ajuda', 'Como ler'], ['guias', 'Guias de uso']];
const ANTIGAS = { esquadra: 'modelos', lab: 'medir' };   // links salvos de versões anteriores
const S = { aba: 'decidir', mesa: null, saude: null, jobs: [], jobsVistos: {}, radarInfo: null, calc: null, calcT: 0, filtroRadar: { maquina: 'boss', papel: '', comunidade: false, antigos: false, cap: '', ordem: 'prioridade', pagina: 0 } };
const papelPorId = id => (S.mesa?.papeis || []).find(p => p.id === id);

// ---------------------------------------------------------------- máquina controlada (esta ou outra do parque, pelo tailnet)
async function carregarMaquinas() {
  try { S.maquinas = await api('/api/maquinas'); } catch (e) { S.maquinas = { remotas: [], parque: [] }; }
  desenharAlvo();
}
function desenharAlvo() {
  const el = $('#alvo'), rem = S.maquinas?.remotas || [];
  if (!rem.length) { el.replaceChildren(); return; }
  const sel = h('select', { 'aria-label': 'Máquina controlada', onchange: ev => escolherAlvo(ev.target.value) },
    h('option', { value: '', selected: !LI.alvo }, 'Esta máquina'),
    rem.map(m => h('option', { value: m.id, selected: m.id === LI.alvo }, `${m.online ? '● ' : '○ '}${m.nome}${m.online ? '' : ' (desligada)'}`)));
  el.replaceChildren(h('label', {}, h('span', { class: 'sub' }, 'Controlando'), sel));
}
async function escolherAlvo(id) {
  LI.alvo = id || '';
  try { sessionStorage.setItem('li-alvo', LI.alvo); } catch (e) { /* ok */ }
  S.mesa = null; S.saude = null; S.jobs = []; S.jobsVistos = {}; S.calcT = 0; S.radarInfo = null;
  S.filtroRadar.maquina = LI.alvo || 'boss';
  desenharBannerAlvo(); desenharStatus(); desenhar();
  await Promise.all([carregarSaude(), carregarMesa(), carregarJobs()]);
  desenharBannerAlvo(); desenharAbas(); desenharStatus(); desenhar();
}
function desenharBannerAlvo() {
  const el = $('#banner-alvo');
  if (!LI.alvo) { el.replaceChildren(); el.className = ''; return; }
  const m = (S.maquinas?.remotas || []).find(x => x.id === LI.alvo) || { nome: LI.alvo };
  const sem = S.mesa && !S.mesa.radar?.existe;
  el.className = 'banner-alvo';
  el.replaceChildren(h('div', { class: 'linha' }, h('div', {}, h('b', {}, `Você está controlando: ${m.nome}`), h('div', { class: 'sub' }, 'Tudo aqui — medir, baixar, aposentar, radar — roda LÁ, com o hardware e os modelos dessa máquina.')),
    h('div', { class: 'linha' }, sem ? h('span', { class: 'chip warn' }, 'sem radar') : null,
      h('button', { class: 'btn mini', onclick: sincronizarRadar }, 'Enviar o radar desta máquina para lá'),
      h('button', { class: 'btn mini', onclick: () => escolherAlvo('') }, 'Voltar para esta máquina'))));
}
async function sincronizarRadar() {
  try {
    const r = await fetch('/api/maquinas/sincronizar-radar', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-LI': '1' }, body: JSON.stringify({ id: LI.alvo }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || 'falhou');
    toast(`Radar enviado: ${d.total} modelos. O encaixe é recalculado com o hardware de lá.`);
    await carregarMesa(); desenharBannerAlvo(); desenhar();
  } catch (e) { toast(e.message, 9000); }
}

// ---------------------------------------------------------------- dados
async function carregarSaude() {
  try { S.saude = await api('/api/saude'); } catch (e) { S.saude = null; }
  desenharStatus();
}
async function carregarMesa() {
  if (window.LI_PUBLIC_MODE) { S.mesa = null; return; }
  try { S.mesa = await api('/api/mesa'); } catch (e) { toast('Falha ao carregar a mesa de decisão: ' + e.message); }
}
async function carregarJobs() {
  let ext = null;
  try { const d = await api('/api/jobs'); S.jobs = d.jobs; ext = d.externa; } catch (e) { return; }
  const rod = S.jobs.find(j => j.estado === 'rodando');
  const barra = $('#tarefa-barra');
  if (!rod && ext) {  // tarefa pesada rodando no terminal (python cli.py bench…): o painel mostra e não deixa disputar a GPU
    const pct = ext.total ? Math.round(100 * (ext.feitos || 0) / ext.total) : null;
    barra.className = 'on';
    barra.replaceChildren(h('div', { class: 'tarefa' },
      h('div', { class: 'tarefa-txt' }, h('span', {}, `${ext.titulo} — ${ext.msg || ''}`), h('span', {}, [pct != null ? pct + '%' : '', ext.eta_s ? ` · faltam ~${Math.ceil(ext.eta_s / 60)} min` : ''].join(''))),
      h('div', { class: 'barra' }, h('i', { style: `width:${pct || 3}%` }))));
  } else if (rod) {
    barra.className = 'on';
    barra.replaceChildren(h('div', { class: 'tarefa' },
      h('div', { class: 'tarefa-txt' }, h('span', {}, `${rod.titulo} — ${rod.msg || ''}`),
        h('span', {}, [rod.pct != null ? Math.round(rod.pct) + '%' : '', rod.eta_s ? ` · faltam ~${Math.ceil(rod.eta_s / 60)} min` : ''].join(''), ' ',
          h('button', { class: 'btn mini', onclick: () => api('/api/cancelar', { job: rod.id }).then(() => toast('Cancelando…')) }, 'Cancelar'))),
      h('div', { class: 'barra' }, h('i', { style: `width:${rod.pct || 3}%` }))));
  } else { barra.className = ''; barra.replaceChildren(); }
  for (const j of S.jobs) {
    const antes = S.jobsVistos[j.id];
    S.jobsVistos[j.id] = j.estado;
    if (antes === 'rodando' && j.estado !== 'rodando') await aoTerminarJob(j);
  }
}
async function aoTerminarJob(j) {
  if (j.estado === 'concluido') toast(`✅ ${j.titulo}: concluído`);
  else if (j.estado === 'erro') toast(`❌ ${j.titulo}: ${j.erro}`, 9000);
  else toast(`${j.titulo}: ${j.estado}`);
  await carregarMesa(); await carregarSaude();
  S.calcT = 0;  // catálogo da calculadora muda com varredura e medição
  if (j.tipo === 'varredura') S.radarInfo = null;
  if ((j.tipo === 'desafio' || j.tipo === 'duelo') && j.estado === 'concluido' && j.resultado?.veredito) {
    const v = (S.mesa?.vereditos || []).find(x => x.id === j.resultado.veredito);
    if (v) abrirVeredito(v);
  }
  desenhar();
}

// ---------------------------------------------------------------- navegação e status
function irPara(aba) { S.aba = aba; location.hash = aba; desenhar(); window.scrollTo({ top: 0 }); }
function desenharAbas() {
  const pend = S.mesa ? (S.mesa.acoes || []).filter(a => a.prioridade <= 2).length : 0;
  const mostrarParque = (S.mesa?.maquinas_parque ?? 1) > 1 || S.aba === 'parque';
  const itens = [];
  let grupoPendente = null;
  for (const [id, nome, grupo] of ABAS) {
    if (grupo) grupoPendente = grupo;
    if (id === 'parque' && !mostrarParque) continue;
    if (grupoPendente) { itens.push(h('div', { class: 'grupo' }, grupoPendente)); grupoPendente = null; }
    itens.push(h('button', { role: 'tab', 'aria-selected': S.aba === id ? 'true' : 'false', onclick: () => irPara(id) }, nome, id === 'decidir' && pend ? h('span', { class: 'badge', title: `${pend} ação(ões) pedem sua atenção` }, pend) : null));
  }
  $('#abas').replaceChildren(...itens);
}
// ---------------------------------------------------------------- tema claro/escuro
function temaAtual() {
  try {
    const salvo = localStorage.getItem('li-tema');
    if (salvo === 'light' || salvo === 'dark') return salvo;
  } catch (x) {}
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function aplicarTema(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('li-tema', t); } catch (x) {}
  const bt = $('#btn-tema');
  if (bt) bt.textContent = t === 'dark' ? '🌙 Modo Escuro' : '☀ Modo Claro';
}
function alternarTema() {
  const prox = temaAtual() === 'dark' ? 'light' : 'dark';
  aplicarTema(prox);
}
function inicializarTema() {
  const bt = $('#btn-tema');
  if (bt) {
    bt.onclick = alternarTema;
    bt.textContent = temaAtual() === 'dark' ? '🌙 Modo Escuro' : '☀ Modo Claro';
  }
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', inicializarTema);
} else {
  inicializarTema();
}
aplicarTema(temaAtual());

function desenharStatus() {
  const s = S.saude;
  const el = $('#status');
  if (!s) { el.replaceChildren(h('span', { class: 'pill' }, h('i', { class: 'dot bad' }), 'painel sem resposta')); return; }
  const gpu = s.gpu, kv = S.mesa?.kv_medido;
  el.replaceChildren(
    h('span', { class: 'pill', title: s.ollama.url }, h('i', { class: 'dot ' + (s.ollama.no_ar ? 'ok' : 'bad') }), s.ollama.no_ar ? `Ollama ${s.ollama.versao}` : 'Ollama desligado'),
    gpu ? h('span', { class: 'pill', title: gpu.nome }, h('i', { class: 'dot ok' }), `GPU: ${gpu.vram_livre_gb} de ${gpu.vram_gb} GB livres`) : null,
    kv ? h('span', { class: 'pill', title: `Medido: a memória cresceu ${kv.medido_gb} GB entre os contextos testados; ${kv.tipo} previa ${kv.previsto_gb[kv.tipo]} GB (via ${kv.modelo})` }, h('i', { class: 'dot ok' }), `cache ${kv.tipo} medido`) : null,
    h('span', { class: 'pill', title: 'Protocolo de benchmark' }, h('i', { class: 'dot' }), 'protocolo ' + s.protocolo),
    s.avisos_internos?.length ? h('span', { class: 'pill', title: s.avisos_internos.join('\n') }, h('i', { class: 'dot warn' }), `${s.avisos_internos.length} aviso(s)`) : null);
}

// ---------------------------------------------------------------- CALCULADORA (aba do painel; o motor e a interface vivem em calc.js / calc-ui.js)
async function pCalculadora() {
  const raiz = $('#p-calculadora');
  raiz.replaceChildren(h('div', { class: 'sub' }, 'Carregando o catálogo de modelos…'));
  try {
    const d = await garantirCalc();
    if (S.aba !== 'calculadora') return;
    LI_CALC_UI.montar(raiz, d, { aoExportar: () => { location.href = '/api/calc/html'; } });
  } catch (e) { raiz.replaceChildren(h('div', { class: 'pagina-topo' }, h('h1', {}, 'Calculadora de hardware')), h('div', { class: 'aviso-caixa' }, e.message), h('div', { style: 'margin-top:12px' }, h('button', { class: 'btn primario', onclick: () => irPara('radar') }, 'Ir para o radar'))); }
}

// ---------------------------------------------------------------- AJUDA
function pAjuda() {
  const cards = [
    ['1', 'Cabe no meu PC?', 'A calculadora estima o que cabe na GPU ou na RAM e quanto contexto sobra. No painel local, a sonda mede o uso real.'],
    ['2', 'É melhor que o meu modelo?', 'Só compare modelos testados com os mesmos itens e protocolo. O intervalo de confiança mostra a incerteza.'],
    ['3', 'Posso apagar o antigo?', 'Espere um substituto ganhar com evidência. Empate técnico é um resultado válido; não precisa trocar.']
  ];
  const evidencias = [
    ['MEDIDO', 'Rodou no computador indicado, com intervalo de confiança. Só vale comparar resultados do mesmo protocolo.'],
    ['ESTIMADO', 'Conta feita com tamanho do modelo e hardware. Velocidade em CPU é aproximada; confirme no seu PC.'],
    ['PRIORIDADE', 'Ajuda a escolher o que testar primeiro. Não é nota de qualidade.']
  ];
  $('#p-ajuda').replaceChildren(
    h('div',{class:'pagina-topo'},h('span',{class:'guia-kicker'},'LEIA SEM PRESSA'),h('h1',{},'Como ler os resultados'),h('p',{class:'sub'},'Um guia curto para entender o que o painel sabe, o que ele estima e qual próximo passo faz sentido.')),
    h('div',{class:'guia-grid'},cards.map(([n,t,d])=>h('article',{class:'guia-card'},h('span',{class:'guia-num'},n),h('h2',{},t),h('p',{},d)))),
    h('h2',{class:'guia-sec'},'Três selos, três significados'),
    h('div',{class:'guia-grid'},evidencias.map(([t,d])=>h('article',{class:'guia-card'},h('span',{class:'chip'},t),h('p',{},d)))),
    h('div',{class:'guia-callout'},h('b',{},'Uma regra prática'),h('p',{},'Se a diferença entre dois modelos não supera a incerteza, trate como empate. Prefira o que já funciona para você e evite baixar ou apagar por impulso.')),
    h('h2',{class:'guia-sec'},'Seu caminho em quatro passos'),
    h('ol',{class:'guia-passos'},h('li',{},'Escolha seu hardware na Calculadora.'),h('li',{},'Confira a quantização e o contexto recomendados.'),h('li',{},'No painel baixado, meça modelos instalados com o mesmo protocolo.'),h('li',{},'Compare evidências; só então decida manter, testar ou aposentar.')),
    h('a',{class:'btn primario',href:'#guias'},'Quero um passo a passo para usar IA local')
  );
}

const PAGINAS = { decidir: pDecidir, modelos: pModelos, radar: pRadar, calculadora: pCalculadora, parque: pParque, offline: pOffline, medir: pMedir, ajuda: pAjuda, guias: pGuias };
function desenhar() {
  desenharAbas();
  for (const [id] of ABAS) $('#p-' + id).classList.toggle('on', id === S.aba);
  PAGINAS[S.aba]();
}
function abaDoHash() {
  const x = ANTIGAS[location.hash.slice(1)] || location.hash.slice(1);
  return ABAS.some(a => a[0] === x) ? x : null;
}
async function iniciar() {
  S.aba = abaDoHash() || 'decidir';
  await carregarMaquinas();
  try { const a = sessionStorage.getItem('li-alvo') || ''; if (a && (S.maquinas.remotas || []).some(m => m.id === a)) { LI.alvo = a; S.filtroRadar.maquina = a; desenharAlvo(); desenharBannerAlvo(); } } catch (e) { /* ok */ }
  desenharAbas();
  await Promise.all([carregarSaude(), carregarMesa(), carregarJobs()]);
  desenharStatus();
  desenhar();
  setInterval(async () => { await carregarJobs(); if (S.aba === 'medir') desenharJobsMedir(); }, 2000);
  setInterval(carregarSaude, 15000);
  setInterval(carregarMaquinas, 30000);
}
window.addEventListener('hashchange', () => { const x = abaDoHash(); if (x && x !== S.aba) { S.aba = x; desenhar(); } });
iniciar();
