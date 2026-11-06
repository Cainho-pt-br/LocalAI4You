'use strict';
function pGuias() {
  const root=$('#p-guias');
  const a=(url,label)=>h('a',{href:url,target:'_blank',rel:'noopener noreferrer'},label+' ↗');
  const card=(n,title,lead,steps,link)=>h('article',{class:'guia-tool'},h('span',{class:'guia-num'},n),h('h2',{},title),h('p',{class:'sub'},lead),h('ol',{},steps.map(x=>h('li',{},x))),link);
  root.replaceChildren(
    h('header',{class:'pagina-topo'},h('span',{class:'guia-kicker'},'PRIMEIRA VEZ? COMECE AQUI'),h('h1',{},'Use um modelo de IA no seu computador'),h('p',{class:'sub'},'Você precisa de três peças: um modelo baixado, um programa que executa o modelo e uma interface para conversar ou programar. Este guia acompanha você em cada etapa.')),
    h('div',{class:'guia-flow'},h('span',{},'MODELO'),h('b',{},'→'),h('span',{},'OLLAMA ou LM STUDIO'),h('b',{},'→'),h('span',{},'SUA INTERFACE')),
    h('div',{class:'guia-callout'},h('b',{},'Antes de baixar'),h('p',{},'Confira a Calculadora para estimar se o modelo cabe na sua memória. Baixar um modelo grande pode ocupar dezenas de gigabytes. O primeiro download precisa de internet; depois, o uso pode ser local.')),
    h('div',{class:'guia-tool-grid'},
      card('1','Ollama + Open WebUI','Boa opção para conversar com modelos numa página parecida com um chat. Primeiro instale o Ollama e baixe um modelo.',[
        'Instale o Ollama pelo site oficial e abra o aplicativo.',
        'Abra o Terminal ou PowerShell e rode: ollama run qwen3:8b. Troque o modelo por um que caiba no seu PC.',
        'Instale o Open WebUI seguindo a documentação. Na conexão com Ollama, use http://localhost:11434 se estiver no mesmo PC.',
        'Abra o endereço local do Open WebUI e selecione o modelo baixado.'
      ],a('https://docs.openwebui.com/','Guia oficial do Open WebUI')),
      card('2','LM Studio','Tudo em um aplicativo gráfico: procurar, baixar, carregar e conversar com modelos. Não precisa do Ollama.',[
        'Instale o LM Studio pelo site oficial.',
        'Abra Discover, pesquise um modelo e escolha uma versão quantizada que caiba na memória.',
        'Baixe o modelo e abra a aba Chat. Selecione-o no topo e envie uma mensagem.',
        'Para conectar outro aplicativo, abra Developer e ligue o servidor local. O endereço padrão é http://localhost:1234/v1.'
      ],a('https://lmstudio.ai/docs/beginner','Começo rápido do LM Studio')),
      card('3','Bionic','O Bionic atual permite escolher onde o modelo roda. Para começar, use o seletor de modelos do próprio app e escolha uma opção local.',[
        'Instale e abra o Bionic pelo site oficial.',
        'Abra o seletor Choose a model e escolha Get local models para ver opções disponíveis no dispositivo.',
        'Baixe um modelo compatível com seu hardware e escolha-o para a conversa ou tarefa.',
        'Se usar Ollama em vez do catálogo integrado, confirme nas configurações do Bionic o endereço local/API esperado pela sua versão.'
      ],a('https://lmstudio.ai/docs/bionic','Guia oficial do Bionic')),
      card('4','OpenCode','Assistente de programação no terminal. Use um modelo local com suporte a ferramentas para permitir ações de código.',[
        'Instale o Ollama e baixe um modelo de código com: ollama run qwen3-coder:30b. Escolha o tamanho conforme sua memória.',
        'Instale e abra o OpenCode na pasta do projeto que quer trabalhar.',
        'Rode /models e escolha um modelo listado em ollama. Modelos locais são detectados no endereço padrão.',
        'Comece pedindo uma explicação ou alteração pequena. Revise o diff antes de aceitar mudanças.'
      ],a('https://opencode.ai/docs/models/','Modelos no OpenCode'))
    ),
    h('h2',{class:'guia-sec'},'Se não funcionar'),
    h('div',{class:'guia-grid'},
      h('article',{class:'guia-card'},h('h3',{},'A lista de modelos está vazia'),h('p',{},'Confira se o Ollama está aberto e se o download terminou. Teste no terminal com ollama list.')),
      h('article',{class:'guia-card'},h('h3',{},'O modelo está lento ou trava'),h('p',{},'Ele pode ser grande demais para sua RAM/VRAM ou o contexto pode estar alto. Tente um modelo menor e reduza o contexto.')),
      h('article',{class:'guia-card'},h('h3',{},'O agente não usa ferramentas'),h('p',{},'Nem todo modelo suporta chamadas de ferramenta confiáveis. Escolha um modelo de código/tool-use e teste primeiro numa tarefa pequena.'))
    ),
    h('p',{class:'sub'},'Os nomes de menus mudam entre versões. As páginas oficiais acima mostram os passos atuais. O app Local AI 4 You mede localmente; não é necessário para usar essas ferramentas.')
  );
}
