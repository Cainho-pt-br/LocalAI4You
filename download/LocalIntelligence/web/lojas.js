'use strict';
/* Links de loja para upgrade de hardware (afiliados). Sem nenhum código preenchido, são só buscas comuns nas lojas.
   Para ganhar comissão, cadastre-se e preencha:
   • amazonTag: Amazon Associados Brasil (associados.amazon.com.br) → o "ID de rastreamento", ex.: 'localai4you20-20'.
   • awin: KaBuM, Pichau e outras lojas brasileiras usam a rede Awin (awin.com). Depois de aprovado em cada loja,
     preencha seu ID de afiliado (awinId) e o código de cada loja (awinmid).
   Quando houver algum código, a página mostra o aviso de que os links podem render comissão (exigência das lojas e
   questão de honestidade). Cliques são contados nas métricas anônimas do site, quando ativas. */
const LOJAS_CONFIG = {
  amazonTag: 'localai4you20-20',
  // Tags por loja Amazon (quando o site está em inglês ou espanhol, usa a loja correspondente se preenchida).
  amazonTags: { br: 'localai4you20-20', us: '', es: '' },
  awin: { awinId: '', lojas: { kabum: '', pichau: '' } },
  // Aluguel de GPU na nuvem (útil para quem tem PC sem placa ou pouca VRAM): preencha com seu link de afiliado.
  nuvem: [
    { nome: 'RunPod', url: '', desc: 'GPU sob demanda por hora' },
    { nome: 'Vast.ai', url: '', desc: 'Aluguel econômico de GPUs' },
  ],
  upgrades: ['rtx-5060', 'rtx-5070', 'rx-7600-xt', 'rtx-5060-ti-16', 'rtx-4090', 'rtx-5090'],
  // Mercado Livre: links curtos de afiliado (meli.la) são POR PRODUTO. Cada item liga um texto de busca (expressão
  // regular, sem diferenciar maiúsculas) ao link do produto; sem correspondência, o botão continua sendo uma busca comum.
  // A memória (VRAM) é o que importa aqui: só liga o link quando a versão do produto bate com a da placa sugerida.
  mercadolivre: [
    { busca: /7600 XT/i, marca: 'Pcyes', url: 'https://meli.la/2fJCp94' },                 // Pcyes RX 7600 XT 16GB
    { busca: /9050/i, marca: 'Gigabyte', url: 'https://meli.la/17ySqfT' },                     // Gigabyte RX 9050 Gaming OC 8GB
    { busca: /5060 Ti 8\s?GB/i, marca: 'Gainward', url: 'https://meli.la/1Tp8jFR' },          // Gainward RTX 5060 Ti 8GB
    { busca: /5060(?! Ti)/i, marca: 'MSI', url: 'https://meli.la/2bewuNP' },                  // MSI RTX 5060 8GB Shadow 2X OC
    { busca: /5060(?! Ti)/i, marca: 'Zotac', url: 'https://meli.la/1cWdy7S' },              // Zotac RTX 5060 Twin Edge 8GB
    { busca: /5070(?! Ti| Laptop)/i, marca: 'Zotac', url: 'https://meli.la/2SwxwKK' },      // Zotac RTX 5070 12GB
  ],
};

/* Atualização dinâmica de links: edite apenas `site/lojas.json` no GitHub para atualizar site + app (Store/ZIP)
   sem precisar gerar nova versão. Por segurança, só aceita URLs HTTPS de domínios oficiais de loja/nuvem. */
const LOJAS_CACHE_KEY = 'li-lojas-cache-v1';
const LOJAS_CACHE_MS = 6 * 3600 * 1000;
const HOSTS_LOJAS_OK = new Set([
  'amazon.com.br', 'www.amazon.com.br', 'amazon.com', 'www.amazon.com', 'amazon.es', 'www.amazon.es', 'amzn.to',
  'meli.la', 'mercadolivre.com.br', 'www.mercadolivre.com.br', 'lista.mercadolivre.com.br', 'produto.mercadolivre.com.br',
  'awin1.com', 'www.awin1.com', 'kabum.com.br', 'www.kabum.com.br', 'pichau.com.br', 'www.pichau.com.br',
  'runpod.io', 'www.runpod.io', 'vast.ai', 'cloud.vast.ai',
]);
function _urlLojaSegura(url) {
  try { const u = new URL(String(url || '')); return u.protocol === 'https:' && HOSTS_LOJAS_OK.has(u.hostname.toLowerCase()); }
  catch (e) { return false; }
}
function aplicarConfigLojas(d) {
  if (!d || typeof d !== 'object') return false;
  if (d.amazonTags && typeof d.amazonTags === 'object') {
    for (const k of ['br', 'us', 'es']) if (typeof d.amazonTags[k] === 'string') LOJAS_CONFIG.amazonTags[k] = d.amazonTags[k].trim();
    if (LOJAS_CONFIG.amazonTags.br) LOJAS_CONFIG.amazonTag = LOJAS_CONFIG.amazonTags.br;
  }
  if (d.awin && typeof d.awin === 'object') {
    if (typeof d.awin.awinId === 'string') LOJAS_CONFIG.awin.awinId = d.awin.awinId.trim();
    if (d.awin.lojas && typeof d.awin.lojas === 'object') {
      for (const [k, v] of Object.entries(d.awin.lojas)) if (typeof v === 'string') LOJAS_CONFIG.awin.lojas[k] = v.trim();
    }
  }
  if (Array.isArray(d.nuvem)) {
    LOJAS_CONFIG.nuvem = d.nuvem.filter(x => x && typeof x.nome === 'string' && (!x.url || _urlLojaSegura(x.url)))
      .map(x => ({ nome: x.nome.trim(), url: String(x.url || '').trim(), desc: String(x.desc || '').trim() }));
  }
  if (Array.isArray(d.upgrades) && d.upgrades.length) {
    const ids = d.upgrades.filter(x => typeof x === 'string' && /^[a-z0-9-]+$/i.test(x));
    if (ids.length) LOJAS_CONFIG.upgrades = ids;
  }
  if (Array.isArray(d.mercadolivre)) {
    const lista = [];
    for (const item of d.mercadolivre) {
      if (!item || typeof item.busca !== 'string' || !_urlLojaSegura(item.url)) continue;
      try { lista.push({ busca: new RegExp(item.busca, 'i'), marca: String(item.marca || '').trim(), url: item.url.trim() }); }
      catch (e) { /* regex inválida: ignora item */ }
    }
    if (lista.length) LOJAS_CONFIG.mercadolivre = lista;
  }
  return true;
}
function _urlLojasRemoto() {
  if (typeof location === 'undefined') return null;
  if (window.LI_PUBLIC_MODE) return '/lojas.json';
  return 'https://localai4you.vercel.app/lojas.json';
}
async function carregarLojasRemotas() {
  const url = _urlLojasRemoto();
  if (!url || typeof fetch !== 'function') return;
  let fresco = false;
  try {
    const raw = localStorage.getItem(LOJAS_CACHE_KEY);
    if (raw) {
      const c = JSON.parse(raw);
      if (c && c.dados) aplicarConfigLojas(c.dados);
      if (c && c.t && Date.now() - c.t < LOJAS_CACHE_MS) fresco = true;
    }
  } catch (e) { /* sem localStorage */ }
  if (fresco) return;
  try {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) return;
    const d = await r.json();
    if (aplicarConfigLojas(d)) {
      try { localStorage.setItem(LOJAS_CACHE_KEY, JSON.stringify({ t: Date.now(), dados: d })); } catch (e) { /* ok */ }
      if (typeof desenhar === 'function' && typeof S !== 'undefined' && (S.aba === 'radar' || S.aba === 'calculadora')) desenhar();
    }
  } catch (e) { /* offline: segue com o fallback embutido */ }
}

const _slug = s => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const _idiomaLojas = () => (typeof window !== 'undefined' && window.LI_IDIOMA) || (typeof document !== 'undefined' && (document.documentElement.lang || '').slice(0, 2)) || 'pt';
function _awin(loja, url) {
  const a = LOJAS_CONFIG.awin, mid = a.lojas[loja];
  return a.awinId && mid ? `https://www.awin1.com/cread.php?awinmid=${encodeURIComponent(mid)}&awinaffid=${encodeURIComponent(a.awinId)}&ued=${encodeURIComponent(url)}` : url;
}
function lojasComAfiliado() {
  const a = LOJAS_CONFIG.awin;
  const tags = LOJAS_CONFIG.amazonTags || {};
  return !!(LOJAS_CONFIG.amazonTag || tags.br || tags.us || tags.es || LOJAS_CONFIG.mercadolivre.length ||
    (LOJAS_CONFIG.nuvem || []).some(n => /^https:\/\//.test(n.url)) || (a.awinId && Object.values(a.lojas).some(Boolean)));
}
/* Lojas para um produto (texto de busca, ex.: "RTX 5060 Ti 16GB"). */
function lojasPara(busca) {
  const q = encodeURIComponent(busca);
  const lang = _idiomaLojas();
  const tags = LOJAS_CONFIG.amazonTags || {};
  if (lang === 'en') {
    const tag = tags.us || '';
    return [['Amazon', `https://www.amazon.com/s?k=${q}` + (tag ? `&tag=${encodeURIComponent(tag)}` : ''), !!tag]];
  }
  if (lang === 'es') {
    const tag = tags.es || '';
    return [['Amazon', `https://www.amazon.es/s?k=${q}` + (tag ? `&tag=${encodeURIComponent(tag)}` : ''), !!tag]];
  }
  const tagBr = tags.br || LOJAS_CONFIG.amazonTag || '';
  const mls = LOJAS_CONFIG.mercadolivre.filter(x => x.busca.test(busca));   // mais de um produto da mesma placa: um botão por marca
  // KaBuM e Pichau só aparecem quando há código de afiliado delas (sem comissão, o botão só ocuparia espaço).
  return [
    ['Amazon', `https://www.amazon.com.br/s?k=${q}` + (tagBr ? `&tag=${encodeURIComponent(tagBr)}` : ''), !!tagBr],
    ['KaBuM', _awin('kabum', `https://www.kabum.com.br/busca/${_slug(busca)}`), !!(LOJAS_CONFIG.awin.awinId && LOJAS_CONFIG.awin.lojas.kabum), true],
    ['Pichau', _awin('pichau', `https://www.pichau.com.br/search?q=${q}`), !!(LOJAS_CONFIG.awin.awinId && LOJAS_CONFIG.awin.lojas.pichau), true],
    ...(mls.length ? mls.map(m => [mls.length > 1 && m.marca ? 'Mercado Livre · ' + m.marca : 'Mercado Livre', m.url, true])
      : [['Mercado Livre', `https://lista.mercadolivre.com.br/${_slug(busca)}`, false]]),
  ].filter(l => !l[3] || l[2]);
}
/* Botões de loja; `contexto` vai para as métricas (qual placa, de onde veio o clique). */
function botoesLoja(busca, contexto = {}) {
  return h('div', { class: 'lojas' }, lojasPara(busca).map(([nome, url, afiliado]) =>
    h('a', { class: 'loja' + (afiliado ? ' loja-af' : ''), href: url, target: '_blank', rel: afiliado ? 'sponsored noopener' : 'noopener',
      onclick: () => { if (typeof registrarEvento === 'function') registrarEvento('loja', { loja: nome, busca, ...contexto }); } }, 'Ver preço · ', nome, ' ↗')));
}
/* Botões de GPU na nuvem (só aparecem quando há URL preenchida em LOJAS_CONFIG.nuvem). */
function botoesNuvem(contexto = {}) {
  const ativos = (LOJAS_CONFIG.nuvem || []).filter(n => _urlLojaSegura(n.url));
  if (!ativos.length) return null;
  return h('div', { class: 'lojas' }, ativos.map(n =>
    h('a', { class: 'loja loja-af', href: n.url, target: '_blank', rel: 'sponsored noopener', title: n.desc || '',
      onclick: () => { if (typeof registrarEvento === 'function') registrarEvento('loja', { loja: n.nome, busca: 'GPU na nuvem', ...contexto }); } }, 'Alugar GPU · ', n.nome, ' ↗')));
}
function avisoLojas() {
  return h('p', { class: 'sub aviso-lojas' }, lojasComAfiliado()
    ? 'Alguns links de loja são de afiliado: se você comprar por eles, o projeto pode receber uma pequena comissão, sem custo a mais para você. Isso não muda a ordem das recomendações.'
    : 'Links de busca nas lojas, sem patrocínio. Compare preços e confira a quantidade de memória (VRAM) antes de comprar.');
}

if (typeof window !== 'undefined') setTimeout(carregarLojasRemotas, 400);
