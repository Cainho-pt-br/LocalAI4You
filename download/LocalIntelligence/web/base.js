'use strict';
/* Helpers compartilhados pelo painel e pelo arquivo autônomo da calculadora. Sem dependências e sem rede externa.
   Segurança: todo texto vindo de fora (Ollama / Hugging Face / radar) entra no DOM por textContent (função h), nunca por innerHTML. */

const $ = (s, el = document) => el.querySelector(s);
// replaceChildren aceita listas aninhadas e ignora null/false (senão o DOM mostraria o texto "null")
const _normaliza = kids => kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false).map(k => (k && k.nodeType) ? k : document.createTextNode(String(k)));
const _rc = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...kids) { return _rc.apply(this, _normaliza(kids)); };
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'open') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === undefined || kid === null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
/* Máquina que o painel está controlando ('' = esta). Com uma máquina remota escolhida, toda chamada /api/... vai para o painel dela
   (o servidor local repassa em /api/m/<id>/...), exceto o que é sempre local: calculadora, parque, quantizações e a própria lista de máquinas. */
const LI = { alvo: '' };
// Endereços do projeto (um lugar só para trocar). O ZIP vem do GitHub Releases: só o app, sem o site.
const LINK_REPO = 'https://github.com/Cainho-pt-br/LocalAI4You';
// Windows baixa o pacote com o Python oficial embutido e o "Instalar"; macOS e Linux, o ZIP com o atalho de abrir.
/* Canais do projeto (vídeos e comunidade). Preencha com o endereço completo (https://…) os que existirem; os vazios
   não aparecem em lugar nenhum. Aparecem no rodapé do site, nas páginas por placa e na janela "Apoiar o projeto". */
const CANAIS = { youtube: '', tiktok: '', instagram: '', discord: '', x: '' };
const CANAIS_NOME = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram', discord: 'Discord', x: 'X' };
function linksCanais(origem) {
  return Object.keys(CANAIS).filter(k => /^https:\/\//.test(CANAIS[k])).map(k => h('a', { href: CANAIS[k], target: '_blank', rel: 'noopener', 'data-sem-traducao': '',
    onclick: () => { if (typeof registrarEvento === 'function') registrarEvento('uso', { acao: 'canal', canal: k, origem: origem || null }); } }, CANAIS_NOME[k] + ' ↗'));
}
const NO_WINDOWS = /Windows/i.test(navigator.userAgent || '');
const LINK_STORE = 'https://apps.microsoft.com/detail/9MWFSJPFFMJW';
const LINK_ZIP = LINK_REPO + '/releases/latest/download/' + (NO_WINDOWS ? 'LocalAI4You-Windows.zip' : 'LocalAI4You.zip');
// No Windows o caminho principal é a Microsoft Store (sem aviso do SmartScreen); o ZIP fica como alternativa.
const LINK_DOWNLOAD = NO_WINDOWS ? LINK_STORE : LINK_ZIP;
const ROTAS_LOCAIS = ['/api/calc/', '/api/maquinas', '/api/parque', '/api/m/', '/api/quants', '/api/radar/snapshot'];
const caminhoAlvo = c => (!LI.alvo || !c.startsWith('/api/') || ROTAS_LOCAIS.some(p => c.startsWith(p))) ? c : '/api/m/' + encodeURIComponent(LI.alvo) + c.slice(4);
async function api(caminho, corpo) {
  caminho = caminhoAlvo(caminho);
  const opts = corpo === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-LI': '1' }, body: JSON.stringify(corpo) };
  let r;
  try { r = await fetch(caminho, opts); }
  catch (e) { throw new Error(window.LI_PUBLIC_MODE ? 'Sem conexão. Confira a internet e tente de novo.' : 'O painel não respondeu. Confira se a janela do Local AI 4 You continua aberta.'); }
  let d = {};
  try { d = await r.json(); } catch (e) { /* corpo vazio */ }
  if (!r.ok) throw new Error(d.erro || ('HTTP ' + r.status));
  return d;
}

// ---------------------------------------------------------------- formatação
const fmtGB = b => (b / 1e9).toFixed(1).replace('.', ',') + ' GB';
const fmtN = (n, c = 0) => Number(n).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
const fmtCtx = n => !n ? '—' : n >= 1048576 ? (n % 1048576 === 0 ? (n / 1048576) + 'M' : (n / 1048576).toFixed(1) + 'M') : n >= 1024 ? Math.round(n / 1024) + 'k' : String(n);
const fmtIdade = d => d == null ? 'data desconhecida' : d < 1 ? 'hoje' : d < 60 ? `há ${Math.floor(d)} dias` : d < 700 ? `há ${Math.floor(d / 30)} meses` : `há ${(d / 365).toFixed(1).replace('.', ',')} anos`;
const fmtTps = t => t ? `${fmtN(t[0], t[0] < 10 ? 1 : 0)}–${fmtN(t[1], t[1] < 10 ? 1 : 0)}` : '?';
const fmtData = iso => (iso || '').slice(0, 10).split('-').reverse().join('/');
const fmtGiB = g => fmtN(g, 1) + ' GB';

function formatarNomeModelo(id) {
  if (!id) return { nome: '—', quant: null, original: '' };
  const orig = String(id).trim();
  let s = orig;
  let quant = null;
  if (s.includes(':')) {
    const p = s.split(':');
    quant = p.slice(1).join(':');
    s = p[0];
  }
  s = s.replace(/^(https?:\/\/)?(hf\.co\/|huggingface\.co\/)/i, '').replace(/^hf:/i, '');
  if (s.includes('/')) s = s.split('/').pop();
  s = s.replace(/[-_]GGUF$/i, '');
  s = s.replace(/[-_]it$/i, '');
  s = s.replace(/[-_]Instruct$/i, '');
  s = s.replace(/[-_]chat$/i, '');

  if (orig.startsWith('hf.co/') || orig.startsWith('huggingface.co/')) {
    return { nome: s, quant: quant || null, original: orig };
  }
  return { nome: orig, quant: quant || null, original: orig };
}

function nomeAmigavelModelo(id) {
  return formatarNomeModelo(id).nome;
}
function tagQuantModelo(id) {
  return formatarNomeModelo(id).quant;
}

// ---------------------------------------------------------------- componentes
function toast(msg, ms = 5000) {
  const t = h('div', { class: 'toast', role: 'status' }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}
async function copiar(txt) {
  try { await navigator.clipboard.writeText(txt); toast('Copiado: ' + (txt.length > 90 ? txt.slice(0, 90) + '…' : txt)); } catch (e) { toast('Não consegui copiar — selecione o texto.'); return; }
  if (typeof momentoDeValor === 'function' && /^ollama /.test(txt)) momentoDeValor('copiou');   // apoio.js (só no painel e no site)
  if (typeof registrarEvento === 'function' && /^ollama /.test(txt)) registrarEvento('copiar', { comando: txt.slice(0, 160) });   // coleta.js (métrica anônima, só no site)
}
const chip = (txt, cls = 'neutro', titulo) => h('span', { class: 'chip ' + cls, title: titulo }, txt);
const CHIP_MEDIDO = () => chip('MEDIDO', 'medido', 'Rodou aqui, no protocolo v2, com intervalo de confiança');
const CHIP_ESTIMADO = () => chip('ESTIMADO', 'estimado', 'Conta de memória/velocidade com arquivos reais; não é medição');
const CHIP_PRIO = () => chip('PRIORIDADE', 'prioridade', 'Heurística de “vale testar?”. NÃO é nota de qualidade.');
const notaClasse = n => n >= 80 ? 'alto' : n >= 65 ? 'medio' : n >= 50 ? 'baixo' : 'ruim';
function cmd(texto) {
  return h('div', { class: 'cmd' }, h('code', {}, texto), h('button', { class: 'btn mini', onclick: () => copiar(texto) }, 'Copiar'));
}
function titulo(txt, sub, ...extra) {
  return h('div', { class: 'sec-titulo' }, h('div', {}, h('h2', {}, txt), sub ? h('div', { class: 'sub' }, sub) : null), extra.length ? h('div', { class: 'sec-extra' }, ...extra) : null);
}
// Links externos só para os dois sites de modelos, sempre em nova aba e sem enviar referência.
const HOSTS_OK = new Set(['huggingface.co', 'ollama.com']);
const urlHF = repo => 'https://huggingface.co/' + String(repo).split('/').map(encodeURIComponent).join('/');
function linkExterno(url, texto, cls = 'btn mini') {
  let ok = false;
  try { const u = new URL(url); ok = u.protocol === 'https:' && HOSTS_OK.has(u.hostname); } catch (e) { ok = false; }
  if (!ok) return null;
  return h('a', { class: cls + ' ext', href: url, target: '_blank', rel: 'noopener noreferrer' }, texto, h('span', { class: 'seta', 'aria-hidden': 'true' }, '↗'));
}
function legendaSelos() {
  return h('div', { class: 'legenda' }, 'Selos:', CHIP_MEDIDO(), 'rodou aqui, com margem de erro', CHIP_ESTIMADO(), 'conta com arquivos reais', CHIP_PRIO(), 'só diz se vale testar');
}

// ---------------------------------------------------------------- diálogo (criado sob demanda: o arquivo autônomo não tem <dialog> no HTML)
function _dlg() {
  let d = document.getElementById('dlg');
  if (!d) {
    d = h('dialog', { id: 'dlg' }, h('div', { class: 'dlg-in', id: 'dlg-in' }));
    d.addEventListener('click', e => { if (e.target === d) d.close(); });
    document.body.append(d);
  }
  return d;
}
function abrirDialogo(conteudo) {
  const d = _dlg();
  d.querySelector('#dlg-in').replaceWith(Object.assign(conteudo, { id: 'dlg-in' }));
  if (!d.open) d.showModal();
}
function fecharDialogo() { const d = document.getElementById('dlg'); if (d && d.open) d.close(); }
document.addEventListener('click', e => { if (e.target && e.target.id === 'dlg') fecharDialogo(); });
