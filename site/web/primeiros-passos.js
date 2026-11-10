'use strict';
/* Assistente de primeiros passos (só no app baixado). Aparece no topo de todas as abas até a pessoa ter o Ollama
   ligado e pelo menos dois modelos instalados (o suficiente para um duelo). Cada passo diz o que falta e tem UM botão
   que resolve. Dá para esconder; volta sozinho se o Ollama cair. */
const PP_OCULTO = 'li-passos-oculto';
let _ppLigando = false;

function _ppEtapas() {
  const s = S.saude, inst = (S.mesa?.instalados || []).length;
  const ligado = !!s?.ollama?.no_ar, instalado = !!(s?.ollama?.instalado || ligado);
  return [
    { feito: ligado, titulo: 'Ollama ligado',
      texto: ligado ? `Versão ${s.ollama.versao || ''} rodando.` : instalado ? 'Ele está instalado, mas desligado.' : 'É o programa gratuito que roda os modelos. Instale e volte aqui.',
      acao: ligado ? null : instalado
        ? h('button', { class: 'btn primario', disabled: _ppLigando, onclick: ligarOllama }, _ppLigando ? 'Ligando…' : 'Ligar o Ollama')
        : h('span', { class: 'linha', style: 'gap:8px;flex-wrap:wrap' },
            h('a', { class: 'btn primario', href: 'https://ollama.com/download', target: '_blank', rel: 'noopener' }, 'Baixar o Ollama ↗'),
            h('button', { class: 'btn', onclick: async () => { await carregarSaude(); desenharPrimeirosPassos(); if (!S.saude?.ollama?.instalado) toast('Ainda não encontrei o Ollama. Terminou de instalar? No Windows, às vezes é preciso fechar e abrir este painel de novo.', 9000); } }, 'Já instalei')) },
    { feito: inst >= 1, titulo: 'Primeiro modelo',
      texto: inst >= 1 ? `${inst} modelo(s) instalado(s).` : 'O Radar já mostra os melhores para o seu computador. Clique em “Instalar” no primeiro do pódio.',
      acao: inst >= 1 ? null : h('button', { class: 'btn primario', disabled: !ligado, title: ligado ? '' : 'Ligue o Ollama primeiro', onclick: () => irPara('radar') }, 'Escolher no Radar') },
    { feito: inst >= 2, titulo: 'Tirar a dúvida',
      texto: inst >= 2 ? 'Pronto para medir e duelar.' : 'Com dois candidatos, o duelo mede os dois aqui no seu PC e diz qual vence (ou se empatam).',
      acao: inst >= 1 ? h('button', { class: 'btn', onclick: () => irPara('medir') }, inst >= 2 ? 'Fazer um duelo' : 'Medir o que tenho') : null },
  ];
}

async function ligarOllama() {
  _ppLigando = true; desenharPrimeirosPassos();
  try { await api('/api/ollama/iniciar', {}); toast('Ollama ligado.'); }
  catch (e) { toast('Não consegui ligar: ' + e.message + ' Abra o aplicativo do Ollama manualmente.', 10000); }
  _ppLigando = false;
  await carregarSaude(); desenharStatus(); desenharPrimeirosPassos();
}

function desenharPrimeirosPassos() {
  const el = document.getElementById('primeiros-passos');
  if (!el) return;
  if (window.LI_PUBLIC_MODE || !S.saude || LI.alvo) { el.replaceChildren(); return; }
  const etapas = _ppEtapas();
  const caiu = !etapas[0].feito;
  let oculto = false;
  try { oculto = localStorage.getItem(PP_OCULTO) === '1'; } catch (e) { /* ok */ }
  if (etapas.every(e => e.feito) || (oculto && !caiu)) { el.replaceChildren(); return; }
  const atual = etapas.findIndex(e => !e.feito);
  el.replaceChildren(h('section', { class: 'pp', 'aria-label': 'Primeiros passos' },
    h('div', { class: 'pp-topo' },
      h('div', {}, h('span', { class: 'guia-kicker' }, 'PRIMEIROS PASSOS'), h('h2', {}, caiu && etapas[1].feito ? 'O Ollama está desligado' : 'Vamos deixar tudo pronto em 3 passos')),
      h('button', { class: 'btn mini', title: 'Esconder (volta se o Ollama cair)', onclick: () => { try { localStorage.setItem(PP_OCULTO, '1'); } catch (e) { /* ok */ } el.replaceChildren(); } }, 'Esconder')),
    h('ol', { class: 'pp-etapas' }, etapas.map((e, i) => h('li', { class: e.feito ? 'feito' : i === atual ? 'atual' : 'depois' },
      h('span', { class: 'pp-n' }, e.feito ? '✓' : String(i + 1)),
      h('div', { class: 'pp-corpo' }, h('b', {}, e.titulo), h('p', { class: 'sub' }, e.texto), i === atual || (e.acao && !e.feito) ? e.acao : null))))));
}

/* Aviso de versão nova (só no app baixado pelo site; a Microsoft Store atualiza sozinha). Compara a impressão digital
   do programa com a do release app-latest no GitHub; o catálogo diário não conta como versão nova. */
async function verificarAtualizacao() {
  const b = S.saude?.build;
  if (window.LI_PUBLIC_MODE || !b || b.loja || !b.impressao) return;
  try { if (sessionStorage.getItem('li-atualizacao-vista') === '1') return; } catch (e) { /* ok */ }
  let notas = '';
  try {
    const r = await fetch('https://api.github.com/repos/Cainho-pt-br/LocalAI4You/releases/tags/app-latest', { cache: 'no-store' });
    if (!r.ok) return;
    notas = (await r.json()).body || '';
  } catch (e) { return; }   // sem internet: tudo bem
  const m = /Versão do app: ([0-9a-f]{6,})/.exec(notas);
  if (!m || m[1] === b.impressao) return;
  const el = document.getElementById('primeiros-passos'); if (!el) return;
  el.parentNode.insertBefore(h('div', { class: 'aviso-atualizacao' },
    h('span', {}, '✨ ', h('b', {}, 'Saiu uma versão nova do Local AI 4 You. '), 'Baixe e rode o instalador de novo: seus modelos, notas e configurações continuam.'),
    h('a', { class: 'btn primario mini', href: typeof LINK_ZIP === 'string' ? LINK_ZIP : '#', target: '_blank', rel: 'noopener' }, 'Baixar a nova versão'),
    h('button', { type: 'button', class: 'btn mini', onclick: ev => { try { sessionStorage.setItem('li-atualizacao-vista', '1'); } catch (e) { /* ok */ } ev.target.closest('.aviso-atualizacao').remove(); } }, 'Depois')), el);
}
