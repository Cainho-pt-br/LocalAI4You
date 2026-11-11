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
  awin: { awinId: '', lojas: { kabum: '', pichau: '' } },
};

const _slug = s => String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
function _awin(loja, url) {
  const a = LOJAS_CONFIG.awin, mid = a.lojas[loja];
  return a.awinId && mid ? `https://www.awin1.com/cread.php?awinmid=${encodeURIComponent(mid)}&awinaffid=${encodeURIComponent(a.awinId)}&ued=${encodeURIComponent(url)}` : url;
}
function lojasComAfiliado() {
  const a = LOJAS_CONFIG.awin;
  return !!(LOJAS_CONFIG.amazonTag || (a.awinId && Object.values(a.lojas).some(Boolean)));
}
/* Lojas para um produto (texto de busca, ex.: "RTX 5060 Ti 16GB"). */
function lojasPara(busca) {
  const q = encodeURIComponent(busca);
  return [
    ['Amazon', `https://www.amazon.com.br/s?k=${q}` + (LOJAS_CONFIG.amazonTag ? `&tag=${encodeURIComponent(LOJAS_CONFIG.amazonTag)}` : ''), !!LOJAS_CONFIG.amazonTag],
    ['KaBuM', _awin('kabum', `https://www.kabum.com.br/busca/${_slug(busca)}`), !!(LOJAS_CONFIG.awin.awinId && LOJAS_CONFIG.awin.lojas.kabum)],
    ['Pichau', _awin('pichau', `https://www.pichau.com.br/search?q=${q}`), !!(LOJAS_CONFIG.awin.awinId && LOJAS_CONFIG.awin.lojas.pichau)],
    ['Mercado Livre', `https://lista.mercadolivre.com.br/${_slug(busca)}`, false],
  ];
}
/* Botões de loja; `contexto` vai para as métricas (qual placa, de onde veio o clique). */
function botoesLoja(busca, contexto = {}) {
  return h('div', { class: 'lojas' }, lojasPara(busca).map(([nome, url, afiliado]) =>
    h('a', { class: 'loja', href: url, target: '_blank', rel: afiliado ? 'sponsored noopener' : 'noopener',
      onclick: () => { if (typeof registrarEvento === 'function') registrarEvento('loja', { loja: nome, busca, ...contexto }); } }, nome, ' ↗')));
}
function avisoLojas() {
  return h('p', { class: 'sub aviso-lojas' }, lojasComAfiliado()
    ? 'Alguns links de loja são de afiliado: se você comprar por eles, o projeto pode receber uma pequena comissão, sem custo a mais para você. Isso não muda a ordem das recomendações.'
    : 'Links de busca nas lojas, sem patrocínio. Compare preços e confira a quantidade de memória (VRAM) antes de comprar.');
}
