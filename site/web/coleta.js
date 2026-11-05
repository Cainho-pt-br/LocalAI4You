'use strict';
/* Coleta voluntária e anônima (Supabase do projeto Local AI Search).
   • Métricas de uso: SÓ no site. Sem cookies e sem IP: um id aleatório por aba (some ao fechar), a aba vista, de onde a
     pessoa veio (só o domínio), UTM e o tipo de aparelho. Respeita "Do Not Track" e o GPC do navegador.
   • E-mail: só quando a pessoa escreve e clica, com o texto de consentimento guardado junto.
   • Benchmarks da comunidade: só no app, só quando a pessoa clica em "enviar", depois de ver exatamente o que sai.
   Tudo passa pelo intermediário do site (/api/coleta, função do Vercel): nenhuma chave fica no código público, e ele
   só aceita as três funções de gravação. No site o caminho é relativo; o app local usa o endereço público do site. */
const COLETA = {
  url: /^(localhost|127\.|0\.0\.0\.0|\[::1\])/.test(location.hostname) || location.protocol === 'file:'
    ? 'https://localaisearch-site.vercel.app/api/coleta' : '/api/coleta',
};
const CONSENTIMENTO_LEAD = 'Aceito receber até 1 e-mail por mês do Local AI Search com modelos novos para o meu hardware. Posso sair quando quiser respondendo qualquer e-mail.';

function _rpc(fn, corpo) {
  if (!COLETA.url) return Promise.reject(new Error('coleta desligada'));
  return fetch(COLETA.url, { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fn, dados: corpo }) })
    .then(async r => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.message || ('HTTP ' + r.status)); } return r.status === 204 ? null : r.json(); });
}

// ---------------------------------------------------------------- métricas (site)
const _naoRastrear = () => navigator.doNotTrack === '1' || window.doNotTrack === '1' || navigator.globalPrivacyControl === true;
function _sessao() {
  try {
    let s = sessionStorage.getItem('li-sessao');
    if (!s) { s = Math.random().toString(36).slice(2, 12) + Date.now().toString(36).slice(-4); sessionStorage.setItem('li-sessao', s); }
    return s;
  } catch (e) { return null; }
}
function _utm() {
  try {
    const q = new URLSearchParams(location.search), u = {};
    for (const k of ['source', 'medium', 'campaign']) if (q.get('utm_' + k)) u[k] = q.get('utm_' + k).slice(0, 80);
    if (Object.keys(u).length) sessionStorage.setItem('li-utm', JSON.stringify(u));
    return JSON.parse(sessionStorage.getItem('li-utm') || '{}');
  } catch (e) { return {}; }
}
let _novo = null;
function _primeiraVisita() {
  if (_novo !== null) return _novo;
  try { _novo = !localStorage.getItem('li-visitou'); localStorage.setItem('li-visitou', '1'); } catch (e) { _novo = null; }
  return _novo;
}
function _origem() {
  try { const r = document.referrer ? new URL(document.referrer).hostname : ''; return r && r !== location.hostname ? r : null; } catch (e) { return null; }
}
/* Registra um evento de uso do site. No app local (e com Do Not Track) não faz nada. Nunca atrapalha a página. */
function registrarEvento(tipo, dados = {}) {
  if (!window.LI_PUBLIC_MODE || _naoRastrear() || /^(localhost|127\.|0\.0\.0\.0|\[::1\])/.test(location.hostname)) return;   // testes locais não contam
  const corpo = { p_tipo: tipo, p_aba: (typeof S !== 'undefined' && S.aba) || null, p_sessao: _sessao(), p_novo: _primeiraVisita(), p_origem: _origem(), p_utm: _utm(),
    p_dispositivo: window.matchMedia && window.matchMedia('(max-width: 880px)').matches ? 'celular' : 'computador',
    p_idioma: (navigator.language || '').slice(0, 10), p_host: location.hostname, p_dados: dados };
  _rpc('registrar_evento', corpo).catch(() => { /* sem rede ou bloqueador: tudo bem */ });
}
/* Um evento por chave por sessão (ex.: qual hardware a pessoa configurou). */
const _jaEnviados = new Set();
function registrarUmaVez(chave, tipo, dados) { if (_jaEnviados.has(chave)) return; _jaEnviados.add(chave); registrarEvento(tipo, dados); }

// ---------------------------------------------------------------- e-mail (site e app)
function _hardwareAtual() {
  try {
    if (window.LI_PUBLIC_MODE && typeof LI_CALC_UI !== 'undefined' && window.LI_DADOS) return LI_CALC_UI.perfilDe(LI_CALC_UI.estadoInicial(window.LI_DADOS), window.LI_DADOS).nome;
    if (typeof S !== 'undefined' && S.mesa && S.mesa.boss) { const b = S.mesa.boss; return b.gpu ? `${b.gpu.nome} · ${b.ram_gb} GB` : `Sem GPU · ${b.ram_gb} GB`; }
  } catch (e) { /* ok */ }
  return null;
}
/* Formulário discreto: um campo, um botão e o texto do consentimento. */
function formLead(origem) {
  const hw = _hardwareAtual();
  const entrada = h('input', { type: 'email', required: true, placeholder: 'seu@email.com', autocomplete: 'email', 'aria-label': 'Seu e-mail' });
  const botao = h('button', { type: 'submit', class: 'btn primario' }, 'Quero o aviso');
  const status = h('span', { class: 'lead-status', role: 'status' });
  const form = h('form', { class: 'lead-form', onsubmit: async ev => {
    ev.preventDefault();
    botao.disabled = true; status.textContent = 'Enviando…';
    try {
      await _rpc('registrar_lead', { p_email: entrada.value, p_consentimento: CONSENTIMENTO_LEAD, p_interesse: hw ? 'alerta-hardware' : 'novidades', p_hardware: hw, p_origem: (window.LI_PUBLIC_MODE ? 'site' : 'app') + ':' + origem });
      registrarEvento('lead', { origem });
      form.replaceChildren(h('div', { class: 'lead-ok' }, '✓ Combinado! Quando sair um modelo que vale a pena para o seu computador, você fica sabendo.'));
    } catch (e) {
      botao.disabled = false;
      status.textContent = /e-mail/.test(e.message) ? 'Confira o e-mail digitado.' : 'Não consegui enviar agora. Tente de novo mais tarde.';
    }
  } }, h('div', { class: 'lead-linha' }, entrada, botao), status);
  return h('div', { class: 'lead' },
    h('div', { class: 'lead-titulo' }, '✉ ', h('b', {}, 'Saiu um modelo melhor para o seu computador?'), ' Receba um aviso.'),
    hw ? h('div', { class: 'sub lead-hw' }, 'Para: ', h('b', {}, hw)) : null,
    form,
    h('p', { class: 'sub lead-consent' }, 'Até 1 e-mail por mês, nada de spam. Seu e-mail fica só com o projeto e você sai quando quiser. ', h('a', { href: '#', onclick: ev => { ev.preventDefault(); abrirPrivacidade(); } }, 'Privacidade')));
}

function abrirPrivacidade() {
  abrirDialogo(h('div', { class: 'dlg-in', style: 'max-width:640px' },
    h('h2', {}, 'Privacidade'),
    h('ul', { class: 'apoio-lista privacidade' },
      h('li', {}, h('b', {}, 'Sem cookies e sem IP. '), 'No site, contamos visitas de forma anônima: a aba vista, de qual site você veio (só o domínio), se é celular ou computador e um número aleatório que some ao fechar a aba. Com “Do Not Track” ligado no navegador, nada é contado.'),
      h('li', {}, h('b', {}, 'Seu hardware fica no navegador. '), 'A configuração da calculadora é salva só no seu navegador.'),
      h('li', {}, h('b', {}, 'E-mail só se você pedir. '), 'Se você se inscrever, guardamos o e-mail, o hardware que você escolheu e o texto que aceitou. Ele não é vendido nem compartilhado. Para sair, responda qualquer e-mail.'),
      h('li', {}, h('b', {}, 'App local é privado. '), 'O app não manda nada sozinho. Resultados de benchmark só saem quando você clica em “Enviar para a comunidade”, depois de ver o que vai.')),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
}

// ---------------------------------------------------------------- benchmarks da comunidade (app)
/* Monta o envio a partir do que o painel já sabe: hardware desta máquina (sem nome) e resultados medidos de cada modelo. */
function montarBenchmarks() {
  const m = typeof S !== 'undefined' ? S.mesa : null;
  if (!m || !m.boss) return [];
  const b = m.boss;
  const hardware = { gpu: b.gpu ? b.gpu.nome : null, vram_gb: b.gpu ? b.gpu.vram_gb : null, unificada: !!b.unificada, ram_gb: b.ram_gb, cpu: b.cpu || null, nucleos: b.nucleos || null, simd: b.simd || [], so: String(b.so || '').split(' ')[0] || null, arquitetura: b.arquitetura || null };
  return (m.instalados || []).filter(x => x.medido && x.medido.papeis).map(x => {
    const r = x.medido, papeis = {}, suites = {};
    for (const [pid, v] of Object.entries(r.papeis || {})) if (v && v.nota != null) papeis[pid] = { nota: v.nota, ic: v.ic || null };
    for (const [s, v] of Object.entries(r.suites || {})) suites[s] = { n: v.n, acc: v.acc };
    return { modelo: x.id, digest: (x.digest || '').slice(0, 64), quant: x.quant || null, bytes: x.bytes || null,
      protocolo: (S.saude && S.saude.protocolo) || null, versao_app: (S.saude && S.saude.versao_painel) || null, nivel: r.modo || null,
      hardware, resultado: { papeis, suites, tps: r.tps_mediana || null, itens: r.n_itens || null } };
  }).filter(x => Object.keys(x.resultado.papeis).length);
}
async function enviarBenchmarks(lista) {
  let ok = 0;
  for (const p of lista) { await _rpc('enviar_benchmark', { p }); ok++; }
  return ok;
}
/* Cartão "Compartilhar com a comunidade" (aba Medir do app). */
function cartaoComunidade() {
  if (window.LI_PUBLIC_MODE) return null;
  const lista = montarBenchmarks();
  const corpo = h('div', { class: 'empilha', style: 'gap:10px' });
  const enviado = (() => { try { return JSON.parse(localStorage.getItem('li-bench-enviados') || '{}'); } catch (e) { return {}; } })();
  const chaveDe = p => p.modelo + '|' + p.digest + '|' + (p.resultado.itens || 0);
  const pendentes = lista.filter(p => !enviado[chaveDe(p)]);
  if (!lista.length) {
    corpo.append(h('p', { class: 'sub' }, 'Quando você medir um modelo, pode compartilhar o resultado aqui, de forma anônima. Com resultados de muita gente, o site passa a mostrar notas medidas em hardware de verdade, não só estimativas.'));
  } else {
    const prev = h('pre', { class: 'comunidade-previa' }, JSON.stringify(pendentes.length ? pendentes : lista, null, 2));
    const botao = h('button', { class: 'btn primario', disabled: !pendentes.length }, pendentes.length ? `Enviar ${pendentes.length} resultado(s) para a comunidade` : '✓ Tudo já enviado');
    const status = h('span', { class: 'sub' });
    botao.onclick = async () => {
      botao.disabled = true; status.textContent = 'Enviando…';
      try {
        const n = await enviarBenchmarks(pendentes);
        for (const p of pendentes) enviado[chaveDe(p)] = Date.now();
        try { localStorage.setItem('li-bench-enviados', JSON.stringify(enviado)); } catch (e) { /* ok */ }
        status.textContent = ''; botao.textContent = `✓ ${n} resultado(s) enviado(s). Obrigado!`;
        if (typeof momentoDeValor === 'function') momentoDeValor('medicao');
      } catch (e) { botao.disabled = false; status.textContent = 'Não consegui enviar agora (sem internet?). Tente de novo depois.'; }
    };
    corpo.append(
      h('p', { class: 'sub' }, `${lista.length} modelo(s) medido(s) neste computador. Vai junto: placa, memória, processador e sistema (sem o nome da máquina) e as notas, sem nenhuma pergunta ou resposta dos testes.`),
      h('details', {}, h('summary', {}, 'Ver exatamente o que será enviado'), prev),
      h('div', { class: 'linha', style: 'justify-content:flex-start;gap:10px;flex-wrap:wrap' }, botao, status));
  }
  return h('div', { class: 'cartao comunidade' },
    h('div', { class: 'linha', style: 'justify-content:flex-start;gap:12px' }, h('span', { class: 'previa-ic', style: '--cor-d:#10b981' }, '🤝'), h('div', {}, h('h3', {}, 'Compartilhar resultados com a comunidade'), h('div', { class: 'sub' }, 'Opcional, anônimo e só quando você clicar.'))),
    corpo);
}
