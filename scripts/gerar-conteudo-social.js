#!/usr/bin/env node
'use strict';
/* Fábrica automática de conteúdo para redes sociais (zero edição manual).
   Lê site/dados.js e calcula rankings reais usando download/LocalIntelligence/web/calc.js.

   Uso:
     node scripts/gerar-conteudo-social.js                     # gera a pauta do dia em PT e EN
     node scripts/gerar-conteudo-social.js --pauta=duelo-3060-4060 --idioma=pt
     node scripts/gerar-conteudo-social.js --listar            # lista todas as pautas disponíveis
     node scripts/gerar-conteudo-social.js --pauta=novidade    # força a pauta de lançamento (último mês)

   Novidade: se a biblioteca oficial do Ollama ganhou um modelo nos últimos 2 dias que entra no Top 3 de alguma placa
   popular, a pauta do dia vira "Saiu X: já roda na sua placa?" em vez da rotação (--sem-novidade desliga).

   Saída em conteudo-social/<YYYY-MM-DD>/<idioma>/<slug>/:
     • slides/slide-1.html .. slide-5.html   (1080×1350 · Carrossel Instagram / LinkedIn / X)
     • cenas-video/cena-1.html .. cena-4.html (1080×1920 · Vídeo vertical TikTok / Reels / Shorts)
     • roteiro.json                           (narração por cena para Edge-TTS + FFmpeg)
     • legendas.md                            (legendas prontas com UTM por rede) */
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

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtTps = e => {
  const t = Array.isArray(e.enc.tps_est) ? e.enc.tps_est[0] : e.enc.tps_est;
  return t >= 10 ? String(Math.round(t)) : String(Math.round(t * 10) / 10);
};

// Rotação de pautas com alto potencial de engajamento (duelos + placas populares)
const PAUTAS = [
  { id: 'duelo-3060-4060', tipo: 'duelo', a: { tipo: 'gpu', id: 'rtx-3060-12' }, b: { tipo: 'gpu', id: 'rtx-4060' } },
  { id: 'placa-rtx-4060', tipo: 'placa', alvo: { tipo: 'gpu', id: 'rtx-4060' } },
  { id: 'duelo-cpu16-3050', tipo: 'duelo', a: { tipo: 'cpu', ram: 16 }, b: { tipo: 'gpu', id: 'rtx-3050-8' } },
  { id: 'placa-rtx-3060-12', tipo: 'placa', alvo: { tipo: 'gpu', id: 'rtx-3060-12' } },
  { id: 'duelo-4060ti16-4070', tipo: 'duelo', a: { tipo: 'gpu', id: 'rtx-4060-ti-16' }, b: { tipo: 'gpu', id: 'rtx-4070' } },
  { id: 'placa-cpu-16gb', tipo: 'placa', alvo: { tipo: 'cpu', ram: 16 } },
  { id: 'duelo-m2-3060', tipo: 'duelo', a: { tipo: 'chip', id: 'm2', ram: 16 }, b: { tipo: 'gpu', id: 'rtx-3060-12' } },
  { id: 'placa-m2-16gb', tipo: 'placa', alvo: { tipo: 'chip', id: 'm2', ram: 16 } },
  { id: 'duelo-5060ti16-5070', tipo: 'duelo', a: { tipo: 'gpu', id: 'rtx-5060-ti-16' }, b: { tipo: 'gpu', id: 'rtx-5070' } },
  { id: 'placa-rtx-5060-ti-16', tipo: 'placa', alvo: { tipo: 'gpu', id: 'rtx-5060-ti-16' } },
  { id: 'duelo-rx7600xt-4060', tipo: 'duelo', a: { tipo: 'gpu', id: 'rx-7600-xt' }, b: { tipo: 'gpu', id: 'rtx-4060' } },
  { id: 'placa-gtx-1660-super', tipo: 'placa', alvo: { tipo: 'gpu', id: 'gtx-1660-super' } },
  { id: 'placa-rtx-4070', tipo: 'placa', alvo: { tipo: 'gpu', id: 'rtx-4070' } },
  { id: 'placa-rtx-3090', tipo: 'placa', alvo: { tipo: 'gpu', id: 'rtx-3090' } },
];

function resolverHardware(D, spec, nTop = 3) {
  const hw = D.hardware;
  const sis = (hw.sistemas || []).find(s => s.id === 'windows') || hw.sistemas[0];
  const mac = (hw.sistemas || []).find(s => s.id === 'macos') || sis;
  const cpu = hw.cpus.find(c => /Zen 4/.test(c.nome)) || hw.cpus[0];
  const memPerfil = cpu.bw ? { bw_min: cpu.bw[0], bw_max: cpu.bw[1] }
    : Calc.memBw(hw.memorias_ram.find(m => m.id === cpu.mem) || hw.memorias_ram[0], cpu.canais || 2);

  let perfil, nomePt, nomeEn, memLabel, slug;
  if (spec.tipo === 'gpu') {
    const g = hw.gpus.find(x => x.id === spec.id);
    if (!g) throw new Error('GPU não encontrada: ' + spec.id);
    perfil = Calc.perfilGpu({ gpu: g, n: 1, ram_gb: 32, mem: memPerfil, cpu, sistema: sis });
    const curto = g.nome.replace(/^(NVIDIA|AMD|Intel)\s+/i, '').replace(/^GeForce\s+/i, '');
    nomePt = curto;
    nomeEn = curto;
    memLabel = `${g.vram_gb} GB VRAM`;
    slug = g.id;
  } else if (spec.tipo === 'chip') {
    const u = hw.unificadas.find(x => x.id === spec.id);
    if (!u) throw new Error('Chip não encontrado: ' + spec.id);
    perfil = Calc.perfilUnificado({ chip: u, ram_gb: spec.ram, cpu: null, sistema: mac });
    nomePt = `${u.nome} ${spec.ram} GB`;
    nomeEn = `${u.nome} ${spec.ram} GB`;
    memLabel = `${spec.ram} GB unificada`;
    slug = `${u.id}-${spec.ram}gb`;
  } else {
    perfil = Calc.perfilCpu({ ram_gb: spec.ram, mem: memPerfil, cpu, sistema: sis });
    nomePt = `PC sem GPU (${spec.ram} GB RAM)`;
    nomeEn = `No-GPU PC (${spec.ram} GB RAM)`;
    memLabel = `${spec.ram} GB RAM`;
    slug = `cpu-${spec.ram}gb`;
  }
  perfil.reserva_vram_gb = perfil.reserva_vram_gb ?? D.reserva_vram_gb ?? 1.3;
  const ids = (D.papeis || []).filter(p => !p.sem_nota).map(p => p.id);
  const rk = Calc.ranking(D, perfil, ids, { kv: 'q8_0' });
  const rkCod = Calc.ranking(D, perfil, ['codigo'], { kv: 'q8_0' });
  return {
    slug, nomePt, nomeEn, memLabel, total: rk.length,
    top3: rk.slice(0, 3),
    top: rk.slice(0, nTop),
    melhorCodigo: rkCod[0] || rk[0] || null,
    notaMax: rk[0] ? Math.round(rk[0].nota) : 0,
  };
}

const CSS_BASE = `
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Inter, "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
  background: #0b1117; color: #f1f5f9;
  display: flex; flex-direction: column; justify-content: space-between;
  padding: 72px 68px; overflow: hidden; position: relative;
}
body::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background:
    radial-gradient(60% 45% at 15% 12%, rgba(20, 184, 166, 0.22), transparent 70%),
    radial-gradient(50% 40% at 88% 85%, rgba(14, 165, 233, 0.16), transparent 70%);
}
body > * { position: relative; z-index: 1; }
.top { display: flex; align-items: center; justify-content: space-between; }
.brand { display: flex; align-items: center; gap: 14px; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; color: #e2e8f0; }
.brand-dot { width: 18px; height: 18px; border-radius: 50%; background: #2dd4bf; box-shadow: 0 0 0 6px rgba(45, 212, 191, 0.2); }
.tag { padding: 10px 18px; border-radius: 999px; background: rgba(45, 212, 191, 0.14); color: #5eead4; font-size: 22px; font-weight: 700; letter-spacing: 0.02em; }
.mid { display: flex; flex-direction: column; gap: 28px; }
h1 { font-size: 74px; line-height: 1.06; letter-spacing: -0.035em; font-weight: 800; }
h1 em { font-style: normal; color: #2dd4bf; }
h2 { font-size: 54px; line-height: 1.1; letter-spacing: -0.03em; font-weight: 800; }
.sub { font-size: 32px; line-height: 1.38; color: #94a3b8; }
.card { background: #131c26; border: 1px solid #243344; border-radius: 26px; padding: 30px 32px; display: flex; align-items: center; gap: 24px; }
.card.gold { border-color: #f59e0b; background: linear-gradient(135deg, #1b1d17, #131c26); }
.rank { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; font-size: 30px; font-weight: 800; flex: none; background: #1e293b; color: #f8fafc; }
.card.gold .rank { background: #f59e0b; color: #0b1117; }
.info { flex: 1; min-width: 0; }
.info b { display: block; font-size: 34px; line-height: 1.15; margin-bottom: 6px; }
.info small { font-size: 24px; color: #94a3b8; display: block; }
.score { font-size: 48px; font-weight: 800; color: #2dd4bf; font-variant-numeric: tabular-nums; }
.cmd { margin-top: 12px; padding: 14px 18px; border-radius: 14px; background: #0b1117; border: 1px solid #243344; font-family: ui-monospace, Menlo, monospace; font-size: 24px; color: #7dd3fc; word-break: break-all; }
.vs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.vs-box { background: #131c26; border: 1px solid #243344; border-radius: 26px; padding: 30px; display: flex; flex-direction: column; gap: 14px; }
.vs-box.win { border-color: #2dd4bf; background: linear-gradient(180deg, rgba(45,212,191,0.12), #131c26); }
.vs-box h3 { font-size: 34px; font-weight: 800; }
.vs-stat { font-size: 58px; font-weight: 800; color: #2dd4bf; line-height: 1; }
.vs-label { font-size: 23px; color: #94a3b8; }
.foot { display: flex; align-items: center; justify-content: space-between; font-size: 24px; color: #64748b; border-top: 1px solid #1e293b; padding-top: 24px; }
.foot b { color: #e2e8f0; }
`;

function paginaHtml(w, h, corpo) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${CSS_BASE}
  body { width: ${w}px; height: ${h}px; }</style></head><body>${corpo}</body></html>`;
}

function cardModelo(e, pos) {
  const v = e.enc.variante || {};
  return `<div class="card ${pos === 1 ? 'gold' : ''}">
    <div class="rank">${pos}</div>
    <div class="info">
      <b>${esc(e.c.nome)}</b>
      <small>${esc(v.quant || 'Q4')} · ~${fmtTps(e)} tok/s</small>
      ${v.pull ? `<div class="cmd">ollama run ${esc(v.pull)}</div>` : ''}
    </div>
    <div class="score">${Math.round(e.nota)}</div>
  </div>`;
}

function gerarPacotePlaca(hw, lang) {
  const pt = lang === 'pt';
  const nome = pt ? hw.nomePt : hw.nomeEn;
  const linkBase = `${URL_SITE}/${pt ? 'placa' : 'en/gpu'}/${hw.slug}.html`;
  const top1 = hw.top3[0];
  const v1 = top1 ? (top1.enc.variante || {}) : {};
  const cod = hw.melhorCodigo;

  const slides = [
    // Slide 1: Gancho
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'IA LOCAL GRÁTIS' : 'FREE LOCAL AI'}</span></div>
     <div class="mid">
       <h1>${pt ? `Quais IAs rodam de verdade na <em>${esc(nome)}</em>?` : `Which AIs actually run on the <em>${esc(nome)}</em>?`}</h1>
       <p class="sub">${pt ? `${hw.total} modelos cabem hoje sem pagar mensalidade e 100% offline. Arrasta para ver o Top 3 →` : `${hw.total} models fit today, free and 100% offline. Swipe for the Top 3 →`}</p>
     </div>
     <div class="foot"><span>${esc(hw.memLabel)}</span><b>localai4you.vercel.app</b></div>`,

    // Slide 2: Top 1 destaque
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">#1 · ${esc(nome)}</span></div>
     <div class="mid">
       <h2>${pt ? 'O mais inteligente que cabe hoje' : 'The smartest model that fits today'}</h2>
       ${top1 ? cardModelo(top1, 1) : ''}
       <p class="sub">${pt ? 'Roda direto no Ollama com um único comando. Sem conta, sem enviar seus dados.' : 'Runs straight on Ollama with a single command. No account, no cloud.'}</p>
     </div>
     <div class="foot"><span>${pt ? 'Estimado por VRAM real' : 'Estimated from real VRAM'}</span><b>2 / 5</b></div>`,

    // Slide 3: Top 2 e 3
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">TOP 3 · ${esc(nome)}</span></div>
     <div class="mid">
       <h2>${pt ? 'Outras 2 ótimas opções' : '2 more great picks'}</h2>
       ${hw.top3[1] ? cardModelo(hw.top3[1], 2) : ''}
       ${hw.top3[2] ? cardModelo(hw.top3[2], 3) : ''}
     </div>
     <div class="foot"><span>${pt ? 'Catálogo atualizado todo dia' : 'Catalog updated daily'}</span><b>3 / 5</b></div>`,

    // Slide 4: Melhor para código
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'PARA PROGRAMAR' : 'FOR CODING'}</span></div>
     <div class="mid">
       <h2>${pt ? `Melhor modelo para código na ${esc(nome)}` : `Best coding model on ${esc(nome)}`}</h2>
       ${cod ? cardModelo(cod, 1) : ''}
       <p class="sub">${pt ? 'Quer testar qual é melhor na prática? O app gratuito faz duelos no seu próprio PC.' : 'Want to test which wins on your PC? Our free local app runs real head-to-head duels.'}</p>
     </div>
     <div class="foot"><span>${pt ? 'Código aberto · Apache-2.0' : 'Open source · Apache-2.0'}</span><b>4 / 5</b></div>`,

    // Slide 5: CTA
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'TESTE O SEU PC' : 'TEST YOUR PC'}</span></div>
     <div class="mid">
       <h1>${pt ? 'Qual é a <em>sua</em> placa de vídeo?' : 'What is <em>your</em> graphics card?'}</h1>
       <p class="sub">${pt ? 'Comenta aqui a sua GPU (ou quanta RAM você tem) que a próxima lista pode ser a dela — ou testa agora grátis no link da bio.' : 'Drop your GPU (or RAM) in the comments for the next video — or test yours free via the link in bio.'}</p>
       <div class="cmd">${esc(linkBase)}</div>
     </div>
     <div class="foot"><span>${pt ? 'Grátis · Sem cadastro' : 'Free · No signup'}</span><b>5 / 5</b></div>`,
  ];

  const cenasVideo = [
    { html: slides[0], fala: pt
      ? `Você tem uma ${nome}? Hoje cabem ${hw.total} modelos de inteligência artificial grátis e offline nela.`
      : `Got a ${nome}? Today, ${hw.total} free offline AI models fit right on it.` },
    { html: slides[1], fala: pt
      ? `Em primeiro lugar, o ${top1 ? top1.c.nome : 'líder'}, rodando a cerca de ${top1 ? fmtTps(top1) : '20'} tokens por segundo.`
      : `Number one is ${top1 ? top1.c.nome : 'our top pick'}, running at around ${top1 ? fmtTps(top1) : '20'} tokens per second.` },
    { html: slides[2], fala: pt
      ? `Logo atrás vêm ${hw.top3[1] ? hw.top3[1].c.nome : ''} e ${hw.top3[2] ? hw.top3[2].c.nome : ''}, todos com o comando do Ollama pronto para copiar.`
      : `Right behind are ${hw.top3[1] ? hw.top3[1].c.nome : ''} and ${hw.top3[2] ? hw.top3[2].c.nome : ''}, with ready-to-copy Ollama commands.` },
    { html: slides[4], fala: pt
      ? `Qual é a sua placa de vídeo? Comenta aí ou testa grátis no Local AI 4 You, link na bio.`
      : `What graphics card do you have? Comment below or check yours free at Local AI 4 You, link in bio.` },
  ];

  const legendas = pt ? `# Legendas prontas — ${nome} (PT-BR)

## TikTok / Reels / YouTube Shorts
${hw.total} modelos de IA rodam grátis e 100% offline na ${nome} 🤯
Hoje o #1 é o ${top1 ? top1.c.nome : ''} (~${top1 ? fmtTps(top1) : '?'} tok/s)${v1.pull ? ` — comando: \`ollama run ${v1.pull}\`` : ''}.

Quer ver a lista completa para o SEU computador?
👉 ${linkBase}?utm_source=tiktok&utm_campaign=${hw.slug}

Comenta qual é a sua placa que eu trago o próximo ranking!
#ialocal #ollama #hardware #pcgamer #inteligenciaartificial #rtx

## Instagram (Carrossel)
As melhores IAs grátis que rodam OFFLINE na ${nome} (sem mensalidade e sem enviar dados pra nuvem).
Arrasta pro lado para ver o Top 3 + o melhor modelo para programar →

Link na bio para testar qualquer placa ou PC sem GPU:
${linkBase}?utm_source=instagram&utm_campaign=${hw.slug}

## X / Threads
Testamos no catálogo de hoje o que cabe na ${nome} (${hw.memLabel}):
1) ${hw.top3[0] ? hw.top3[0].c.nome : '—'} (~${hw.top3[0] ? fmtTps(hw.top3[0]) : '?'} tok/s)
2) ${hw.top3[1] ? hw.top3[1].c.nome : '—'} (~${hw.top3[1] ? fmtTps(hw.top3[1]) : '?'} tok/s)
3) ${hw.top3[2] ? hw.top3[2].c.nome : '—'} (~${hw.top3[2] ? fmtTps(hw.top3[2]) : '?'} tok/s)

Lista completa + comandos Ollama: ${linkBase}?utm_source=x&utm_campaign=${hw.slug}
` : `# Ready-to-post captions — ${nome} (EN)

## TikTok / Reels / YouTube Shorts
${hw.total} local AI models run free and 100% offline on the ${nome} 🤯
Today's #1 pick is ${top1 ? top1.c.nome : ''} (~${top1 ? fmtTps(top1) : '?'} tok/s)${v1.pull ? ` — run: \`ollama run ${v1.pull}\`` : ''}.

Check the full list for YOUR PC (free, open source):
👉 ${linkBase}?utm_source=tiktok&utm_campaign=${hw.slug}

Drop your GPU in the comments for the next ranking!
#localai #ollama #localllm #gpu #pcbuild #ai

## X / Reddit
Today's top local LLMs for ${nome} (${hw.memLabel}) — ${hw.total} models fit:
1) ${hw.top3[0] ? hw.top3[0].c.nome : '—'} (~${hw.top3[0] ? fmtTps(hw.top3[0]) : '?'} tok/s)
2) ${hw.top3[1] ? hw.top3[1].c.nome : '—'} (~${hw.top3[1] ? fmtTps(hw.top3[1]) : '?'} tok/s)
3) ${hw.top3[2] ? hw.top3[2].c.nome : '—'} (~${hw.top3[2] ? fmtTps(hw.top3[2]) : '?'} tok/s)

Full list & copyable Ollama commands: ${linkBase}?utm_source=x&utm_campaign=${hw.slug}
`;

  return { slides, cenasVideo, legendas, linkBase };
}

function gerarPacoteDuelo(a, b, slug, lang) {
  const pt = lang === 'pt';
  const nA = pt ? a.nomePt : a.nomeEn;
  const nB = pt ? b.nomePt : b.nomeEn;
  const venceA = a.notaMax >= b.notaMax;
  const vencedor = venceA ? a : b;
  const nV = pt ? vencedor.nomePt : vencedor.nomeEn;
  const linkBase = `${URL_SITE}/${pt ? 'placa' : 'en/gpu'}/${vencedor.slug}.html`;

  const slides = [
    // Slide 1: Gancho polêmico
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'DUELO DE IA LOCAL' : 'LOCAL AI DUEL'}</span></div>
     <div class="mid">
       <h1><em>${esc(nA)}</em> vs <em>${esc(nB)}</em></h1>
       <p class="sub">${pt ? 'Qual das duas roda inteligência artificial melhor no seu PC? O resultado surpreende muita gente →' : 'Which one runs local AI better? The answer surprises most people →'}</p>
     </div>
     <div class="foot"><span>${esc(a.memLabel)} × ${esc(b.memLabel)}</span><b>localai4you.vercel.app</b></div>`,

    // Slide 2: Placar lado a lado
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'PLACAR REAL' : 'HEAD TO HEAD'}</span></div>
     <div class="mid">
       <h2>${pt ? 'Mais VRAM = modelos mais inteligentes' : 'More VRAM = smarter models'}</h2>
       <div class="vs-grid">
         <div class="vs-box ${venceA ? 'win' : ''}">
           <h3>${esc(nA)}</h3>
           <div class="vs-label">${esc(a.memLabel)}</div>
           <div class="vs-stat">${a.notaMax}</div>
           <div class="vs-label">${pt ? `nota máx · ${a.total} modelos` : `top score · ${a.total} models`}</div>
         </div>
         <div class="vs-box ${!venceA ? 'win' : ''}">
           <h3>${esc(nB)}</h3>
           <div class="vs-label">${esc(b.memLabel)}</div>
           <div class="vs-stat">${b.notaMax}</div>
           <div class="vs-label">${pt ? `nota máx · ${b.total} modelos` : `top score · ${b.total} models`}</div>
         </div>
       </div>
     </div>
     <div class="foot"><span>${pt ? `Vencedora em IA: ${nV}` : `AI Winner: ${nV}`}</span><b>2 / 5</b></div>`,

    // Slide 3: Melhor modelo na A
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${esc(nA)}</span></div>
     <div class="mid">
       <h2>${pt ? `Melhor modelo na ${esc(nA)}` : `Top model on ${esc(nA)}`}</h2>
       ${a.top3[0] ? cardModelo(a.top3[0], 1) : ''}
       ${a.top3[1] ? cardModelo(a.top3[1], 2) : ''}
     </div>
     <div class="foot"><span>${esc(a.memLabel)}</span><b>3 / 5</b></div>`,

    // Slide 4: Melhor modelo na B
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${esc(nB)}</span></div>
     <div class="mid">
       <h2>${pt ? `Melhor modelo na ${esc(nB)}` : `Top model on ${esc(nB)}`}</h2>
       ${b.top3[0] ? cardModelo(b.top3[0], 1) : ''}
       ${b.top3[1] ? cardModelo(b.top3[1], 2) : ''}
     </div>
     <div class="foot"><span>${esc(b.memLabel)}</span><b>4 / 5</b></div>`,

    // Slide 5: CTA
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'SIMULE O UPGRADE' : 'SIMULATE UPGRADE'}</span></div>
     <div class="mid">
       <h1>${pt ? 'Qual placa você colocaria no <em>próximo duelo</em>?' : 'Which GPUs should we <em>compare next</em>?'}</h1>
       <p class="sub">${pt ? 'Comenta as duas placas aqui embaixo — e testa grátis o que cabe no seu PC no link da bio.' : 'Comment two GPUs below — and test your own PC for free via the link in bio.'}</p>
       <div class="cmd">${esc(linkBase)}</div>
     </div>
     <div class="foot"><span>${pt ? 'Grátis · Código aberto' : 'Free · Open source'}</span><b>5 / 5</b></div>`,
  ];

  const cenasVideo = [
    { html: slides[0], fala: pt
      ? `${nA} contra ${nB} para rodar inteligência artificial local. Qual das duas ganha?`
      : `${nA} versus ${nB} for running local AI. Which one actually wins?` },
    { html: slides[1], fala: pt
      ? `Na ${nA} cabem ${a.total} modelos com nota máxima ${a.notaMax}. Na ${nB} cabem ${b.total}, nota máxima ${b.notaMax}. Em IA local, memória de vídeo manda.`
      : `The ${nA} fits ${a.total} models scoring up to ${a.notaMax}. The ${nB} fits ${b.total}, scoring up to ${b.notaMax}. In local AI, VRAM is king.` },
    { html: venceA ? slides[2] : slides[3], fala: pt
      ? `A vencedora é a ${nV}, puxando o ${vencedor.top3[0] ? vencedor.top3[0].c.nome : 'modelo líder'} direto no Ollama.`
      : `The winner is the ${nV}, running ${vencedor.top3[0] ? vencedor.top3[0].c.nome : 'the top model'} right on Ollama.` },
    { html: slides[4], fala: pt
      ? `Qual duelo você quer ver amanhã? Comenta sua placa ou testa grátis no Local AI 4 You.`
      : `Which duel do you want tomorrow? Comment your GPU or test yours free at Local AI 4 You.` },
  ];

  const legendas = pt ? `# Legendas prontas — ${nA} vs ${nB} (PT-BR)

## TikTok / Reels / YouTube Shorts
${nA} vs ${nB} pra rodar IA local no seu PC: quem vence? ⚡
• ${nA} (${a.memLabel}): ${a.total} modelos · nota máx ${a.notaMax}
• ${nB} (${b.memLabel}): ${b.total} modelos · nota máx ${b.notaMax}

Em jogos a mais nova pode ganhar, mas em IA local a VRAM manda!
Testa grátis a sua placa: ${linkBase}?utm_source=tiktok&utm_campaign=${slug}

Comenta qual duelo você quer ver amanhã 👇
#pcgamer #hardware #ialocal #ollama #nvidia #amd

## X / Threads
${nA} vs ${nB} para IA local (catálogo de hoje):
- ${nA}: ${a.total} modelos, líder ${a.top3[0] ? a.top3[0].c.nome : '—'} (nota ${a.notaMax})
- ${nB}: ${b.total} modelos, líder ${b.top3[0] ? b.top3[0].c.nome : '—'} (nota ${b.notaMax})

Compare qualquer placa grátis: ${URL_SITE}/app.html#calculadora?utm_source=x&utm_campaign=${slug}
` : `# Ready-to-post captions — ${nA} vs ${nB} (EN)

## TikTok / Reels / YouTube Shorts
${nA} vs ${nB} for local AI: which one wins? ⚡
• ${nA} (${a.memLabel}): ${a.total} models · top score ${a.notaMax}
• ${nB} (${b.memLabel}): ${b.total} models · top score ${b.notaMax}

In local LLMs, VRAM beats raw gaming FPS.
Test your own PC free: ${linkBase}?utm_source=tiktok&utm_campaign=${slug}
#localllm #localai #ollama #gpu #pcgaming #ai
`;

  return { slides, cenasVideo, legendas, linkBase };
}

function gravarPacote(pasta, pacote, lang, pautaId) {
  const dirSlides = path.join(pasta, 'slides');
  const dirCenas = path.join(pasta, 'cenas-video');
  fs.mkdirSync(dirSlides, { recursive: true });
  fs.mkdirSync(dirCenas, { recursive: true });

  pacote.slides.forEach((corpo, i) => {
    fs.writeFileSync(path.join(dirSlides, `slide-${i + 1}.html`), paginaHtml(1080, 1350, corpo));
  });
  pacote.cenasVideo.forEach((c, i) => {
    fs.writeFileSync(path.join(dirCenas, `cena-${i + 1}.html`), paginaHtml(1080, 1920, c.html));
  });
  fs.writeFileSync(path.join(pasta, 'legendas.md'), pacote.legendas);
  fs.writeFileSync(path.join(pasta, 'roteiro.json'), JSON.stringify({
    pauta: pautaId,
    idioma: lang,
    voz_edge_tts: lang === 'pt' ? 'pt-BR-AntonioNeural' : 'en-US-AndrewNeural',
    link: pacote.linkBase,
    cenas: pacote.cenasVideo.map((c, i) => ({
      arquivo: `cenas-video/cena-${i + 1}.html`,
      fala: c.fala,
    })),
  }, null, 2));
}

// ---------------------------------------------------------------- pauta de novidade (lançamentos)
// Placas que o público mais tem: é nelas que medimos se o lançamento muda alguma coisa.
const HW_NOVIDADE = [
  { tipo: 'cpu', ram: 16 }, { tipo: 'gpu', id: 'rtx-3050-8' }, { tipo: 'gpu', id: 'rtx-3060-12' }, { tipo: 'gpu', id: 'rtx-4060' },
  { tipo: 'gpu', id: 'rtx-4060-ti-16' }, { tipo: 'gpu', id: 'rtx-5060-ti-16' }, { tipo: 'gpu', id: 'rtx-4070' }, { tipo: 'gpu', id: 'rtx-3090' },
  { tipo: 'chip', id: 'm2', ram: 16 },
];
const diasDesde = c => { const t = Date.parse(c.lancamento || ''); return isNaN(t) ? Infinity : (Date.now() - t) / 864e5; };

/* Procura a família lançada há até `janela` dias (só a biblioteca oficial do Ollama: um comando e pronto, o que dá
   para mostrar num vídeo de 30 s) que entra no Top 3 em mais placas populares. null se nenhuma muda nada. */
function acharNovidade(D, janela) {
  const novas = new Map();
  for (const c of D.candidatos || []) {
    if (c.confianca !== 'ollama-oficial' || diasDesde(c) > janela) continue;
    novas.set(c.familia || c.id, c);
  }
  if (!novas.size) return null;
  const hws = HW_NOVIDADE.map(spec => { try { return resolverHardware(D, spec, 10); } catch (e) { return null; } }).filter(Boolean);
  let melhor = null;
  for (const [familia, ref] of novas) {
    const onde = [], fora = [];
    for (const hw of hws) {
      const pos = hw.top.findIndex(e => (e.c.familia || e.c.id) === familia);
      if (pos >= 0 && pos < 3) onde.push({ hw, pos: pos + 1, e: hw.top[pos] });
      else fora.push({ hw, pos: pos >= 0 ? pos + 1 : null });
    }
    if (!onde.length) continue;
    const peso = onde.reduce((t, o) => t + (4 - o.pos), 0);
    if (!melhor || peso > melhor.peso || (peso === melhor.peso && (ref.pop || 0) > (melhor.ref.pop || 0)))
      melhor = { familia, ref, onde, fora, peso, dias: Math.floor(diasDesde(ref)) };
  }
  return melhor;
}

function gerarPacoteNovidade(nv, lang) {
  const pt = lang === 'pt';
  const nomeHw = hw => pt ? hw.nomePt : hw.nomeEn;
  const nome = nv.familia;
  const lider = nv.onde.slice().sort((a, b) => a.pos - b.pos || b.hw.total - a.hw.total)[0];
  const linkBase = `${URL_SITE}/${pt ? 'placa' : 'en/gpu'}/${lider.hw.slug}.html`;
  const quando = nv.dias <= 0 ? (pt ? 'hoje' : 'today') : nv.dias === 1 ? (pt ? 'ontem' : 'yesterday') : (pt ? `há ${nv.dias} dias` : `${nv.dias} days ago`);
  const posTxt = p => pt ? (p === 1 ? '#1 — o melhor' : `#${p} no Top 3`) : (p === 1 ? '#1 — the best' : `#${p} in the Top 3`);
  const linhaOnde = o => `<div class="card ${o.pos === 1 ? 'gold' : ''}"><div class="rank">${o.pos}</div><div class="info"><b>${esc(nomeHw(o.hw))}</b><small>${esc(o.e.c.nome)} · ${esc(o.e.enc.variante.quant)} · ~${fmtTps(o.e)} tok/s</small></div></div>`;
  const ondeTop = nv.onde.slice().sort((a, b) => a.pos - b.pos).slice(0, 4);
  const naoMuda = nv.fora.slice(0, 4).map(f => nomeHw(f.hw));

  const slides = [
    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'ACABOU DE SAIR' : 'JUST RELEASED'}</span></div>
     <div class="mid">
       <h1>${pt ? `Saiu o <em>${esc(nome)}</em>. Roda na sua placa?` : `<em>${esc(nome)}</em> is out. Does it run on your GPU?`}</h1>
       <p class="sub">${pt ? `Lançado ${quando} no Ollama. Calculamos em ${nv.onde.length + nv.fora.length} computadores populares onde ele já vale a troca →` : `Released ${quando} on Ollama. We checked ${nv.onde.length + nv.fora.length} popular computers to see where it's worth switching →`}</p>
     </div>
     <div class="foot"><span>${pt ? 'Grátis · Offline' : 'Free · Offline'}</span><b>localai4you.vercel.app</b></div>`,

    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'ONDE ELE ENTRA NO TOP 3' : 'WHERE IT MAKES THE TOP 3'}</span></div>
     <div class="mid">
       <h2>${pt ? 'Já está entre os melhores em:' : 'Already among the best on:'}</h2>
       ${ondeTop.map(linhaOnde).join('')}
     </div>
     <div class="foot"><span>${pt ? 'Estimado pela memória de cada placa' : 'Estimated from each card\'s memory'}</span><b>2 / 5</b></div>`,

    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${esc(nomeHw(lider.hw))}</span></div>
     <div class="mid">
       <h2>${pt ? `Na ${esc(nomeHw(lider.hw))} ele fica em ${posTxt(lider.pos)}` : `On the ${esc(nomeHw(lider.hw))} it ranks ${posTxt(lider.pos)}`}</h2>
       ${cardModelo(lider.e, lider.pos)}
       <p class="sub">${pt ? 'Um comando no Terminal e ele baixa e abre a conversa. Sem conta, sem mensalidade.' : 'One Terminal command downloads it and opens the chat. No account, no subscription.'}</p>
     </div>
     <div class="foot"><span>${pt ? 'Comando pronto para copiar' : 'Copy-ready command'}</span><b>3 / 5</b></div>`,

    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'E SE NÃO FOR A SUA?' : 'NOT YOUR CARD?'}</span></div>
     <div class="mid">
       <h2>${pt ? 'Nem todo lançamento muda a sua lista' : 'Not every release changes your list'}</h2>
       <p class="sub">${naoMuda.length ? (pt ? `Em ${esc(naoMuda.join(', '))} ele não entra no Top 3: ou não cabe, ou já existe opção melhor.` : `On ${esc(naoMuda.join(', '))} it doesn't make the Top 3: it either doesn't fit or there's a better option.`) : (pt ? 'Ele entrou no Top 3 em todos os computadores que testamos.' : 'It made the Top 3 on every computer we checked.')}</p>
       <p class="sub">${pt ? 'O Radar atualiza todo dia e marca com 🆕 o que saiu no último mês.' : 'The Radar updates daily and marks last month\'s releases with 🆕.'}</p>
     </div>
     <div class="foot"><span>${pt ? 'Catálogo atualizado todo dia' : 'Catalog updated daily'}</span><b>4 / 5</b></div>`,

    `<div class="top"><div class="brand"><span class="brand-dot"></span>Local AI 4 You</div><span class="tag">${pt ? 'TESTE O SEU PC' : 'TEST YOUR PC'}</span></div>
     <div class="mid">
       <h1>${pt ? 'Vale trocar o <em>seu</em> modelo?' : 'Should <em>you</em> switch models?'}</h1>
       <p class="sub">${pt ? 'Escolha sua placa e veja na hora se esse lançamento roda melhor que o que você usa. Link na bio.' : 'Pick your GPU and see right away if this release beats what you use. Link in bio.'}</p>
       <div class="cmd">${esc(linkBase)}</div>
     </div>
     <div class="foot"><span>${pt ? 'Grátis · Sem cadastro' : 'Free · No signup'}</span><b>5 / 5</b></div>`,
  ];

  const cenasVideo = [
    { html: slides[0], fala: pt ? `Saiu o ${nome}. Será que ele roda na sua placa de vídeo?` : `${nome} just came out. Will it run on your graphics card?` },
    { html: slides[1], fala: pt
      ? `Ele já entra no top 3 em ${nv.onde.length} dos computadores mais comuns, como ${nomeHw(lider.hw)}.`
      : `It already makes the top 3 on ${nv.onde.length} of the most common computers, like the ${nomeHw(lider.hw)}.` },
    { html: slides[2], fala: pt
      ? `Na ${nomeHw(lider.hw)}, roda a cerca de ${fmtTps(lider.e)} tokens por segundo com um único comando do Ollama.`
      : `On the ${nomeHw(lider.hw)}, it runs at about ${fmtTps(lider.e)} tokens per second with a single Ollama command.` },
    { html: slides[4], fala: pt ? 'Quer saber se vale trocar no seu computador? Testa grátis no Local AI 4 You, link na bio.' : 'Want to know if it\'s worth switching on your PC? Check free at Local AI 4 You, link in bio.' },
  ];

  const camp = 'novidade-' + nv.familia.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
  const lista = ondeTop.map(o => `• ${nomeHw(o.hw)}: #${o.pos} (~${fmtTps(o.e)} tok/s)`).join('\n');
  const legendas = pt ? `# Legendas prontas — novidade: ${nome} (PT-BR)

## TikTok / Reels / YouTube Shorts
Saiu o ${nome} (${quando}) 🆕 Roda na sua placa?
${lista}

Veja se vale trocar no SEU computador:
👉 ${linkBase}?utm_source=tiktok&utm_campaign=${camp}
#ialocal #ollama #lancamento #inteligenciaartificial #hardware

## X / Threads
Lançamento: ${nome} já está no Ollama. Onde ele entra no Top 3 (estimado):
${lista}
Lista para qualquer placa: ${linkBase}?utm_source=x&utm_campaign=${camp}
` : `# Ready-to-post captions — new release: ${nome} (EN)

## TikTok / Reels / YouTube Shorts
${nome} just dropped (${quando}) 🆕 Does it run on your GPU?
${lista}

Check if it's worth switching on YOUR PC:
👉 ${linkBase}?utm_source=tiktok&utm_campaign=${camp}
#localai #ollama #localllm #newmodel #gpu

## X / Reddit
New on Ollama: ${nome}. Where it makes the Top 3 (estimated):
${lista}
Any GPU: ${linkBase}?utm_source=x&utm_campaign=${camp}
`;
  return { slides, cenasVideo, legendas, linkBase, slug: camp };
}

function main() {
  const args = Object.fromEntries(process.argv.slice(2).map(a => {
    const [k, v] = a.replace(/^--/, '').split('=');
    return [k, v === undefined ? true : v];
  }));

  if (args.listar) {
    PAUTAS.forEach((p, i) => console.log(`${String(i + 1).padStart(2, '0')}. ${p.id} (${p.tipo})`));
    console.log('    novidade (lançamento do último mês que entra no Top 3 de uma placa popular; automática quando é dos últimos 2 dias)');
    return;
  }

  const D = carregarDados();
  Calc.configurar(D.constantes);

  const hoje = new Date();
  const dataIso = typeof args.data === 'string' ? args.data : hoje.toISOString().slice(0, 10);
  const diaAno = Math.floor((hoje - new Date(hoje.getFullYear(), 0, 0)) / 864e5);
  // novidade: forçada (último mês) ou automática (lançada nos últimos 2 dias e muda o Top 3 de alguma placa popular)
  const nv = args.pauta === 'novidade' ? acharNovidade(D, 30)
    : typeof args.pauta !== 'string' && !args['sem-novidade'] ? acharNovidade(D, 2) : null;
  if (args.pauta === 'novidade' && !nv) throw new Error('Nenhum lançamento do último mês entra no Top 3 das placas populares.');
  const pauta = nv ? { id: 'novidade', tipo: 'novidade' }
    : typeof args.pauta === 'string' ? PAUTAS.find(p => p.id === args.pauta)
    : PAUTAS[diaAno % PAUTAS.length];
  if (!pauta) throw new Error('Pauta não encontrada: ' + args.pauta);

  const idiomas = args.idioma === 'pt' ? ['pt'] : args.idioma === 'en' ? ['en'] : ['pt', 'en'];
  const baseOut = path.join(RAIZ, 'conteudo-social', dataIso);

  for (const lang of idiomas) {
    const pacote = pauta.tipo === 'novidade' ? gerarPacoteNovidade(nv, lang)
      : pauta.tipo === 'duelo'
      ? gerarPacoteDuelo(resolverHardware(D, pauta.a), resolverHardware(D, pauta.b), pauta.id, lang)
      : gerarPacotePlaca(resolverHardware(D, pauta.alvo), lang);
    const id = pacote.slug || pauta.id;
    const destino = path.join(baseOut, lang, id);
    gravarPacote(destino, pacote, lang, id);
    console.log(`Gerado [${lang}] ${id} -> ${path.relative(RAIZ, destino)}`);
  }
}

main();
