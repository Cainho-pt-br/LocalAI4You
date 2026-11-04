'use strict';
/* Apoio ao projeto, de forma discreta:
   • um link pequeno no rodapé da barra lateral, sempre disponível;
   • uma linha única, que some sozinha, DEPOIS de um momento em que a ferramenta ajudou (copiar um comando,
     terminar uma medição ou um duelo). Nunca na primeira ação, no máximo uma vez a cada 60 dias, e some de vez
     com "não mostrar mais". Nada é rastreado nem enviado: os contadores ficam só neste navegador.
   Para ativar doações, preencha APOIO abaixo (chave Pix e/ou um link como GitHub Sponsors, Ko-fi ou Apoia.se). */
const APOIO = {
  pix: '',          // ex.: 'seu-email@exemplo.com' ou chave aleatória
  link: '',         // ex.: 'https://github.com/sponsors/SEU-USUARIO'
  linkRotulo: 'Doar pelo navegador',
};
const APOIO_LS = 'li-apoio-v1';
const APOIO_INTERVALO_DIAS = 60;
const APOIO_MOMENTOS_ANTES = 2;     // só depois do 2º momento de valor

function _apoioEstado() { try { return JSON.parse(localStorage.getItem(APOIO_LS) || '{}') || {}; } catch (e) { return {}; } }
function _apoioGuardar(s) { try { localStorage.setItem(APOIO_LS, JSON.stringify(s)); } catch (e) { /* navegação privada: sem lembrete */ } }

function abrirApoio() {
  const linhas = [
    h('li', {}, '⭐ ', h('a', { href: LINK_REPO, target: '_blank', rel: 'noopener' }, 'Dar uma estrela no GitHub'), ' — ajuda outras pessoas a encontrar o projeto.'),
    h('li', {}, '💬 ', h('a', { href: LINK_REPO + '/issues', target: '_blank', rel: 'noopener' }, 'Contar o que achou ou relatar um problema'), '.'),
    h('li', {}, '🔗 Mostrar para quem está começando com IA local.'),
  ];
  const doar = [];
  if (APOIO.pix) doar.push(h('div', { class: 'cmd' }, h('code', {}, 'Pix: ' + APOIO.pix), h('button', { class: 'btn mini', onclick: () => navigator.clipboard.writeText(APOIO.pix).then(() => toast('Chave Pix copiada. Obrigado!'), () => toast('Não consegui copiar — selecione o texto.')) }, 'Copiar chave')));
  if (APOIO.link) doar.push(h('a', { class: 'btn primario', href: APOIO.link, target: '_blank', rel: 'noopener' }, APOIO.linkRotulo));
  abrirDialogo(h('div', { class: 'dlg-in apoio-dlg' },
    h('h2', {}, '♥ Apoiar o Local AI Search'),
    h('p', { class: 'sub' }, 'O projeto é gratuito, de código aberto e feito no tempo livre. Se ele te poupou tempo, qualquer uma destas ajuda:'),
    h('ul', { class: 'apoio-lista' }, linhas),
    doar.length ? [h('h3', {}, '☕ Doação (opcional)'), h('p', { class: 'sub' }, 'Ajuda a pagar o tempo de manutenção e os testes em hardware novo. Qualquer valor é bem-vindo.'), ...doar] : null,
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
}

function desenharApoio() {
  const link = () => h('button', { type: 'button', class: 'apoio-link', onclick: abrirApoio, title: 'Como ajudar o projeto' }, '♥ Apoiar o projeto');
  const el = document.getElementById('apoio');
  if (el) el.replaceChildren(link());
  const main = document.querySelector('main');   // no celular a barra lateral vira barra de topo: o link vai para o pé da página
  if (main && !main.querySelector('.rodape-apoio')) main.appendChild(h('footer', { class: 'rodape-apoio' }, link()));
}

/* Chamado quando a ferramenta acabou de ser útil. Mostra (raramente) uma linha discreta no rodapé. */
function momentoDeValor(tipo) {
  const s = _apoioEstado();
  s.momentos = (s.momentos || 0) + 1;
  const agora = Date.now(), dias = s.mostrado ? (agora - s.mostrado) / 864e5 : Infinity;
  const mostrar = !s.nunca && s.momentos >= APOIO_MOMENTOS_ANTES && dias >= APOIO_INTERVALO_DIAS;
  if (mostrar) s.mostrado = agora;
  _apoioGuardar(s);
  if (!mostrar || document.querySelector('.apoio-linha')) return;
  const texto = tipo === 'medicao' ? 'Medição pronta. Se o Local AI Search está te ajudando,' : 'Comando copiado. Se o Local AI Search te ajudou a escolher,';
  const linha = h('div', { class: 'apoio-linha', role: 'status' },
    h('span', {}, texto + ' '), h('button', { type: 'button', class: 'apoio-link forte', onclick: () => { linha.remove(); abrirApoio(); } }, 'veja como apoiar ♥'),
    h('button', { type: 'button', class: 'apoio-fechar', title: 'Não mostrar mais', 'aria-label': 'Não mostrar mais', onclick: () => { const e = _apoioEstado(); e.nunca = true; _apoioGuardar(e); linha.remove(); } }, '✕'));
  document.body.appendChild(linha);
  setTimeout(() => linha.remove(), 14000);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', desenharApoio); else desenharApoio();
