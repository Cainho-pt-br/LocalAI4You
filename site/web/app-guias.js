'use strict';
function pGuias() {
  const root = $('#p-guias');
  const sub = S.guiasSub || 'usar';
  const nav = h('div', { class: 'seg', role: 'tablist', style: 'margin-bottom:22px' },
    h('button', { type: 'button', role: 'tab', 'aria-pressed': String(sub === 'usar'), onclick: () => { S.guiasSub = 'usar'; pGuias(); } }, '💬 Como usar e conversar'),
    h('button', { type: 'button', role: 'tab', 'aria-pressed': String(sub === 'ler'), onclick: () => { S.guiasSub = 'ler'; pGuias(); } }, '📊 Como ler notas e selos'));

  if (sub === 'ler') {
    const corpo = h('div', { class: 'ajuda' });
    root.replaceChildren(nav, corpo);
    pAjuda();
    const aj = $('#p-ajuda');
    if (aj) corpo.replaceChildren(...Array.from(aj.childNodes));
    return;
  }

  const a = (url, label) => h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, label + ' ↗');
  const card = (n, title, lead, steps, link) => h('article', { class: 'guia-tool' }, h('span', { class: 'guia-num' }, n), h('h2', {}, title), h('p', { class: 'sub' }, lead), h('ol', {}, steps.map(x => h('li', {}, x))), link);
  root.replaceChildren(
    nav,
    h('header', { class: 'pagina-topo' }, h('span', { class: 'guia-kicker' }, 'PRIMEIRA VEZ? COMECE AQUI'), h('h1', {}, 'Como conversar com sua IA local'), h('p', { class: 'sub' }, 'Você não precisa usar terminal se não quiser. Escolha abaixo a forma mais simples de conversar ou programar com o modelo que você baixou.')),
    h('div', { class: 'guia-flow' }, h('span', {}, '1. MODELO NO RADAR'), h('b', {}, '→'), h('span', {}, '2. OLLAMA ou LM STUDIO'), h('b', {}, '→'), h('span', {}, '3. CONVERSAR NO CHAT')),
    h('div', { class: 'guia-callout' }, h('b', {}, 'Jeito mais rápido (sem terminal)'), h('p', {}, 'Depois de instalar um modelo pelo Radar, abra o próprio aplicativo do Ollama no seu computador (ícone da lhama perto do relógio) e comece a conversar direto pela janela de chat dele. Funciona 100% offline depois do download.')),
    h('div', { class: 'guia-tool-grid' },
      card('1', 'Aplicativo do Ollama ou Open WebUI', 'O Ollama já traz janela de chat própria. Se quiser uma interface completa estilo ChatGPT no navegador, use o Open WebUI.', [
        'Instale o Ollama pelo site oficial e abra o aplicativo.',
        'Instale um modelo clicando em “Instalar” no Radar (ou cole o comando no Terminal se preferir).',
        'Abra a janela do Ollama e escolha o modelo baixado para começar a conversar.',
        'Opcional: para histórico avançado e documentos, instale o Open WebUI apontando para http://localhost:11434.'
      ], a('https://docs.openwebui.com/', 'Guia oficial do Open WebUI')),
      card('2', 'LM Studio (tudo visual)', 'Tudo em um aplicativo gráfico: procurar, baixar, carregar e conversar com modelos. Não precisa do Ollama.', [
        'Instale o LM Studio pelo site oficial.',
        'Abra Discover, pesquise um modelo e escolha uma versão compactada (Q4) que caiba na memória.',
        'Baixe o modelo e abra a aba Chat. Selecione-o no topo e envie uma mensagem.',
        'Para conectar outro aplicativo, abra Developer e ligue o servidor local (http://localhost:1234/v1).'
      ], a('https://lmstudio.ai/docs/beginner', 'Começo rápido do LM Studio')),
      card('3', 'Bionic', 'Permite escolher modelos locais direto no seletor do aplicativo.', [
        'Instale e abra o Bionic pelo site oficial.',
        'Abra o seletor Choose a model e escolha Get local models para ver opções disponíveis no dispositivo.',
        'Baixe um modelo compatível com seu hardware e escolha-o para a conversa ou tarefa.',
        'Se usar Ollama em vez do catálogo integrado, confirme nas configurações o endereço local.'
      ], a('https://lmstudio.ai/docs/bionic', 'Guia oficial do Bionic')),
      card('4', 'OpenCode (programação)', 'Assistente de programação no terminal. Use um modelo local com suporte a ferramentas.', [
        'Instale o Ollama e baixe um modelo indicado para Código no Radar.',
        'Instale e abra o OpenCode na pasta do projeto.',
        'Rode /models e escolha seu modelo listado em ollama.',
        'Comece pedindo uma explicação ou alteração pequena e revise o diff antes de aceitar.'
      ], a('https://opencode.ai/docs/models/', 'Modelos no OpenCode'))
    ),
    h('h2', { class: 'guia-sec' }, 'Se algo não funcionar'),
    h('div', { class: 'guia-grid' },
      h('article', { class: 'guia-card' }, h('h3', {}, 'A lista de modelos está vazia'), h('p', {}, 'Confira se o Ollama está aberto e se o download terminou. Se quiser conferir no terminal, rode ollama list.')),
      h('article', { class: 'guia-card' }, h('h3', {}, 'O modelo está lento ou trava'), h('p', {}, 'Ele pode estar grande demais para sua memória ou o tamanho da conversa está muito alto. Tente um modelo menor na aba Radar.')),
      h('article', { class: 'guia-card' }, h('h3', {}, 'O agente não usa ferramentas'), h('p', {}, 'Nem todo modelo suporta chamadas de ferramenta. Escolha no Radar um modelo marcado com 🛠 ferramentas.'))
    )
  );
}
