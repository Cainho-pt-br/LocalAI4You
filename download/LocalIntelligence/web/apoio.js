'use strict';
/* Apoio ao projeto, sempre presente e sem atrapalhar:
   • um link pequeno no rodapé da barra lateral (no celular, no pé da página);
   • um bloco discreto no fim do Radar;
   • uma linha compacta depois de cada momento em que a ferramenta ajudou (copiar um comando, terminar uma medição
     ou um duelo). Ela não cobre nada importante, nunca empilha, some sozinha em poucos segundos e o ✕ a esconde
     até o fim da visita. Nada é rastreado nem enviado.
   Para ativar doações, preencha APOIO abaixo (chave Pix e/ou um link como GitHub Sponsors, Ko-fi ou Apoia.se). */
const APOIO = {
  pix: '636ca1e2-6635-4ca0-8e6e-0f7d4873bf6c',   // chave Pix aleatória
  link: 'https://nubank.com.br/cobrar/4orxp/6af4d048-69bc-49ec-bb90-8b75f637dfde',   // pedido de Pix com QR code (Nubank)
  linkRotulo: 'Doar via Pix (QR code)',
};
const APOIO_SESSAO = 'li-apoio-oculto';   // ✕ esconde só nesta visita
const APOIO_SEGUNDOS = 7;

function _apoioOculto() { try { return sessionStorage.getItem(APOIO_SESSAO) === '1'; } catch (e) { return false; } }
function _apoioOcultar() { try { sessionStorage.setItem(APOIO_SESSAO, '1'); } catch (e) { /* navegação privada */ } }

function abrirApoio() {
  if (typeof registrarEvento === 'function') registrarEvento('apoio', {});
  const linhas = [
    h('li', {}, '⭐ ', h('a', { href: LINK_REPO, target: '_blank', rel: 'noopener' }, 'Dar uma estrela no GitHub'), ' — ajuda outras pessoas a encontrar o projeto.'),
    h('li', {}, '💬 ', h('a', { href: LINK_REPO + '/issues', target: '_blank', rel: 'noopener' }, 'Contar o que achou ou relatar um problema'), '.'),
    h('li', {}, '🔗 Mostrar para quem está começando com IA local.'),
  ];
  const canais = typeof linksCanais === 'function' ? linksCanais('apoio') : [];
  if (canais.length) linhas.push(h('li', {}, '📣 Acompanhar o projeto:', ' ', canais.flatMap((a, i) => i ? [' · ', a] : [a])));
  const doar = [];
  if (APOIO.pix) doar.push(h('div', { class: 'cmd' }, h('code', {}, 'Pix: ' + APOIO.pix), h('button', { class: 'btn mini', onclick: () => navigator.clipboard.writeText(APOIO.pix).then(() => toast('Chave Pix copiada. Obrigado!'), () => toast('Não consegui copiar — selecione o texto.')) }, 'Copiar chave')));
  if (APOIO.link) doar.push(h('a', { class: 'btn primario', href: APOIO.link, target: '_blank', rel: 'noopener' }, APOIO.linkRotulo));
  abrirDialogo(h('div', { class: 'dlg-in apoio-dlg' },
    h('h2', {}, '♥ Apoiar o Local AI 4 You'),
    h('p', { class: 'sub' }, 'O projeto é gratuito, de código aberto e feito no tempo livre. Se ele te poupou tempo, qualquer uma destas ajuda:'),
    h('ul', { class: 'apoio-lista' }, linhas),
    doar.length ? [h('h3', {}, '☕ Doação (opcional)'), h('p', { class: 'sub' }, 'Ajuda a pagar o tempo de manutenção e os testes em hardware novo. Qualquer valor é bem-vindo.'), ...doar] : null,
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
}

function desenharApoio() {
  const el = document.getElementById('apoio');
  if (el) el.replaceChildren(h('button', { type: 'button', class: 'apoio-link', onclick: abrirApoio, title: 'Como ajudar o projeto' }, '♥ Apoiar o projeto'));
  // rodapé de todas as abas: apoio (discreto e voluntário)
  const main = document.querySelector('main');
  if (main && !main.querySelector('.rodape-global')) main.appendChild(h('footer', { class: 'rodape-global' },
    blocoApoio()));
}

/* Bloco fixo e discreto para o fim de páginas longas (Radar). */
function blocoApoio() {
  return h('aside', { class: 'apoio-bloco' },
    h('span', { class: 'apoio-coracao', 'aria-hidden': 'true' }, '♥'),
    h('div', { class: 'grow' }, h('b', {}, 'O Local AI 4 You é gratuito e de código aberto.'),
      h('span', { class: 'sub' }, ' Se ele te ajudou a escolher, dá para apoiar com uma estrela, um comentário ou uma doação.')),
    h('button', { type: 'button', class: 'btn mini', onclick: abrirApoio }, 'Como apoiar'));
}

/* Chamado quando a ferramenta acabou de ser útil: uma linha compacta que some sozinha. */
let _apoioTimer = null;
function momentoDeValor(tipo) {
  if (_apoioOculto()) return;
  const texto = tipo === 'medicao' ? 'Medição pronta.' : 'Comando copiado.';
  let linha = document.querySelector('.apoio-linha');
  if (!linha) {
    linha = h('div', { class: 'apoio-linha', role: 'status' });
    document.body.appendChild(linha);
  }
  linha.replaceChildren(
    h('span', {}, texto + ' Gostou? '),
    h('button', { type: 'button', class: 'apoio-link forte', onclick: () => { linha.remove(); abrirApoio(); } }, 'Apoie o projeto ♥'),
    h('button', { type: 'button', class: 'apoio-fechar', title: 'Esconder até a próxima visita', 'aria-label': 'Esconder até a próxima visita', onclick: () => { _apoioOcultar(); linha.remove(); } }, '✕'));
  clearTimeout(_apoioTimer);
  _apoioTimer = setTimeout(() => linha.remove(), APOIO_SEGUNDOS * 1000);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', desenharApoio); else desenharApoio();
