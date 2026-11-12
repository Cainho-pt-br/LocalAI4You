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
  // Pix "copia e cola" sem valor (quem doa escolhe quanto) e sem nome pessoal: o recebedor é só "LOCAL AI 4 YOU". O QR
  // code (pixQr) é gerado desse mesmo texto.
  pixCopiaECola: '00020101021126580014br.gov.bcb.pix0136636ca1e2-6635-4ca0-8e6e-0f7d4873bf6c5204000053039865802BR5914LOCAL AI 4 YOU6006BRASIL62070503***6304A4E6',
  pixQr: 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22424%22 height=%22424%22 class=%22segno%22%3E%3Cg transform=%22scale(8)%22%3E%3Cpath fill=%22%23fff%22 d=%22M0 0h53v53h-53z%22/%3E%3Cpath class=%22qrline%22 stroke=%22%2314161f%22 d=%22M2 2.5h7m1 0h2m2 0h1m1 0h6m4 0h1m2 0h2m1 0h4m2 0h2m2 0h1m1 0h7m-49 1h1m5 0h1m1 0h1m5 0h3m2 0h2m1 0h2m2 0h2m2 0h1m1 0h4m2 0h3m1 0h1m5 0h1m-49 1h1m1 0h3m1 0h1m3 0h2m1 0h1m2 0h2m1 0h2m1 0h1m2 0h1m2 0h1m3 0h1m2 0h3m1 0h2m1 0h1m1 0h3m1 0h1m-49 1h1m1 0h3m1 0h1m1 0h4m2 0h1m2 0h2m3 0h2m2 0h1m6 0h1m2 0h1m2 0h1m2 0h1m1 0h3m1 0h1m-49 1h1m1 0h3m1 0h1m3 0h2m1 0h1m2 0h1m2 0h1m2 0h6m1 0h1m1 0h2m2 0h1m1 0h1m4 0h1m1 0h3m1 0h1m-49 1h1m5 0h1m2 0h2m1 0h1m1 0h4m1 0h4m3 0h1m1 0h1m1 0h4m2 0h1m1 0h1m3 0h1m5 0h1m-49 1h7m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h7m-41 1h1m1 0h1m1 0h6m1 0h1m1 0h2m3 0h1m1 0h1m2 0h1m3 0h4m-39 1h1m1 0h2m1 0h3m3 0h1m1 0h1m1 0h2m1 0h1m1 0h1m1 0h7m1 0h2m1 0h1m1 0h1m1 0h3m2 0h1m2 0h1m1 0h2m-49 1h1m3 0h1m2 0h1m3 0h2m8 0h1m3 0h1m2 0h4m4 0h1m2 0h1m1 0h3m1 0h1m1 0h1m-44 1h3m1 0h1m2 0h1m2 0h3m2 0h2m3 0h1m2 0h1m1 0h4m1 0h1m2 0h1m2 0h1m3 0h1m2 0h1m-48 1h1m2 0h1m3 0h2m2 0h3m3 0h1m4 0h1m1 0h1m7 0h1m1 0h4m1 0h2m3 0h1m1 0h1m1 0h1m-49 1h1m3 0h3m1 0h1m1 0h1m1 0h1m3 0h2m1 0h1m2 0h1m1 0h1m4 0h3m1 0h1m2 0h3m1 0h3m3 0h3m-47 1h1m6 0h1m2 0h2m1 0h1m2 0h1m1 0h1m5 0h1m1 0h2m8 0h1m2 0h1m2 0h1m3 0h1m-49 1h1m1 0h1m1 0h1m1 0h1m1 0h1m2 0h1m2 0h1m3 0h1m2 0h2m1 0h1m1 0h2m1 0h3m1 0h1m1 0h1m2 0h1m1 0h4m2 0h1m-47 1h1m3 0h1m2 0h2m2 0h2m1 0h1m2 0h1m3 0h1m1 0h1m1 0h2m1 0h1m1 0h4m1 0h1m3 0h1m2 0h4m2 0h1m-48 1h1m3 0h3m2 0h1m1 0h2m1 0h1m2 0h4m1 0h1m2 0h1m2 0h1m2 0h4m3 0h2m3 0h4m-47 1h1m1 0h1m4 0h2m1 0h3m1 0h1m2 0h1m4 0h3m1 0h2m2 0h2m1 0h2m1 0h1m2 0h2m4 0h3m-48 1h2m1 0h3m1 0h1m1 0h1m1 0h1m1 0h2m1 0h1m1 0h2m2 0h2m1 0h1m2 0h1m1 0h1m1 0h6m6 0h1m2 0h1m-48 1h2m1 0h2m1 0h1m2 0h3m1 0h1m1 0h1m1 0h2m1 0h1m2 0h1m1 0h1m3 0h2m4 0h1m1 0h4m1 0h1m3 0h1m-48 1h2m2 0h3m2 0h1m5 0h2m1 0h1m1 0h2m1 0h1m1 0h1m1 0h2m1 0h2m2 0h1m4 0h1m3 0h1m1 0h1m-46 1h1m1 0h3m2 0h2m4 0h1m2 0h3m2 0h1m6 0h4m1 0h1m1 0h2m2 0h1m2 0h1m2 0h1m1 0h1m-47 1h1m2 0h5m2 0h1m3 0h1m2 0h2m1 0h6m2 0h6m2 0h1m2 0h8m-47 1h4m3 0h3m1 0h3m1 0h1m2 0h1m2 0h1m3 0h2m1 0h1m1 0h2m1 0h3m3 0h1m3 0h1m1 0h1m1 0h1m-49 1h1m1 0h1m1 0h1m1 0h1m1 0h4m4 0h1m2 0h4m1 0h1m1 0h2m1 0h3m4 0h1m1 0h3m1 0h1m1 0h1m1 0h1m1 0h1m-48 1h4m3 0h4m3 0h1m1 0h1m2 0h3m3 0h1m1 0h2m2 0h1m5 0h1m1 0h1m3 0h2m2 0h1m-49 1h3m1 0h5m1 0h2m4 0h1m1 0h1m2 0h8m1 0h4m1 0h2m1 0h7m1 0h1m-47 1h2m1 0h1m1 0h1m1 0h1m1 0h2m1 0h5m1 0h1m2 0h1m1 0h1m3 0h4m1 0h2m1 0h1m2 0h1m2 0h1m3 0h1m-45 1h2m1 0h3m2 0h3m1 0h1m2 0h1m1 0h1m1 0h1m1 0h1m3 0h1m2 0h1m1 0h2m1 0h2m1 0h2m2 0h1m2 0h3m-47 1h1m2 0h3m2 0h1m1 0h4m1 0h3m2 0h1m1 0h1m3 0h1m2 0h1m1 0h1m1 0h2m1 0h2m3 0h2m2 0h4m-48 1h1m2 0h3m1 0h2m1 0h4m2 0h2m1 0h1m2 0h3m4 0h2m1 0h1m1 0h4m1 0h3m1 0h3m1 0h1m-49 1h1m1 0h4m2 0h5m1 0h3m1 0h2m1 0h1m1 0h1m7 0h1m2 0h1m1 0h1m1 0h2m1 0h1m2 0h2m1 0h2m-46 1h4m2 0h7m1 0h1m1 0h1m1 0h1m5 0h2m2 0h1m5 0h1m6 0h1m1 0h3m-49 1h1m1 0h4m1 0h2m2 0h2m3 0h1m2 0h1m3 0h2m2 0h1m1 0h2m1 0h2m2 0h1m5 0h1m2 0h1m1 0h1m-47 1h4m1 0h1m1 0h3m1 0h1m2 0h1m1 0h4m1 0h1m3 0h2m1 0h1m4 0h2m1 0h1m3 0h1m2 0h1m2 0h1m-47 1h1m3 0h1m1 0h3m1 0h4m3 0h5m3 0h1m1 0h2m2 0h1m1 0h4m1 0h5m2 0h1m1 0h1m-49 1h2m3 0h3m1 0h4m1 0h1m5 0h2m1 0h1m5 0h1m3 0h1m2 0h2m1 0h1m1 0h2m1 0h1m1 0h3m-48 1h1m5 0h1m3 0h1m2 0h1m2 0h1m1 0h2m2 0h1m2 0h3m6 0h2m1 0h2m3 0h3m2 0h1m-48 1h1m3 0h5m3 0h2m3 0h5m4 0h1m2 0h2m1 0h1m1 0h1m2 0h1m5 0h1m-44 1h3m3 0h3m5 0h1m1 0h1m1 0h1m1 0h2m4 0h3m1 0h3m7 0h1m5 0h2m-49 1h3m3 0h2m2 0h2m6 0h2m1 0h7m4 0h1m2 0h1m1 0h1m2 0h5m1 0h1m-39 1h1m1 0h1m1 0h1m2 0h1m2 0h2m1 0h2m3 0h1m1 0h1m5 0h2m1 0h1m1 0h2m3 0h1m1 0h3m-49 1h7m1 0h1m1 0h1m4 0h4m2 0h2m1 0h1m1 0h2m1 0h1m1 0h10m1 0h1m1 0h2m2 0h1m-49 1h1m5 0h1m1 0h4m2 0h4m2 0h1m1 0h1m3 0h3m1 0h2m4 0h1m3 0h1m3 0h1m3 0h1m-49 1h1m1 0h3m1 0h1m2 0h3m1 0h1m1 0h2m1 0h1m3 0h7m2 0h1m5 0h1m2 0h6m-46 1h1m1 0h3m1 0h1m1 0h1m1 0h2m1 0h1m2 0h1m5 0h1m2 0h2m1 0h4m7 0h1m1 0h5m2 0h1m-49 1h1m1 0h3m1 0h1m1 0h4m3 0h2m2 0h2m2 0h1m3 0h3m2 0h2m1 0h1m1 0h1m1 0h1m4 0h1m1 0h3m-49 1h1m5 0h1m5 0h1m1 0h2m2 0h2m2 0h1m1 0h1m1 0h2m3 0h2m2 0h2m2 0h2m2 0h4m-47 1h7m1 0h2m1 0h2m1 0h1m1 0h1m1 0h2m4 0h1m2 0h1m1 0h2m2 0h2m1 0h6m5 0h2%22/%3E%3C/g%3E%3C/svg%3E',   // QR code do texto acima (SVG embutido: funciona no site e no app)
  link: '',         // ex.: 'https://github.com/sponsors/SEU-USUARIO'
  linkRotulo: 'Doar pelo navegador',
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
  const doar = [];
  if (APOIO.pixCopiaECola) doar.push(h('div', { class: 'pix-bloco', style: 'display:flex;gap:14px;align-items:center;flex-wrap:wrap' },
    h('img', { src: APOIO.pixQr, alt: 'QR code do Pix', width: 148, height: 148, style: 'border-radius:10px;background:#fff;padding:4px' }),
    h('div', { class: 'empilha', style: 'gap:8px;min-width:200px;flex:1' },
      h('div', { class: 'sub' }, 'Aponte a câmera do app do seu banco ou copie o código. Você escolhe o valor.'),
      h('button', { class: 'btn primario', onclick: () => navigator.clipboard.writeText(APOIO.pixCopiaECola).then(() => toast('Pix copia e cola copiado. Obrigado!'), () => toast('Não consegui copiar. Use o QR code.')) }, 'Copiar Pix copia e cola'),
      h('div', { class: 'sub', style: 'font-size:.8rem' }, 'Ou use a chave aleatória: ', h('code', {}, APOIO.pix)))));
  else if (APOIO.pix) doar.push(h('div', { class: 'cmd' }, h('code', {}, 'Pix: ' + APOIO.pix)));
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
