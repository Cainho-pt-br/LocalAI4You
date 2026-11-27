#!/usr/bin/env node
/* Gera os prints da listagem da Microsoft Store (1920×1080) a partir do app de verdade, nos 3 idiomas.

   Uso (com o painel rodando):
     cd download/LocalIntelligence && python cli.py painel --sem-navegador      # em outro terminal
     node scripts/prints-store.js [--base=http://127.0.0.1:8765] [--telas=1,4] [--idiomas=pt,en,es]

   Cada print = título + subtítulo (os mesmos da listagem) + a janela do app recortada. O computador mostrado é sempre
   o mesmo (MAQUINA abaixo), injetado na resposta de /api/calc/dados, para o resultado não depender de onde o script roda.
   Telas que precisam de modelos instalados e medidos (2-duelo, 3-placar, 5-decidir) ainda não são geradas aqui.
   Precisa do Playwright (require('playwright')). Saída: empacotar/store/listagem/<idioma>/<n>-<nome>.png */
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')));
const BASE = (args.base || 'http://127.0.0.1:8765').replace(/\/+$/, '');
const IDIOMAS = (args.idiomas || 'pt,en,es').split(',');
const RAIZ = path.resolve(__dirname, '..');
const SAIDA = path.join(RAIZ, 'empacotar', 'store', 'listagem');
const ICONE = path.join(RAIZ, 'empacotar', 'store', 'Assets', 'Square310x310Logo.png');

const MAQUINA = {
  id: 'store', nome: 'Este PC', papel: 'Estação local (auto-detectada)', so: 'Windows 11', cpu: 'AMD Ryzen 5 5600',
  nucleos: 6, ram_gb: 32, gpu: { nome: 'GeForce RTX 4060', vram_gb: 8, bw_gbs: 272 }, unificada: false,
  bw_gbs_min: 40, bw_gbs_max: 51, simd: ['avx', 'avx2'], reserva_so_gb: 4, runtime: 'ollama',
};

// Janela do app: 1400×734 CSS px ampliados ≈1,114× = 1560×818, o recorte que cabe abaixo do título.
const JANELA = { width: 1400, height: 734 }, ESCALA = 1560 / 1400;

const TEXTOS = {
  1: {
    nome: '1-seu-modelo', aba: 'radar',
    pt: ['A melhor IA para o ', 'seu computador', 'Escolhida para o seu hardware, com o passo a passo para começar.'],
    en: ['The best AI for ', 'your computer', 'Picked for your hardware, with step-by-step instructions to start.'],
    es: ['La mejor IA para ', 'tu computadora', 'Elegida para tu hardware, con el paso a paso para empezar.'],
  },
  4: {
    nome: '4-trocar-placa', aba: 'calculadora',
    pt: ['Vale trocar de placa? ', 'Veja antes de gastar', 'O que muda com mais memória de vídeo, modelo a modelo.'],
    en: ['Worth a new GPU? ', 'See before you buy', 'What changes with more video memory, model by model.'],
    es: ['¿Vale cambiar de tarjeta? ', 'Míralo antes de gastar', 'Qué cambia con más memoria de video, modelo a modelo.'],
  },
};
const TELAS = (args.telas || '1,4').split(',').map(Number).filter(n => TEXTOS[n]);

/* Coloca a tela certa no lugar antes do print. Devolve o elemento que deve ficar no topo da janela. */
async function prepararTela(p, n) {
  if (n === 1) {
    await p.waitForSelector('.radar-topo');
    return ['.radar-topo', 16];
  }
  if (n === 4) {
    // 1º "Calcular o que roda →" (o texto passa pela tradução, por isso a busca é pela classe/ordem)
    const calc = p.locator('button', { hasText: /→/ }).first();
    if (await calc.count()) { await calc.click(); await p.waitForTimeout(1200); }
    await p.waitForSelector('#calc-sec-upgrade', { timeout: 15000 });
    return ['#calc-sec-upgrade', 96];   // desconta a barra de passos, que fica fixa no topo
  }
}

function moldura(lang, t, png) {
  const [antes, destaque, sub] = t[lang];
  const ico = 'data:image/png;base64,' + fs.readFileSync(ICONE).toString('base64');
  const app = 'data:image/png;base64,' + png.toString('base64');
  return `<!doctype html><meta charset="utf-8"><style>
  *{box-sizing:border-box;margin:0}
  body{width:1920px;height:1080px;overflow:hidden;font-family:Inter,"Segoe UI",system-ui,sans-serif;color:#0f172a;
    background:radial-gradient(1200px 700px at 0% 0%,#c7d7fb 0%,transparent 60%),radial-gradient(1100px 800px at 100% 0%,#dccbf7 0%,transparent 60%),linear-gradient(180deg,#eef2fb,#f3f1fb)}
  .marca{position:absolute;left:110px;top:61px;display:flex;align-items:center;gap:14px;font-size:28px;font-weight:600;color:#1f2a44}
  .marca img{width:52px;height:52px;border-radius:12px}
  .tit{position:absolute;right:110px;top:52px;max-width:1150px;text-align:right}
  h1{font-size:64px;line-height:1.05;letter-spacing:-1.5px;font-weight:800}
  h1 span{background:linear-gradient(90deg,#2563eb,#9333ea 60%,#c026d3);-webkit-background-clip:text;background-clip:text;color:transparent}
  p{margin-top:14px;font-size:30px;color:#475569}
  .app{position:absolute;left:180px;top:262px;width:1560px;height:818px;border-radius:28px 28px 0 0;overflow:hidden;
    border:1px solid rgba(148,163,184,.45);border-bottom:0;box-shadow:0 30px 80px rgba(30,41,99,.18)}
  .app img{display:block;width:1560px;height:818px}
  </style><div class="marca"><img src="${ico}">Local AI 4 You</div>
  <div class="tit"><h1>${antes}<span>${destaque}</span></h1><p>${sub}</p></div>
  <div class="app"><img src="${app}"></div>`;
}

(async () => {
  const b = await chromium.launch();
  for (const lang of IDIOMAS) {
    const ctx = await b.newContext({ viewport: JANELA, deviceScaleFactor: ESCALA, locale: lang });
    await ctx.addInitScript(l => {
      try {
        localStorage.setItem('li-idioma', l); localStorage.setItem('li-tema', 'light');
        localStorage.setItem('li-passos-oculto', '1'); localStorage.setItem('li-visitou', '1');
      } catch (e) { /* ok */ }
    }, lang);
    await ctx.route('**/api/calc/dados', async rota => {
      const r = await rota.fetch(); const d = await r.json();
      d.maquinas = [MAQUINA]; d.esta_maquina = MAQUINA.id;
      await rota.fulfill({ response: r, json: d });
    });
    // Quem usa o app tem o Ollama ligado; aqui (CI ou máquina de quem gera) pode não ter.
    await ctx.route('**/api/saude', async rota => {
      const r = await rota.fetch(); const d = await r.json();
      d.ollama = { ...d.ollama, no_ar: true, instalado: true, versao: '0.13.0' };
      await rota.fulfill({ response: r, json: d });
    });
    for (const n of TELAS) {
      const t = TEXTOS[n];
      const p = await ctx.newPage();
      await p.goto(`${BASE}/#${t.aba}`, { waitUntil: 'networkidle' });
      await p.addStyleTag({ content: '#primeiros-passos{display:none!important}' });
      await p.waitForTimeout(1200);
      const topo = await prepararTela(p, n);
      if (topo) await p.evaluate(([sel, folga]) => { const el = document.querySelector(sel); if (el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - folga); }, topo);
      await p.waitForTimeout(500);
      const png = await p.screenshot();
      await p.close();
      const comp = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
      await comp.setContent(moldura(lang, t, png), { waitUntil: 'load' });
      const destino = path.join(SAIDA, lang, t.nome + '.png');
      await comp.screenshot({ path: destino });
      await comp.close();
      console.log('gerado', path.relative(RAIZ, destino));
    }
    await ctx.close();
  }
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
