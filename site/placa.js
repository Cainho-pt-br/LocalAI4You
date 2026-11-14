'use strict';
/* Páginas por placa: copiar o comando, botões de loja (só nas páginas em português) e eventos anônimos. */
(function () {
  const pg = document.body.dataset;
  const ev = (tipo, dados) => { if (typeof registrarEvento === 'function') registrarEvento(tipo, dados); };
  ev('pagina', { aba: 'placa', hardware: pg.hw, idioma: pg.idioma });

  document.addEventListener('click', e => {
    const b = e.target.closest('[data-copiar]');
    if (b) {
      const txt = b.dataset.copiar, antes = b.dataset.rotulo || (b.dataset.rotulo = b.textContent);
      const feito = () => { b.textContent = pg.copiado || '✓'; setTimeout(() => { b.textContent = antes; }, 1800); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(feito, () => {});
      ev('copiar', { comando: txt.slice(0, 160), origem: 'pagina-placa', hardware: pg.hw });
      return;
    }
    const a = e.target.closest('[data-ev]');
    if (a) ev('uso', { acao: 'cta', origem: 'placa-' + a.dataset.ev, hardware: pg.hw });
  });

  const rodape = document.querySelector('.l-rodape nav');
  if (rodape && typeof linksCanais === 'function') rodape.append(...linksCanais('pagina-placa'));

  const lj = document.querySelector('[data-lojas]');
  if (lj && typeof botoesLoja === 'function') {
    lj.append(botoesLoja(lj.dataset.lojas, { origem: 'pagina-placa', hardware: pg.hw }));
    if (typeof avisoLojas === 'function') lj.append(avisoLojas());
  }
})();
