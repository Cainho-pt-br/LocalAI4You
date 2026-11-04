'use strict';
/* Local Intelligence — painel. Sem dependências e sem rede externa: funciona offline.
   Estrutura: base.js (helpers) · calc.js (motor da calculadora) · calc-ui.js · app-*.js (uma página cada) · este arquivo (estado, tarefas, rotas). */

const ABAS = [['decidir', 'Decidir', 'Decisão'], ['modelos', 'Meus modelos'], ['radar', 'Radar', 'Explorar & Arena'], ['calculadora', 'Calculadora'], ['medir', 'Medir'],
              ['parque', 'Parque', 'Sistema'], ['offline', 'Offline'], ['ajuda', 'Como ler']];
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
  $('#p-ajuda').replaceChildren(
    h('div', { class: 'pagina-topo' }, h('h1', {}, 'Como ler este painel'), h('p', { class: 'sub' }, 'Três perguntas, três selos de evidência e o que fazer quando sair um modelo novo.')),
    h('h3', {}, 'As três perguntas'),
    h('ol', {}, h('li', {}, h('b', {}, 'Cabe? '), 'O painel calcula, com o tamanho exato do arquivo e a arquitetura do modelo, se ele cabe na máquina e com quanto contexto. Nos seus modelos instalados isso é MEDIDO (aba Medir → Sonda de contexto).'),
      h('li', {}, h('b', {}, 'É melhor do que o que eu já tenho? '), 'Só um teste responde. “Testar contra o titular” ou “Arena: Duelo Direto (A × B)” baixa, mede nos mesmos itens e compara. Se a diferença não passa do ruído, o veredito é “empate técnico” — e a decisão racional é manter o que já está instalado.'),
      h('li', {}, h('b', {}, 'O que eu apago? '), 'O painel mostra quem não se justifica: pior que o titular, dominados por um menor e mais rápido, ou que só “lidera” por empate com um modelo bem menor (custo-benefício). “Aposentar” apaga, passa as funções a um herdeiro e guarda as notas em Meus modelos → Aposentados.')),
    h('h3', {}, 'Os três selos'),
    h('dl', {}, h('dt', {}, 'MEDIDO'), h('dd', {}, 'Rodou aqui, na sua GPU, no protocolo v2, com os mesmos itens para todos. Tem intervalo de confiança (±).'),
      h('dt', {}, 'ESTIMADO'), h('dd', {}, 'Conta de memória e velocidade usando o tamanho real dos arquivos e a configuração do modelo. Em máquinas sem GPU a velocidade vale ±2×.'),
      h('dt', {}, 'PRIORIDADE'), h('dd', {}, 'Nota de 0–100 de “vale testar?”: porte, recência, confiança do autor, adoção. NÃO mede qualidade — só ordena a fila de testes.')),
    h('h3', {}, 'Como ler a nota e o ±'),
    h('p', {}, 'A nota de cada função (0–100) é a média ponderada de acertos em testes públicos (MMLU-PT, MMLU-Pro, CAPITU, IFEval, BFCL, HumanEval, GSM8K e Visão). Com poucas dezenas de itens, a margem é grande: 78 ± 8 e 85 ± 7 NÃO são diferentes. Por isso as comparações usam bootstrap pareado e só declaram vencedor se o intervalo da diferença exclui zero e passa de 3 pontos.'),
    h('h3', {}, 'Quantização: do modelo e do cache de contexto'),
    h('p', {}, 'Quantizar o modelo (Q4_K_M, IQ3_S…) encolhe os pesos. Quantizar o cache de contexto (KV: f16, q8_0, q4_0) encolhe a memória da conversa, que cresce com o contexto. As duas coisas liberam memória, mas custam qualidade de formas diferentes — a aba Calculadora mostra os números do seu hardware e os comandos para ligar cada uma. Em “Radar → Outras quantizações” você vê todas as formas de baixar um modelo (Ollama e GGUF do Hugging Face) e se cada uma cabe.'),
    h('h3', {}, 'Calculadora de hardware'),
    h('p', {}, 'Escolha placa de vídeo (ou Mac, ou só processador), memória e uso: a calculadora mostra, para cada atividade, o modelo mais capaz que cabe, o de melhor equilíbrio e o leve/rápido, além de opções com muito contexto. É a mesma conta do painel, e dá para exportá-la como um arquivo HTML único para qualquer pessoa usar offline.'),
    h('h3', {}, 'Quando sair um modelo novo daqui a 2 meses'),
    h('ol', {}, h('li', {}, 'A vigia semanal (ou o botão “Varrer de novo” no Radar) detecta lançamentos dos laboratórios que você acompanha e mostra “NOVO” com a data.'),
      h('li', {}, 'O painel diz em quais máquinas ele cabe e em qual quantização — e você pode escolher outra no explorador de quantizações.'),
      h('li', {}, 'Clique em “Testar contra o titular”: o mesmo protocolo mede o novato — e a comparação com o titular é imediata, sem refazer nada.'),
      h('li', {}, 'Promova só nas funções em que ele ganhou e aposente quem sobrou sem função. O histórico de trocas fica registrado.')),
    h('h3', {}, 'Glossário rápido'),
    h('dl', {}, h('dt', {}, 'Quantização (Q4_K_M, IQ3_S…)'), h('dd', {}, 'Compressão dos pesos. Q4 é o padrão: perda pequena com ~1/4 do tamanho. Abaixo de 3 bits por peso a qualidade cai de forma perceptível — prefira um modelo menor em Q4.'),
      h('dt', {}, 'MoE (A3B, A4B…)'), h('dd', {}, 'Modelo com “especialistas”: tem 35B de parâmetros mas usa só ~3B por token. Ocupa memória como um 35B, mas roda rápido como um 3B.'),
      h('dt', {}, 'KV cache / contexto'), h('dd', {}, 'A memória da conversa. Cresce com o tamanho do contexto. O painel liga cache quantizado (q8_0) para caber mais contexto na VRAM.'),
      h('dt', {}, 'tok/s'), h('dd', {}, 'Tokens por segundo na geração. Em CPU é limitado pela banda da memória RAM; em GPU, pela VRAM.'),
      h('dt', {}, '100% na GPU'), h('dd', {}, 'Se qualquer parte do modelo vaza para a RAM do PC, a velocidade despenca. O benchmark só ranqueia quem fica 100% na GPU.')),
    h('h3', {}, 'Limites que você precisa conhecer'),
    h('ul', {}, h('li', {}, 'Os testes são públicos e curtos; não substituem experimentar o modelo no seu trabalho real.'),
      h('li', {}, 'HumanEval mede funções Python curtas — não é o mesmo que editar um repositório inteiro.'),
      h('li', {}, 'Visão mede leitura de notas fiscais, gráficos e painéis sintéticos; documentos reais escaneados com ruído podem exigir modelos maiores.'),
      h('li', {}, 'As notas do protocolo antigo (v1) não são comparáveis: o contexto era 2048 e as respostas eram cortadas em 512 tokens.'),
      h('li', {}, 'Na calculadora, “mais capaz” é regra de bolso (porte efetivo), não nota: só os modelos marcados MEDIDO foram testados.')));
}

// ---------------------------------------------------------------- roteamento
const PAGINAS = { decidir: pDecidir, modelos: pModelos, radar: pRadar, calculadora: pCalculadora, parque: pParque, offline: pOffline, medir: pMedir, ajuda: pAjuda };
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
