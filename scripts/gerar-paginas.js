#!/usr/bin/env node
'use strict';
/* Gera as páginas estáticas "o que roda em cada placa" (uma por placa de vídeo, chip e computador sem placa), em
   português, inglês e espanhol, mais o índice de cada idioma e o sitemap.

   Por quê: quem procura "qual IA roda na RTX 4060" no Google precisa cair numa página que já responde, e o app
   (app.html) monta tudo no navegador, o que os buscadores leem mal. Aqui o conteúdo sai pronto no HTML, calculado
   com o MESMO motor do Radar (web/calc.js) sobre o catálogo do dia (site/dados.js).

       node scripts/gerar-paginas.js              # grava em site/placa, site/en/gpu, site/es/gpu e site/sitemap.xml
       node scripts/gerar-paginas.js --verificar  # só monta em memória (usado no CI): falha se algo quebrar

   Roda todo dia no workflow do catálogo. Os textos evitam números que mudam a toda hora (a contagem é arredondada,
   não há data na página): assim uma página só muda no Git quando a lista dela muda de verdade. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const RAIZ = path.resolve(__dirname, '..');
const SITE = path.join(RAIZ, 'site');
const URL_SITE = (process.env.SITE_URL || 'https://localai4you.vercel.app').replace(/\/+$/, '');
const Calc = require(path.join(RAIZ, 'download', 'LocalIntelligence', 'web', 'calc.js'));

function carregarDados() {
  const caixa = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(SITE, 'dados.js'), 'utf8'), caixa);
  if (!caixa.window.LI_DADOS) throw new Error('site/dados.js não definiu window.LI_DADOS');
  return caixa.window.LI_DADOS;
}

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const TOP = 10;
const RAM_PADRAO = 32;                       // o mesmo padrão da Calculadora
const RAM_SEM_PLACA = [8, 16, 32, 64];
const GPUS_MAIORES = ['rtx-3060-12', 'rtx-5060-ti-16', 'rtx-4090', 'rtx-5090'];   // degraus de upgrade sugeridos

// ---------------------------------------------------------------- idiomas
const USOS = {
  chat_pt: ['Conversa', 'Chat', 'Conversación'], codigo: ['Código', 'Coding', 'Código'], agente: ['Agentes', 'Agents', 'Agentes'],
  regras: ['Extrair dados e JSON', 'Data extraction and JSON', 'Extraer datos y JSON'], raciocinio: ['Raciocínio', 'Reasoning', 'Razonamiento'],
  rapido: ['Rápido e leve', 'Fast and light', 'Rápido y ligero'], visao: ['Imagens e documentos', 'Images and documents', 'Imágenes y documentos'],
  contexto: ['Documentos longos', 'Long documents', 'Documentos largos'],
};
const GRUPOS = {
  nvidia: ['NVIDIA GeForce (desktop)', 'NVIDIA GeForce (desktop)', 'NVIDIA GeForce (escritorio)'],
  'nvidia-nb': ['NVIDIA GeForce (notebook)', 'NVIDIA GeForce (laptop)', 'NVIDIA GeForce (portátil)'],
  amd: ['AMD Radeon', 'AMD Radeon', 'AMD Radeon'],
  'amd-nb': ['AMD Radeon (notebook)', 'AMD Radeon (laptop)', 'AMD Radeon (portátil)'],
  intel: ['Intel Arc', 'Intel Arc', 'Intel Arc'],
  unificada: ['Mac e memória unificada', 'Mac and unified memory', 'Mac y memoria unificada'],
  cpu: ['Sem placa de vídeo', 'No graphics card', 'Sin tarjeta gráfica'],
  'nvidia-pro': ['NVIDIA para estação e servidor', 'NVIDIA workstation and server', 'NVIDIA para estación y servidor'],
  'amd-pro': ['AMD para estação e servidor', 'AMD workstation and server', 'AMD para estación y servidor'],
};
const IDIOMAS = {
  pt: {
    i: 0, og: 'og.png', dir: 'placa', html: 'pt-BR', loc: 'pt-BR', rotulo: 'Português', inicio: '/',
    marca_sub: 'Qual IA roda no seu computador',
    nav: { radar: 'Radar', calc: 'Calculadora', placas: 'Todas as placas', inicio: 'Início' },
    nome: h => h.tipo === 'gpu' ? `${h.curto} de ${h.mem} GB` : h.tipo === 'chip' ? `${h.base} com ${h.mem} GB` : `PC sem placa de vídeo, com ${h.mem} GB de RAM`,
    em: h => h.tipo === 'gpu' ? `na ${h.curto} de ${h.mem} GB` : h.tipo === 'chip' ? `no ${h.base} com ${h.mem} GB` : `num PC sem placa de vídeo, com ${h.mem} GB de RAM`,
    para: h => h.tipo === 'gpu' ? `a ${h.curto} de ${h.mem} GB` : h.tipo === 'chip' ? `o ${h.base} com ${h.mem} GB` : `um PC sem placa de vídeo e ${h.mem} GB de RAM`,
    titulo: h => h.tipo === 'cpu' ? `Quais IAs rodam sem placa de vídeo, com ${h.mem} GB de RAM?` : `Quais IAs rodam ${IDIOMAS.pt.em(h)}? Os melhores modelos locais`,
    h1: h => h.tipo === 'cpu' ? `Quais IAs rodam sem placa de vídeo, com ${h.mem} GB de RAM?` : `Quais IAs rodam ${IDIOMAS.pt.em(h)}?`,
    kicker: 'IA LOCAL · ESTIMADO PARA ESTE HARDWARE',
    aprox: n => n >= 20 ? `Mais de ${Math.floor(n / 10) * 10}` : String(n),
    desc: (h, a, top, tps) => `${a} modelos de IA local cabem ${IDIOMAS.pt.em(h)}. O mais indicado é o ${top} (~${tps} tokens/s). Veja os melhores por uso, com o comando do Ollama pronto.`,
    lead: (h, a, top, v, gb, tps) => `<b>${a} modelos</b> de IA (LLMs) cabem ${esc(IDIOMAS.pt.em(h))} e rodam no seu computador, de graça e sem internet. O mais indicado hoje é o <b>${esc(top)}</b> (${esc(v)}, ${gb} GB), que deve gerar cerca de <b>${tps} tokens por segundo</b>.`,
    vazio: h => `Nenhum modelo do catálogo cabe ${IDIOMAS.pt.em(h)} com boa qualidade. Com mais memória, a lista abre: veja as opções abaixo.`,
    fatos: (h, orc) => h.tipo === 'gpu' ? [`${h.mem} GB de memória de vídeo (VRAM)`, `${orc} GB livres para o modelo no Windows`, `${h.bw} GB/s de banda de memória`]
      : h.tipo === 'chip' ? [`${h.mem} GB de memória unificada`, `${orc} GB livres para o modelo`, `${h.bw} GB/s de banda de memória`]
      : [`${h.mem} GB de RAM`, `${orc} GB livres para o modelo no Windows`, 'roda no processador: mais devagar que numa placa'],
    cta: 'Ver a lista completa para o meu computador →', cta_calc: 'Simular um upgrade',
    h2_top: (h, n) => `Os ${n} melhores modelos para ${IDIOMAS.pt.para(h)}`,
    sub_top: 'Do mais indicado ao menos indicado. Copie o comando e rode no terminal, com o Ollama instalado.',
    folga: 'cabe com folga', limite: 'cabe no limite: use contexto menor', lento: 'lento neste hardware',
    bom_para: 'Bom para', copiar: 'Copiar', copiado: 'Copiado ✓',
    h2_usos: 'O melhor para cada uso', th: ['Uso', 'Modelo', 'Versão', 'Velocidade'],
    h2_fora: 'O que ainda não cabe',
    sub_fora: orc => `Estes são os que ficam mais perto: mesmo na menor versão de boa qualidade, precisam de mais do que os ${orc} GB livres.`,
    precisa: gb => `precisa de ~${gb} GB`,
    h2_maior: 'Com mais memória, o que muda?', sub_maior: 'Modelos maiores costumam ser mais inteligentes. Compare com estas placas:',
    h2_lojas: h => `Onde comprar a ${h.curto} de ${h.mem} GB`, sub_lojas: 'Compare o preço nas lojas antes de decidir. Confira sempre a quantidade de memória (VRAM) no anúncio.',
    h2_como: 'Como esta lista é feita',
    como: h => `Só entra o que cabe na memória com compressão de boa qualidade. A ordem prioriza a inteligência estimada do modelo; a velocidade conta até ficar confortável de ler (cerca de 10 tokens por segundo). Tudo aqui é <b>estimado</b> a partir do tamanho real dos arquivos${h.tipo === 'chip' ? '' : `, para Windows${h.tipo === 'gpu' ? `, ${RAM_PADRAO} GB de RAM e uma placa` : ''}`}. Para medir de verdade no seu computador, o app gratuito faz duelos entre os modelos instalados.`,
    h2_faq: 'Perguntas comuns',
    faq: (h, top, v, tps, cod) => [
      [`Qual é o melhor modelo de IA para ${IDIOMAS.pt.para(h)}?`, `Hoje, o ${top} (${v}), que deve gerar cerca de ${tps} tokens por segundo.${cod && cod !== top ? ` Para programar, o mais indicado é o ${cod}.` : ''}`],
      ['Preciso de internet ou de pagar alguma coisa?', 'Só de internet para baixar. Depois, o modelo roda no seu computador com o Ollama, um programa gratuito: sem mensalidade e sem enviar suas conversas para ninguém.'],
      ['Como eu instalo?', 'Instale o Ollama, abra o terminal e cole o comando que aparece ao lado do modelo. O download começa e, quando terminar, é só conversar.'],
    ],
    h2_rel: 'Outros computadores', rodape: 'gratuito e de código aberto (Apache-2.0)', privacidade: 'Privacidade',
    hub_titulo: 'IA local por placa de vídeo: o que roda em cada computador',
    hub_desc: 'Escolha a sua placa de vídeo, o seu Mac ou a memória do seu PC e veja quais modelos de IA rodam bem nele, com o comando do Ollama pronto.',
    hub_lead: 'Escolha a sua placa de vídeo, o seu Mac ou a memória do seu PC. Cada página mostra os melhores modelos de IA que cabem ali, por uso, com o comando pronto para baixar.',
    hub_cta: 'Não achou o seu? Informe o hardware no Radar →',
    aviso_lojas: '',
  },
  en: {
    i: 1, og: 'og-en.png', dir: 'en/gpu', html: 'en', loc: 'en-US', rotulo: 'English', inicio: '/',
    marca_sub: 'Which AI runs on your computer',
    nav: { radar: 'Radar', calc: 'Calculator', placas: 'All graphics cards', inicio: 'Home' },
    nome: h => h.tipo === 'gpu' ? `${h.curto} ${h.mem} GB` : h.tipo === 'chip' ? `${h.base} with ${h.mem} GB` : `PC with no graphics card and ${h.mem} GB of RAM`,
    em: h => h.tipo === 'gpu' ? `on the ${h.curto} ${h.mem} GB` : h.tipo === 'chip' ? `on the ${h.base} with ${h.mem} GB` : `on a PC with no graphics card and ${h.mem} GB of RAM`,
    para: h => h.tipo === 'gpu' ? `the ${h.curto} ${h.mem} GB` : h.tipo === 'chip' ? `the ${h.base} with ${h.mem} GB` : `a PC with no graphics card and ${h.mem} GB of RAM`,
    titulo: h => h.tipo === 'cpu' ? `Best local LLMs with no graphics card and ${h.mem} GB of RAM` : `Best local LLMs for ${IDIOMAS.en.para(h)}: what actually runs`,
    h1: h => h.tipo === 'cpu' ? `Which AI models run with no graphics card and ${h.mem} GB of RAM?` : `Which AI models run ${IDIOMAS.en.em(h)}?`,
    kicker: 'LOCAL AI · ESTIMATED FOR THIS HARDWARE',
    aprox: n => n >= 20 ? `More than ${Math.floor(n / 10) * 10}` : String(n),
    desc: (h, a, top, tps) => `${a} local AI models fit ${IDIOMAS.en.em(h)}. The top pick is ${top} (~${tps} tokens/s). See the best ones by use, with the Ollama command ready to copy.`,
    lead: (h, a, top, v, gb, tps) => `<b>${a} AI models</b> (LLMs) fit ${esc(IDIOMAS.en.em(h))} and run on your own computer, free and offline. The top pick today is <b>${esc(top)}</b> (${esc(v)}, ${gb} GB), which should generate about <b>${tps} tokens per second</b>.`,
    vazio: h => `No model in the catalog fits ${IDIOMAS.en.em(h)} at good quality. With more memory the list opens up: see the options below.`,
    fatos: (h, orc) => h.tipo === 'gpu' ? [`${h.mem} GB of video memory (VRAM)`, `${orc} GB free for the model on Windows`, `${h.bw} GB/s memory bandwidth`]
      : h.tipo === 'chip' ? [`${h.mem} GB of unified memory`, `${orc} GB free for the model`, `${h.bw} GB/s memory bandwidth`]
      : [`${h.mem} GB of RAM`, `${orc} GB free for the model on Windows`, 'runs on the processor: slower than on a graphics card'],
    cta: 'See the full list for my computer →', cta_calc: 'Simulate an upgrade',
    h2_top: (h, n) => `The ${n} best models for ${IDIOMAS.en.para(h)}`,
    sub_top: 'From most to least recommended. Copy the command and run it in the terminal, with Ollama installed.',
    folga: 'fits comfortably', limite: 'barely fits: use a smaller context', lento: 'slow on this hardware',
    bom_para: 'Good for', copiar: 'Copy', copiado: 'Copied ✓',
    h2_usos: 'The best pick for each use', th: ['Use', 'Model', 'Version', 'Speed'],
    h2_fora: 'What does not fit yet',
    sub_fora: orc => `These come closest: even in their smallest good-quality version, they need more than the ${orc} GB available.`,
    precisa: gb => `needs ~${gb} GB`,
    h2_maior: 'What changes with more memory?', sub_maior: 'Bigger models tend to be smarter. Compare with these cards:',
    h2_como: 'How this list is built',
    como: h => `Only models that fit in memory at good compression quality make the list. The order favors the estimated intelligence of the model; speed counts until it is comfortable to read (about 10 tokens per second). Everything here is <b>estimated</b> from real file sizes${h.tipo === 'chip' ? '' : `, for Windows${h.tipo === 'gpu' ? `, ${RAM_PADRAO} GB of RAM and a single card` : ''}`}. To measure for real on your own computer, the free app runs duels between your installed models.`,
    h2_faq: 'Common questions',
    faq: (h, top, v, tps, cod) => [
      [`What is the best AI model for ${IDIOMAS.en.para(h)}?`, `Today it is ${top} (${v}), which should generate about ${tps} tokens per second.${cod && cod !== top ? ` For coding, the top pick is ${cod}.` : ''}`],
      ['Do I need internet or a subscription?', 'Only internet to download. After that the model runs on your computer with Ollama, a free program: no subscription, and your conversations are not sent anywhere.'],
      ['How do I install it?', 'Install Ollama, open the terminal and paste the command shown next to the model. The download starts and, when it finishes, you can start chatting.'],
    ],
    h2_rel: 'Other computers', rodape: 'free and open source (Apache-2.0)', privacidade: 'Privacy',
    hub_titulo: 'Local AI by graphics card: what runs on each computer',
    hub_desc: 'Pick your graphics card, your Mac or your PC memory and see which AI models run well on it, with the Ollama command ready to copy.',
    hub_lead: 'Pick your graphics card, your Mac or your PC memory. Each page lists the best AI models that fit, by use, with the download command ready.',
    hub_cta: 'Not listed? Enter your hardware in the Radar →',
  },
  es: {
    i: 2, og: 'og-es.png', dir: 'es/gpu', html: 'es', loc: 'es-ES', rotulo: 'Español', inicio: '/',
    marca_sub: 'Qué IA corre en tu computadora',
    nav: { radar: 'Radar', calc: 'Calculadora', placas: 'Todas las tarjetas', inicio: 'Inicio' },
    nome: h => h.tipo === 'gpu' ? `${h.curto} de ${h.mem} GB` : h.tipo === 'chip' ? `${h.base} con ${h.mem} GB` : `PC sin tarjeta gráfica, con ${h.mem} GB de RAM`,
    em: h => h.tipo === 'gpu' ? `en la ${h.curto} de ${h.mem} GB` : h.tipo === 'chip' ? `en el ${h.base} con ${h.mem} GB` : `en un PC sin tarjeta gráfica, con ${h.mem} GB de RAM`,
    para: h => h.tipo === 'gpu' ? `la ${h.curto} de ${h.mem} GB` : h.tipo === 'chip' ? `el ${h.base} con ${h.mem} GB` : `un PC sin tarjeta gráfica y ${h.mem} GB de RAM`,
    titulo: h => h.tipo === 'cpu' ? `¿Qué IA local corre sin tarjeta gráfica, con ${h.mem} GB de RAM?` : `¿Qué IA local corre ${IDIOMAS.es.em(h)}? Los mejores modelos`,
    h1: h => h.tipo === 'cpu' ? `¿Qué IA corre sin tarjeta gráfica, con ${h.mem} GB de RAM?` : `¿Qué IA corre ${IDIOMAS.es.em(h)}?`,
    kicker: 'IA LOCAL · ESTIMADO PARA ESTE HARDWARE',
    aprox: n => n >= 20 ? `Más de ${Math.floor(n / 10) * 10}` : String(n),
    desc: (h, a, top, tps) => `${a} modelos de IA local caben ${IDIOMAS.es.em(h)}. El más recomendado es ${top} (~${tps} tokens/s). Mira los mejores por uso, con el comando de Ollama listo.`,
    lead: (h, a, top, v, gb, tps) => `<b>${a} modelos</b> de IA (LLM) caben ${esc(IDIOMAS.es.em(h))} y corren en tu computadora, gratis y sin internet. El más recomendado hoy es <b>${esc(top)}</b> (${esc(v)}, ${gb} GB), que debería generar unos <b>${tps} tokens por segundo</b>.`,
    vazio: h => `Ningún modelo del catálogo cabe ${IDIOMAS.es.em(h)} con buena calidad. Con más memoria la lista se abre: mira las opciones abajo.`,
    fatos: (h, orc) => h.tipo === 'gpu' ? [`${h.mem} GB de memoria de video (VRAM)`, `${orc} GB libres para el modelo en Windows`, `${h.bw} GB/s de ancho de banda de memoria`]
      : h.tipo === 'chip' ? [`${h.mem} GB de memoria unificada`, `${orc} GB libres para el modelo`, `${h.bw} GB/s de ancho de banda de memoria`]
      : [`${h.mem} GB de RAM`, `${orc} GB libres para el modelo en Windows`, 'corre en el procesador: más lento que en una tarjeta gráfica'],
    cta: 'Ver la lista completa para mi computadora →', cta_calc: 'Simular una mejora',
    h2_top: (h, n) => `Los ${n} mejores modelos para ${IDIOMAS.es.para(h)}`,
    sub_top: 'Del más recomendado al menos recomendado. Copia el comando y ejecútalo en la terminal, con Ollama instalado.',
    folga: 'cabe con holgura', limite: 'cabe justo: usa un contexto menor', lento: 'lento en este hardware',
    bom_para: 'Bueno para', copiar: 'Copiar', copiado: 'Copiado ✓',
    h2_usos: 'El mejor para cada uso', th: ['Uso', 'Modelo', 'Versión', 'Velocidad'],
    h2_fora: 'Lo que todavía no cabe',
    sub_fora: orc => `Estos son los que quedan más cerca: incluso en su versión más pequeña de buena calidad, necesitan más que los ${orc} GB libres.`,
    precisa: gb => `necesita ~${gb} GB`,
    h2_maior: '¿Qué cambia con más memoria?', sub_maior: 'Los modelos más grandes suelen ser más inteligentes. Compara con estas tarjetas:',
    h2_como: 'Cómo se hace esta lista',
    como: h => `Solo entra lo que cabe en la memoria con compresión de buena calidad. El orden prioriza la inteligencia estimada del modelo; la velocidad cuenta hasta que resulta cómoda de leer (unos 10 tokens por segundo). Todo aquí es <b>estimado</b> a partir del tamaño real de los archivos${h.tipo === 'chip' ? '' : `, para Windows${h.tipo === 'gpu' ? `, ${RAM_PADRAO} GB de RAM y una sola tarjeta` : ''}`}. Para medir de verdad en tu computadora, la app gratuita hace duelos entre los modelos instalados.`,
    h2_faq: 'Preguntas comunes',
    faq: (h, top, v, tps, cod) => [
      [`¿Cuál es el mejor modelo de IA para ${IDIOMAS.es.para(h)}?`, `Hoy, ${top} (${v}), que debería generar unos ${tps} tokens por segundo.${cod && cod !== top ? ` Para programar, el más recomendado es ${cod}.` : ''}`],
      ['¿Necesito internet o pagar algo?', 'Solo internet para descargar. Después, el modelo corre en tu computadora con Ollama, un programa gratuito: sin suscripción y sin enviar tus conversaciones a nadie.'],
      ['¿Cómo lo instalo?', 'Instala Ollama, abre la terminal y pega el comando que aparece junto al modelo. La descarga empieza y, cuando termina, ya puedes conversar.'],
    ],
    h2_rel: 'Otras computadoras', rodape: 'gratuito y de código abierto (Apache-2.0)', privacidade: 'Privacidad',
    hub_titulo: 'IA local por tarjeta gráfica: qué corre en cada computadora',
    hub_desc: 'Elige tu tarjeta gráfica, tu Mac o la memoria de tu PC y mira qué modelos de IA corren bien, con el comando de Ollama listo.',
    hub_lead: 'Elige tu tarjeta gráfica, tu Mac o la memoria de tu PC. Cada página muestra los mejores modelos de IA que caben, por uso, con el comando listo para descargar.',
    hub_cta: '¿No está la tuya? Indica tu hardware en el Radar →',
  },
};
const LISTA_IDIOMAS = Object.keys(IDIOMAS);

// ---------------------------------------------------------------- hardware
function listarHardware(D) {
  const hw = D.hardware;
  const win = hw.sistemas.find(s => s.id === 'windows') || hw.sistemas[0];
  const mac = hw.sistemas.find(s => s.id === 'macos') || win;
  const cpu = hw.cpus.find(c => /Ryzen 7000 \(Zen 4\)/.test(c.nome)) || hw.cpus[0];          // o mesmo padrão da Calculadora
  const mem = cpu.bw ? { bw_min: cpu.bw[0], bw_max: cpu.bw[1] } : Calc.memBw(hw.memorias_ram.find(m => m.id === cpu.mem) || hw.memorias_ram[0], cpu.canais || 2);
  const reserva = p => ({ ...p, reserva_vram_gb: p.reserva_vram_gb ?? D.reserva_vram_gb ?? 1.3 });
  const grupoGpu = g => g.fab === 'NVIDIA' ? (/Laptop/.test(g.nome) ? 'nvidia-nb' : /GeForce/.test(g.nome) ? 'nvidia' : 'nvidia-pro')
    : g.fab === 'AMD' ? (/Instinct|PRO|Radeon VII/.test(g.nome) ? 'amd-pro' : /7900M/.test(g.nome) ? 'amd-nb' : 'amd') : 'intel';
  const lista = [];
  for (const g of hw.gpus) {
    const base = g.nome.replace(/\s\d+\s?GB\b/i, '');
    lista.push({ tipo: 'gpu', slug: g.id, grupo: grupoGpu(g), base, curto: base.replace(/^GeForce\s+/i, ''), mem: g.vram_gb, bw: g.bw_gbs, consulta: 'gpu=' + g.id,
      busca: g.nome.replace(/^GeForce\s+/i, '').replace(/\s(\d+)\sGB\b/i, ' $1GB'),
      perfil: reserva(Calc.perfilGpu({ gpu: g, n: 1, ram_gb: RAM_PADRAO, mem, cpu, sistema: win })) });
  }
  for (const c of hw.unificadas) for (const ram of c.ram_opcoes || []) {
    lista.push({ tipo: 'chip', slug: `${c.id}-${ram}gb`, grupo: 'unificada', base: c.nome, curto: c.nome, mem: ram, bw: c.bw_gbs, consulta: `chip=${c.id}&ram=${ram}`,
      perfil: reserva(Calc.perfilUnificado({ chip: c, ram_gb: ram, cpu: null, sistema: mac })) });
  }
  for (const ram of RAM_SEM_PLACA) {
    lista.push({ tipo: 'cpu', slug: `cpu-${ram}gb`, grupo: 'cpu', base: 'CPU', curto: 'CPU', mem: ram, bw: null, consulta: 'ram=' + ram,
      perfil: Calc.perfilCpu({ ram_gb: ram, mem, cpu, sistema: win }) });
  }
  const vistos = new Set();
  for (const h of lista) { if (vistos.has(h.slug)) throw new Error('slug repetido: ' + h.slug); vistos.add(h.slug); }
  return lista;
}

/* Tudo o que a página mostra, calculado uma vez por hardware (vale para os três idiomas). */
function avaliar(D, h) {
  const papeis = (D.papeis || []).filter(p => !p.sem_nota);
  const ids = papeis.map(p => p.id), op = { kv: 'q8_0', ctx: null };
  const rk = Calc.ranking(D, h.perfil, ids, op);
  const fora = Calc.naoCabem(D, h.perfil, ids, op);
  const usos = papeis.map(p => ({ p, x: Calc.ranking(D, h.perfil, [p.id], op)[0] || null })).filter(u => u.x);
  const orc = rk[0] ? rk[0].enc.encaixe.orcamento_gb : fora[0] ? fora[0].orcamento_gb : Calc.orcamentoBytes(h.perfil, h.perfil.reserva_vram_gb ?? 1.3) / Calc.GIB;
  return { rk, fora: fora.slice(0, 5), usos, orc, n: rk.length };
}

// ---------------------------------------------------------------- HTML
const nomeModelo = c => {       // como o site mostra: sem o caminho do repositório nem sufixos de empacotamento
  let s = String(c.nome || c.id);
  if (s.includes('/')) s = s.split('/').pop();
  return s.replace(/[-_]GGUF$/i, '');
};
function formatos(L) {
  const n = (v, c = 0) => Number(v).toLocaleString(L.loc, { minimumFractionDigits: c, maximumFractionDigits: c });
  return {
    n,
    gb: bytes => n(bytes / 1e9, 1),
    tps: t => !t ? '?' : (t[0] + t[1]) / 2 >= 10 ? n((t[0] + t[1]) / 2, 0) : n((t[0] + t[1]) / 2, 1),
    faixa: t => !t ? '?' : `${n(t[0], t[0] < 10 ? 1 : 0)}–${n(t[1], t[1] < 10 ? 1 : 0)}`,
  };
}
const caminho = (L, slug) => `/${L.dir}/${slug ? slug + '.html' : ''}`;
const alternativas = slug => LISTA_IDIOMAS.map(k => `<link rel="alternate" hreflang="${IDIOMAS[k].html}" href="${URL_SITE}${caminho(IDIOMAS[k], slug)}">`).join('\n')
  + `\n<link rel="alternate" hreflang="x-default" href="${URL_SITE}${caminho(IDIOMAS.en, slug)}">`;

function moldura(L, { slug, titulo, desc, corpo, jsonld, hw, lojas }) {
  const url = URL_SITE + caminho(L, slug);
  const troca = LISTA_IDIOMAS.map(k => k === Object.keys(IDIOMAS)[L.i]
    ? `<b aria-current="true">${IDIOMAS[k].rotulo}</b>` : `<a href="${caminho(IDIOMAS[k], slug)}" hreflang="${IDIOMAS[k].html}">${IDIOMAS[k].rotulo}</a>`).join(' · ');
  return `<!doctype html>
<html lang="${L.html}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(titulo)} | Local AI 4 You</title>
<meta name="description" content="${esc(desc)}">
<link rel="canonical" href="${url}">
${alternativas(slug)}
<meta property="og:title" content="${esc(titulo)}">
<meta property="og:description" content="${esc(desc)}">
<meta property="og:type" content="article">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${URL_SITE}/${L.og}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:site_name" content="Local AI 4 You">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/web/logo.svg" type="image/svg+xml">
<script>
  window.LI_PUBLIC_MODE = true;
  try { const t = localStorage.getItem('li-tema'); if (t) document.documentElement.setAttribute('data-theme', t); } catch (e) {}
</script>
<link rel="stylesheet" href="/web/style.css">
<link rel="stylesheet" href="/landing.css">
<link rel="stylesheet" href="/placa.css">
${jsonld ? `<script type="application/ld+json">${JSON.stringify(jsonld).replace(/</g, '\\u003c')}</script>` : ''}
</head>
<body class="landing pg-placa" data-hw="${esc(hw || 'indice')}" data-idioma="${Object.keys(IDIOMAS)[L.i]}" data-copiado="${esc(L.copiado)}">
<header class="l-topo">
  <a class="l-marca" href="/"><img class="pg-logo" src="/web/logo.svg" alt="" width="30" height="30"> Local AI 4 You</a>
  <nav class="l-nav" aria-label="${esc(L.nav.inicio)}">
    <a href="/app.html#radar">${esc(L.nav.radar)}</a>
    <a href="/app.html#calculadora">${esc(L.nav.calc)}</a>
    <a href="${caminho(L)}">${esc(L.nav.placas)}</a>
  </nav>
  <div class="l-topo-acoes pg-idiomas">${troca}</div>
</header>
<main class="l-main pg-main">
${corpo}
</main>
<footer class="l-rodape">
  <div><b>Local AI 4 You</b> · ${esc(L.rodape)}</div>
  <nav>
    <a href="/">${esc(L.nav.inicio)}</a>
    <a href="/app.html#radar">${esc(L.nav.radar)}</a>
    <a href="${caminho(L)}">${esc(L.nav.placas)}</a>
    <a href="https://github.com/Cainho-pt-br/LocalAI4You" target="_blank" rel="noopener">GitHub ↗</a>
    <a href="/privacidade.html">${esc(L.privacidade)}</a>
  </nav>
</footer>
<script src="/web/base.js"></script>
<script src="/web/coleta.js"></script>
${lojas ? '<script src="/web/lojas.js"></script>\n' : ''}<script src="/placa.js"></script>
</body>
</html>
`;
}

function paginaHardware(L, D, h, av, todos) {
  const F = formatos(L), li = L.i;
  const uso = id => (USOS[id] || [id, id, id])[li];
  const top = av.rk[0];
  const orc = F.n(av.orc, 1);
  const app = `/app.html?${h.consulta}`;
  const titulo = L.titulo(h);
  const topNome = top ? nomeModelo(top.c) : '';
  const cod = (av.usos.find(u => u.p.id === 'codigo') || {}).x;
  const desc = top ? L.desc(h, L.aprox(av.n), topNome, F.tps(top.enc.tps_est)) : L.vazio(h);

  const item = (x, i) => {
    const v = x.enc.variante, nivel = x.enc.encaixe && x.enc.encaixe.nivel;
    const cmd = 'ollama pull ' + v.pull;
    return `    <li class="pg-item${i < 3 ? ' pg-top' : ''}">
      <span class="pg-pos">${i + 1}</span>
      <div class="pg-info">
        <h3>${esc(nomeModelo(x.c))}</h3>
        <p class="pg-meta"><b>${esc(v.quant)}</b> · ${F.gb(v.bytes)} GB · ~${F.faixa(x.enc.tps_est)} tok/s · ${x.lento ? L.lento : nivel === 'confortavel' ? L.folga : L.limite}</p>
        <p class="pg-usos">${L.bom_para}: ${x.papeis.map(uso).map(esc).join(', ').toLowerCase()}.</p>
        <div class="cmd"><code>${esc(cmd)}</code><button class="btn mini" type="button" data-copiar="${esc(cmd)}">${L.copiar}</button></div>
      </div>
    </li>`;
  };
  const maiores = h.tipo === 'chip' ? todos.filter(o => o.tipo === 'chip' && o.base === h.base && o.mem > h.mem)
    : GPUS_MAIORES.map(id => todos.find(o => o.slug === id)).filter(o => o && (h.tipo === 'cpu' || o.mem > h.mem));
  const vizinhos = todos.filter(o => o.grupo === h.grupo && o.slug !== h.slug);
  const pos = todos.filter(o => o.grupo === h.grupo).findIndex(o => o.slug === h.slug);
  const relacionados = [...new Set([...vizinhos.slice(Math.max(0, pos - 3), pos + 3), ...todos.filter(o => o.tipo === 'gpu' && h.tipo === 'gpu' && o.mem === h.mem && o.slug !== h.slug).slice(0, 4)])]
    .filter(o => !maiores.includes(o)).slice(0, 8);
  const linkHw = o => `<a class="pg-chip" href="${caminho(L, o.slug)}">${esc(L.nome(o))}</a>`;
  const faq = top ? L.faq(h, topNome, top.enc.variante.quant, F.tps(top.enc.tps_est), cod ? nomeModelo(cod.c) : null) : [];

  const corpo = `  <nav class="pg-trilha" aria-label="breadcrumb"><a href="/">${esc(L.nav.inicio)}</a> › <a href="${caminho(L)}">${esc(L.nav.placas)}</a> › <span>${esc(L.nome(h))}</span></nav>
  <section class="pg-cab">
    <span class="l-kicker-s">${L.kicker}</span>
    <h1>${esc(L.h1(h))}</h1>
    <p class="l-lead">${top ? L.lead(h, L.aprox(av.n), topNome, top.enc.variante.quant, F.gb(top.enc.variante.bytes), F.tps(top.enc.tps_est)) : esc(L.vazio(h))}</p>
    <ul class="pg-fatos">${L.fatos(h, orc).map(f => `<li>${esc(f)}</li>`).join('')}</ul>
    <div class="l-ctas">
      <a class="btn primario l-btn-grande" href="${app}#radar" data-ev="radar">${esc(L.cta)}</a>
      ${h.tipo === 'chip' ? '' : `<a class="btn l-btn-grande" href="${app}#calculadora" data-ev="upgrade">${esc(L.cta_calc)}</a>`}
    </div>
  </section>
${top ? `  <section>
    <h2>${esc(L.h2_top(h, Math.min(TOP, av.n)))}</h2>
    <p class="sub">${esc(L.sub_top)}</p>
    <ol class="pg-lista">
${av.rk.slice(0, TOP).map(item).join('\n')}
    </ol>
    <a class="btn primario" href="${app}#radar" data-ev="radar-lista">${esc(L.cta)}</a>
  </section>
  <section>
    <h2>${esc(L.h2_usos)}</h2>
    <div class="tabela-wrap"><table class="pg-tabela">
      <thead><tr>${L.th.map(t => `<th>${esc(t)}</th>`).join('')}</tr></thead>
      <tbody>
${av.usos.map(u => `        <tr><td>${u.p.icone || ''} ${esc(uso(u.p.id))}</td><td><b>${esc(nomeModelo(u.x.c))}</b></td><td>${esc(u.x.enc.variante.quant)} · ${F.gb(u.x.enc.variante.bytes)} GB</td><td>~${F.faixa(u.x.enc.tps_est)} tok/s</td></tr>`).join('\n')}
      </tbody>
    </table></div>
  </section>` : ''}
${av.fora.length ? `  <section>
    <h2>${esc(L.h2_fora)}</h2>
    <p class="sub">${esc(L.sub_fora(orc))}</p>
    <ul class="pg-fora">
${av.fora.map(y => `      <li><b>${esc(nomeModelo(y.c))}</b> — ${esc(L.precisa(F.n(y.precisa_gb, 1)))} (${esc(y.variante.quant)})</li>`).join('\n')}
    </ul>
  </section>` : ''}
${maiores.length ? `  <section>
    <h2>${esc(L.h2_maior)}</h2>
    <p class="sub">${esc(L.sub_maior)}</p>
    <div class="pg-chips">${maiores.map(linkHw).join('')}</div>
  </section>` : ''}
${L.h2_lojas && h.tipo === 'gpu' ? `  <section>
    <h2>${esc(L.h2_lojas(h))}</h2>
    <p class="sub">${esc(L.sub_lojas)}</p>
    <div data-lojas="${esc(h.busca)}"></div>
  </section>` : ''}
  <section>
    <h2>${esc(L.h2_como)}</h2>
    <p>${L.como(h)}</p>
  </section>
${faq.length ? `  <section class="l-faq pg-faq">
    <h2>${esc(L.h2_faq)}</h2>
${faq.map(([p, r]) => `    <details open><summary>${esc(p)}</summary><p>${esc(r)}</p></details>`).join('\n')}
  </section>` : ''}
${relacionados.length ? `  <section>
    <h2>${esc(L.h2_rel)}</h2>
    <div class="pg-chips">${relacionados.map(linkHw).join('')}</div>
  </section>` : ''}`;

  const jsonld = [{ '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
    { '@type': 'ListItem', position: 1, name: L.nav.inicio, item: URL_SITE + '/' },
    { '@type': 'ListItem', position: 2, name: L.nav.placas, item: URL_SITE + caminho(L) },
    { '@type': 'ListItem', position: 3, name: L.nome(h), item: URL_SITE + caminho(L, h.slug) }] }];
  if (faq.length) jsonld.push({ '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: faq.map(([p, r]) => ({ '@type': 'Question', name: p, acceptedAnswer: { '@type': 'Answer', text: r } })) });
  return moldura(L, { slug: h.slug, titulo, desc, corpo, jsonld, hw: h.slug, lojas: !!L.h2_lojas && h.tipo === 'gpu' });
}

function paginaIndice(L, todos) {
  const grupos = Object.keys(GRUPOS).map(k => [k, todos.filter(h => h.grupo === k)]).filter(([, l]) => l.length);
  const corpo = `  <section class="pg-cab">
    <span class="l-kicker-s">${L.kicker.split(' · ')[0]}</span>
    <h1>${esc(L.hub_titulo)}</h1>
    <p class="l-lead">${esc(L.hub_lead)}</p>
    <div class="l-ctas"><a class="btn primario l-btn-grande" href="/app.html#radar" data-ev="radar">${esc(L.hub_cta)}</a></div>
  </section>
${grupos.map(([k, l]) => `  <section>
    <h2>${esc(GRUPOS[k][L.i])}</h2>
    <div class="pg-chips">${l.map(o => `<a class="pg-chip" href="${caminho(L, o.slug)}">${esc(L.nome(o))}</a>`).join('')}</div>
  </section>`).join('\n')}`;
  return moldura(L, { slug: '', titulo: L.hub_titulo, desc: L.hub_desc, corpo, jsonld: null, hw: 'indice' });
}

function sitemap(todos) {
  const urls = ['/', '/app.html', '/privacidade.html'];
  for (const k of LISTA_IDIOMAS) { urls.push(caminho(IDIOMAS[k])); for (const h of todos) urls.push(caminho(IDIOMAS[k], h.slug)); }
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map(u => `  <url><loc>${URL_SITE}${u}</loc></url>`).join('\n')}\n</urlset>\n`;
}

// ---------------------------------------------------------------- gravação
function gerar() {
  const D = carregarDados();
  Calc.configurar(D.constantes);
  const todos = listarHardware(D);
  const arquivos = new Map();
  const avals = new Map(todos.map(h => [h.slug, avaliar(D, h)]));
  for (const k of LISTA_IDIOMAS) {
    const L = IDIOMAS[k];
    arquivos.set(path.join(L.dir, 'index.html'), paginaIndice(L, todos));
    for (const h of todos) arquivos.set(path.join(L.dir, h.slug + '.html'), paginaHardware(L, D, h, avals.get(h.slug), todos));
  }
  arquivos.set('sitemap.xml', sitemap(todos));
  return { arquivos, todos, avals };
}

function main() {
  const { arquivos, todos, avals } = gerar();
  const vazias = todos.filter(h => !avals.get(h.slug).n).map(h => h.slug);
  for (const [nome, html] of arquivos) if (/\bundefined\b|\[object Object\]|\bNaN\b/.test(html)) throw new Error('texto quebrado em ' + nome);
  if (process.argv.includes('--verificar')) { console.log(`ok: ${arquivos.size} arquivos montados em memória (${todos.length} computadores, ${vazias.length} sem nenhum modelo).`); return; }
  let mudou = 0, apagou = 0;
  for (const [rel, conteudo] of arquivos) {
    const p = path.join(SITE, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    if (fs.existsSync(p) && fs.readFileSync(p, 'utf8') === conteudo) continue;
    fs.writeFileSync(p, conteudo); mudou++;
  }
  for (const k of LISTA_IDIOMAS) {     // hardware que saiu do catálogo: a página dele também sai
    const dir = path.join(SITE, IDIOMAS[k].dir);
    for (const f of fs.readdirSync(dir)) if (f.endsWith('.html') && !arquivos.has(path.join(IDIOMAS[k].dir, f))) { fs.unlinkSync(path.join(dir, f)); apagou++; }
  }
  console.log(`${arquivos.size} arquivos (${todos.length} computadores × ${LISTA_IDIOMAS.length} idiomas): ${mudou} gravados, ${apagou} apagados.${vazias.length ? ' Sem nenhum modelo: ' + vazias.join(', ') : ''}`);
}

main();
