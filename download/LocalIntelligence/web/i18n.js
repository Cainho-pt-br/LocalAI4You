'use strict';
/* Tradução da interface (inglês e espanhol). O código continua escrito em português; esta camada troca os textos que
   aparecem na tela usando os dicionários de i18n-dados.js:
     1. frase exata;
     2. a mesma frase com os números trocados por {n} (ex.: "{n} modelos cabem");
     3. regras por trechos, para textos montados em partes (descrições de modelos, listas de usos…).
   O que não estiver no dicionário fica em português. Idioma: o escolhido no seletor (guardado no navegador) ou o do
   navegador/sistema; português é o padrão. */
(function () {
  const IDIOMAS = { pt: 'Português', en: 'English', es: 'Español' };
  const CHAVE = 'li-idioma';
  function detectar() {
    try { const s = localStorage.getItem(CHAVE); if (s && IDIOMAS[s]) return s; } catch (e) { /* ok */ }
    for (const l of (navigator.languages || [navigator.language || 'pt'])) {
      const b = String(l).toLowerCase().slice(0, 2);
      if (b === 'pt') return 'pt';
      if (b === 'es') return 'es';
      if (b === 'en') return 'en';
    }
    return 'en';   // fora de pt/es, inglês é a melhor aposta
  }
  const LANG = detectar();
  window.LI_IDIOMA = LANG;
  window.LI_IDIOMAS = IDIOMAS;
  window.trocarIdioma = l => { try { localStorage.setItem(CHAVE, l); } catch (e) { /* ok */ } location.reload(); };
  document.documentElement.lang = LANG === 'pt' ? 'pt-BR' : LANG;
  if (LANG === 'pt') return;

  const col = LANG === 'en' ? 1 : 2;
  const exatas = new Map(), modelos = new Map();
  const NUM = /\d+(?:[.,]\d+)?/g;
  for (const linha of (window.LI_I18N_DADOS || [])) {
    const alvo = linha[col]; if (!alvo) continue;
    (linha[0].includes('{n}') ? modelos : exatas).set(linha[0], alvo);
  }
  const regras = (window.LI_I18N_REGRAS || []).map(r => [new RegExp(r[0], r[3] || 'g'), r[col]]).filter(r => r[1] != null);
  const fmtNum = n => LANG === 'en' ? n.replace(/(\d),(\d)/, '$1.$2') : n;

  function traduzir(texto) {
    const t = texto.trim();
    if (!t || !/[A-Za-zÀ-ú]/.test(t)) return LANG === 'en' ? texto.replace(/(\d),(\d{1,2})(?!\d)/g, '$1.$2') : texto;
    let r = exatas.get(t);
    if (r == null) {
      const nums = t.match(NUM) || [];
      const m = nums.length ? modelos.get(t.replace(NUM, '{n}')) : null;
      if (m != null) { let i = 0; r = m.replace(/\{n\}/g, () => fmtNum(nums[i++] ?? '')); }
    }
    if (r == null) {
      let s = t;
      for (const [re, sub] of regras) s = s.replace(re, sub);
      // só aceita se não sobrar português no meio (melhor a frase inteira em pt do que uma mistura)
      if (s !== t && !/ção|ções|[ãõ]|\b(não|você|seu|sua|uma|também|placa|apenas|está)\b/i.test(s)) r = LANG === 'en' ? s.replace(/(\d),(\d{1,2})(?!\d)/g, '$1.$2') : s;
    }
    if (r == null) return LANG === 'en' ? texto.replace(/(\d),(\d)/g, '$1.$2') : texto;
    const ini = texto.match(/^\s*/)[0], fim = texto.match(/\s*$/)[0];
    return ini + r + fim;
  }
  window.LI_T = traduzir;

  const FEITO = new WeakMap();
  const ATTRS = ['placeholder', 'title', 'aria-label'];
  function noTexto(n) {
    const pe = n.parentElement;
    if (!pe || pe.closest('script,style,code,pre,.cmd,[data-sem-traducao]')) return;
    const v = n.nodeValue;
    if (FEITO.get(n) === v) return;
    const nv = traduzir(v);
    if (nv !== v) n.nodeValue = nv;
    FEITO.set(n, nv);
  }
  function elemento(el) {
    if (el.closest && el.closest('[data-sem-traducao]')) return;
    for (const a of ATTRS) { const v = el.getAttribute && el.getAttribute(a); if (v) { const nv = traduzir(v); if (nv !== v) el.setAttribute(a, nv); } }
  }
  function varrer(raiz) {
    if (raiz.nodeType === 3) return noTexto(raiz);
    if (raiz.nodeType !== 1) return;
    elemento(raiz);
    const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n; while ((n = w.nextNode())) n.nodeType === 3 ? noTexto(n) : elemento(n);
  }
  function iniciar() {
    document.title = traduzir(document.title);
    const md = document.querySelector('meta[name="description"]'); if (md) md.content = traduzir(md.content);
    varrer(document.body);
    new MutationObserver(ms => {
      for (const m of ms) {
        if (m.type === 'characterData') noTexto(m.target);
        else if (m.type === 'attributes') elemento(m.target);
        else m.addedNodes.forEach(varrer);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  // confirm()/alert() também passam pelo dicionário
  const conf = window.confirm.bind(window), ale = window.alert.bind(window);
  window.confirm = m => conf(traduzir(String(m)));
  window.alert = m => ale(traduzir(String(m)));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();

/* Seletor de idioma: um <select> pequeno. Recarrega a página ao trocar. */
function seletorIdioma(classe) {
  const s = document.createElement('select');
  s.className = 'seletor-idioma ' + (classe || '');
  s.setAttribute('aria-label', 'Idioma / Language / Idioma');
  s.setAttribute('data-sem-traducao', '');
  for (const [k, v] of Object.entries(window.LI_IDIOMAS || {})) { const o = document.createElement('option'); o.value = k; o.textContent = '🌐 ' + v; if (k === window.LI_IDIOMA) o.selected = true; s.appendChild(o); }
  s.addEventListener('change', () => window.trocarIdioma(s.value));
  return s;
}
// Onde houver data-idioma, entra o seletor.
(function () {
  const por = () => document.querySelectorAll('[data-idioma]').forEach(el => { if (!el.querySelector('.seletor-idioma')) el.appendChild(seletorIdioma()); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', por); else por();
})();
