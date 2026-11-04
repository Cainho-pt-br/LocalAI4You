'use strict';
/* Interface da calculadora de hardware. Usada em dois lugares: aba "Calculadora" do painel e arquivo HTML autônomo.
   Depende de base.js (h, chip, cmd…) e calc.js (motor). Não faz nenhuma chamada de rede por conta própria: o painel injeta
   `buscarMais` (consulta ao Hugging Face) e `aoTestar` (baixar e medir) quando existem. */
const LI_CALC_UI = (function () {
  const KVS = ['f16', 'q8_0', 'q4_0'];
  const KV_ROTULO = { f16: 'f16 (sem quantizar)', q8_0: 'q8_0 (metade do tamanho)', q4_0: 'q4_0 (um quarto)' };
  const CTXS = [4096, 8192, 16384, 32768, 65536, 131072, 262144];
  const ATIVIDADES = ['chat_pt', 'codigo', 'agente', 'regras', 'raciocinio', 'rapido', 'contexto', 'visao'];
  const ROT = { parrudo: 'Mais capaz que cabe', equilibrado: 'Melhor equilíbrio', leve: 'Leve e rápido' };
  const ROT_CTX = { parrudo: 'Mais capaz nesse contexto', equilibrado: 'Melhor equilíbrio', leve: 'Leve, com muito contexto' };
  const NIVEL_TXT = { confortavel: ['cabe com folga', 'ok'], justo: ['cabe, mas só com contexto menor', 'warn'], nao_cabe: ['não cabe', 'bad'] };
  const LS = 'li-calculadora-v1';

  const guardar = e => { try { localStorage.setItem(LS, JSON.stringify(e)); } catch (x) { /* navegação privada */ } };
  const lembrar = () => { try { return JSON.parse(localStorage.getItem(LS) || '{}') || {}; } catch (x) { return {}; } };
  const r1gb = b => Math.round(b / 1e7) / 100;
  const num = (v, pad) => { const n = Number(String(v).replace(',', '.')); return Number.isFinite(n) && n > 0 ? n : pad; };
  const slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);

  // ---------------------------------------------------------------- hardware
  const cpuPadrao = hw => hw.cpus.find(c => /Ryzen 7000 \(Zen 4\)/.test(c.nome)) || hw.cpus[0];
  const grupoGpu = g => g.fab === 'NVIDIA' ? (/Laptop/.test(g.nome) ? 'NVIDIA GeForce — notebook' : /GeForce/.test(g.nome) ? 'NVIDIA GeForce — desktop' : 'NVIDIA — estação e servidor')
    : g.fab === 'AMD' ? (/Instinct|PRO|Radeon VII/.test(g.nome) ? 'AMD — estação e servidor' : /7900M/.test(g.nome) ? 'AMD — notebook' : 'AMD Radeon') : 'Intel Arc';
  function memDe(E, hw, cpu) {
    const v = num(E.bwCustom, 0);
    if (v) return { bw_min: Math.round(v * 7.8) / 10, bw_max: v, rotulo: 'banda informada por você' };
    if (cpu.bw && !E.memTocada) return { bw_min: cpu.bw[0], bw_max: cpu.bw[1], rotulo: 'banda típica desse processador' };
    const tipo = hw.memorias_ram.find(m => m.id === E.memId) || hw.memorias_ram.find(m => m.id === cpu.mem) || hw.memorias_ram[0];
    const canais = Math.max(1, Math.round(num(E.canais, cpu.canais || 2)));
    const b = Calc.memBw(tipo, canais);
    return { ...b, rotulo: `${tipo.nome} em ${canais} canal(is): ${fmtN(b.teorica, 1)} GB/s teóricos` };
  }
  function perfilDe(E, dados) {
    const hw = dados.hardware;
    if (E.preset) { const m = (dados.maquinas || []).find(x => x.id === E.preset); if (m) return { ...m, reserva_vram_gb: dados.reserva_vram_gb ?? 1.3 }; }
    const sis = hw.sistemas.find(s => s.id === E.sisId) || hw.sistemas[0];
    const cpu = hw.cpus.find(c => c.id === E.cpuId) || cpuPadrao(hw);
    const mem = memDe(E, hw, cpu);
    if (E.modo === 'unificada') {
      const chip = E.chipId === 'custom' ? { nome: 'Memória unificada', bw_gbs: num(E.bw, 200) } : (hw.unificadas.find(c => c.id === E.chipId) || hw.unificadas[0]);
      return Calc.perfilUnificado({ chip, ram_gb: num(E.chipRam, 16), cpu: null, sistema: sis });
    }
    const p = E.modo === 'cpu' ? Calc.perfilCpu({ ram_gb: num(E.ramGb, 8), mem, cpu, sistema: sis })
      : Calc.perfilGpu({ gpu: E.gpuId === 'custom' ? { nome: 'Placa personalizada', vram_gb: num(E.vram, 8), bw_gbs: num(E.bw, 300) } : (hw.gpus.find(x => x.id === E.gpuId) || hw.gpus[0]),
        n: Math.max(1, Math.min(8, Math.round(num(E.nGpus, 1)))), ram_gb: num(E.ramGb, 16), mem, cpu, sistema: sis });
    p.cpu_nome = cpu.nome; p.mem_rotulo = mem.rotulo;
    return p;
  }
  function resumoHw(maq) {
    const orc = Calc.orcamentoBytes(maq, maq.reserva_vram_gb ?? 1.3) / Calc.GIB;
    const par = (t, v) => h('span', {}, t + ' ', h('b', {}, v));
    const bwRam = maq.bw_gbs_min && maq.bw_gbs_max ? `${fmtN(maq.bw_gbs_min, 0)}–${fmtN(maq.bw_gbs_max, 0)} GB/s` : '?';
    return [
      par('Memória para o modelo:', fmtN(orc, 1) + ' GB' + (maq.gpu ? (maq.unificada ? ' (da memória unificada)' : ' de VRAM') : ' de RAM')),
      par(maq.gpu ? 'Banda da GPU:' : 'Banda da RAM:', maq.gpu ? maq.gpu.bw_gbs + ' GB/s' : bwRam),
      maq.gpu && !maq.unificada ? par('RAM do PC:', `${fmtN(maq.ram_gb, 0)} GB a ${bwRam} (só se você permitir)`) : null,
      par('Reservado ao sistema:', fmtN(maq.gpu ? (maq.reserva_vram_gb ?? 1.3) : (maq.reserva_so_gb ?? 1.5), 1) + ' GB'),
      maq.mem_rotulo ? par('Memória:', maq.mem_rotulo) : null];
  }
  /* Resumo de uma frase: até que tamanho cabe e como a velocidade se sente. */
  function resumoGeral(maq, op) {
    const m = Calc.mapaTamanhos(maq, op.kv, maq.reserva_vram_gb ?? 1.3), q4 = m.valores[m.quants.indexOf('Q4_K_M')];
    const t8 = Calc.estimarTps(Math.round(8e9 * Calc.BPW_QUANT.Q4_K_M / 8), maq, false), cl = Calc.classeTps(t8);
    const f = v => (v < 0.5 ? 'nenhum' : '~' + fmtN(v, v < 10 ? 1 : 0) + 'B');
    return h('div', { class: 'info-caixa' }, h('b', {}, 'Em resumo: '),
      `modelos densos em Q4_K_M de até ${f(q4[0])} com 8k de contexto, ${f(q4[1])} com 32k e ${f(q4[2])} com 128k. Um modelo de 8B em Q4 roda a ~${fmtTps(t8)} tok/s (`, h('b', {}, cl[0]), ').',
      maq.gpu && !maq.unificada ? ` Modelos MoE (ex.: 35B com 3B ativos) ocupam memória pelo total mas rodam bem mais rápido.` : '');
  }

  // ---------------------------------------------------------------- cálculo por variante (tabela de quantizações)
  function avaliarVariante(c, v, maq, ctx, kv, reserva) {
    const peso = v.bytes + Math.trunc(v.extra_bytes || 0);
    const b = Calc.bpw(v.bytes, c.params_b);
    const enc = Calc.avaliarEncaixe(peso, c.arch, maq, ctx, kv, reserva);
    const tps = Calc.estimarTps(Calc.pesoAtivo(v.bytes, c.params_b, c.ativos_b), maq, !!c.moe);
    const hib = enc.nivel === 'nao_cabe' ? Calc.hibridoVariante(c, v, maq, ctx, kv, reserva) : null;
    return { v, bpw: b, enc, tps, hib, qual: Calc.faixaQualidade(b), peso };
  }
  /* No Ollama várias tags apontam para o MESMO arquivo (27b = 27b-q4_K_M; 27b-mtp-q4_K_M só liga a especulação por parâmetro).
     Mostra uma linha por arquivo e guarda as outras tags como apelidos. */
  function fundirAliases(vs) {
    const mapa = new Map();
    for (const v of vs) { const k = v.quant + '|' + v.bytes; (mapa.get(k) || mapa.set(k, []).get(k)).push(v); }
    const out = [];
    for (const lista of mapa.values()) {
      const tg = v => String(v.tag || v.quant), pont = v => (tg(v).toLowerCase().includes(String(v.quant).toLowerCase()) ? 0 : 10) + (/mtp/i.test(tg(v)) ? 5 : 0) + tg(v).length / 100;
      const ord = [...lista].sort((a, b) => pont(a) - pont(b));
      out.push({ ...ord[0], tag: tg(ord[0]), aliases: ord.slice(1).map(tg) });
    }
    return out;
  }
  function gruposDeVariantes(c, extras) {
    const grupos = [];
    const nativas = c.variantes.filter(v => !String(v.pull).startsWith('hf.co/'));
    if (nativas.length) grupos.push({ nome: 'Biblioteca do Ollama (oficial)', url: c.origem === 'ollama' && c.familia ? `https://ollama.com/library/${c.familia}/tags` : null, variantes: nativas });
    const porRepo = {};
    for (const v of c.variantes.filter(v => String(v.pull).startsWith('hf.co/'))) {
      const repo = v.pull.slice(6).split(':')[0];
      (porRepo[repo] = porRepo[repo] || []).push(v);
    }
    for (const [repo, vs] of Object.entries(porRepo)) grupos.push({ nome: repo, url: urlHF(repo), variantes: vs });
    const ja = new Set(grupos.flatMap(g => g.variantes.map(v => v.pull.toLowerCase())));
    for (const f of extras || []) {
      const novas = f.variantes.filter(v => !ja.has(v.pull.toLowerCase()));
      if (!novas.length) continue;
      novas.forEach(v => ja.add(v.pull.toLowerCase()));
      const existente = grupos.find(g => g.nome === f.nome);
      if (existente) existente.variantes.push(...novas);
      else grupos.push({ nome: f.nome, url: f.url, autor: f.autor, confianca: f.confianca, variantes: novas });
    }
    for (const g of grupos) g.variantes = fundirAliases(g.variantes).sort((a, b) => a.bytes - b.bytes);
    return grupos;
  }
  function linksDoModelo(c) {
    const L = [];
    if (c.origem === 'ollama' && c.familia) { L.push(['Página no Ollama', `https://ollama.com/library/${c.familia}`]); L.push(['Todas as tags (Ollama)', `https://ollama.com/library/${c.familia}/tags`]); }
    if (c.repo) L.push(['Modelo no Hugging Face', urlHF(c.repo)]);
    if (c.repo_gguf && c.repo_gguf !== c.repo) L.push(['GGUF no Hugging Face', urlHF(c.repo_gguf)]);
    if (c.repo && !/gguf/i.test(c.repo)) L.push(['Todas as quantizações (HF)', `https://huggingface.co/models?other=base_model:quantized:${String(c.repo).split('/').map(encodeURIComponent).join('/')}&sort=downloads`]);
    L.push(['Buscar GGUF no HF', `https://huggingface.co/models?search=${encodeURIComponent(c.nome + ' gguf')}&sort=downloads`]);
    return L;
  }
  function blocoComando(texto) {
    return h('div', { class: 'cmd' }, h('code', {}, texto), h('button', { class: 'btn mini', onclick: () => copiar(texto) }, 'Copiar'));
  }
  function comandosDe(pull, ctx, kv, nome) {
    const mod = `FROM ${pull}\nPARAMETER num_ctx ${ctx}`;
    const nomeCtx = `${slug(nome || pull)}-${fmtCtx(ctx)}`;
    const temPainel = typeof api === 'function' && typeof toast === 'function';
    return h('div', { class: 'empilha' },
      h('div', {}, h('div', { class: 'sub' }, '1. Baixar'), blocoComando('ollama pull ' + pull)),
      h('div', {}, h('div', { class: 'sub' }, `2. Contexto de ${fmtCtx(ctx)} (o padrão do Ollama é bem menor) — crie um modelo com o tamanho certo`),
        temPainel ? h('div', { style: 'margin:6px 0' }, h('button', { class: 'btn mini primario', onclick: async () => {
          try { const r = await api('/api/fixar-ctx', { base: pull, alias: nomeCtx, num_ctx: ctx }); toast(`✅ Criado no Ollama: ${r.alias} (num_ctx=${r.num_ctx})`); } catch (e) { toast(e.message, 8000); }
        } }, `Criar “${nomeCtx}” no Ollama agora (1 clique — exige ${pull} já baixado)`)) : null,
        blocoComando(mod + '\n'), blocoComando(`ollama create ${nomeCtx} -f Modelfile`)),
      h('div', {}, h('div', { class: 'sub' }, `3. Cache de contexto em ${kv} (uma vez só; vale para todos os modelos do servidor)`),
        blocoComando('# Windows (PowerShell)\nsetx OLLAMA_FLASH_ATTENTION 1\nsetx OLLAMA_KV_CACHE_TYPE ' + kv + '\n# depois: feche e reabra o Ollama')));
  }

  // ---------------------------------------------------------------- barra de memória
  function barraMemoria(c, v, maq, ctx, kv, reserva) {
    const orc = Calc.orcamentoBytes(maq, reserva) / Calc.GB;
    const peso = (v.bytes + Math.trunc(v.extra_bytes || 0)) / Calc.GB, cache = Calc.kvBytes(c.arch, ctx, kv) / Calc.GB;
    const resto = (Calc.vramTotal(v.bytes + Math.trunc(v.extra_bytes || 0), c.arch, ctx, kv) / Calc.GB) - peso - cache;
    const tot = peso + cache + resto, base = Math.max(tot, orc);
    const seg = (cls, gb, txt) => h('span', { class: cls, style: `width:${(100 * gb / base).toFixed(2)}%`, title: `${txt}: ${fmtN(gb, 2)} GB` }, 100 * gb / base > 11 ? fmtN(gb, 1) : '');
    return h('div', {},
      h('div', { class: 'ctxbarra', role: 'img', 'aria-label': `peso ${fmtN(peso, 1)} GB, cache ${fmtN(cache, 1)} GB, outros ${fmtN(resto, 1)} GB de ${fmtN(orc, 1)} GB disponíveis` },
        seg('peso', peso, 'Pesos do modelo'), seg('cache', cache, 'Cache de contexto (KV)'), seg('extra', resto, 'Buffers de cálculo')),
      h('div', { class: 'sub', style: 'margin-top:6px' },
        h('span', { style: 'color:#4f6bd9' }, '■ '), `pesos ${fmtN(peso, 1)} GB   `, h('span', { style: 'color:#7b55d1' }, '■ '), `cache ${fmtN(cache, 1)} GB   `, h('span', { style: 'color:#8b8b96' }, '■ '), `buffers ${fmtN(resto, 1)} GB   ·   total `,
        h('b', {}, fmtN(tot, 1) + ' GB'), ` de ${fmtN(orc, 1)} GB disponíveis` + (tot > orc ? ' — não cabe' : '')));
  }

  // ---------------------------------------------------------------- diálogo do modelo: quantizações, cache e comandos
  function dialogoModelo({ c, maq, op, papelId, buscarMais, aoTestar, aoInstalar, aoDuelo, instalados, rotuloMaquina }) {
    const reserva = maq.reserva_vram_gb ?? 1.3;
    const papel = (window.LI_DADOS_PAPEIS || []).find(p => p.id === papelId);
    const instSet = new Set((instalados || []).map(x => String(x).toLowerCase()));
    const S = { ctx: op.ctx || (papel && papel.ctx_alvo) || 16384, kv: op.kv || 'q8_0', sel: null, extras: [], buscando: false, aviso: null };
    if (!CTXS.includes(S.ctx)) CTXS.push(S.ctx), CTXS.sort((a, b) => a - b);
    const corpo = h('div', { class: 'dlg-in' });
    const zona = h('div', { class: 'empilha' });
    const tabelas = h('div', { class: 'empilha' });

    function estaInstalada(pull) {
      const p = String(pull || '').toLowerCase();
      return instSet.has(p) || instSet.has(p.replace(/^hf\.co\//, '')) || instSet.has('hf.co/' + p);
    }

    function desenhar() {
      const grupos = gruposDeVariantes(c, S.extras);
      const todas = grupos.flatMap(g => g.variantes);
      const instaladasDeste = todas.filter(v => estaInstalada(v.pull));
      const idInstalado = instaladasDeste.length ? instaladasDeste[0].pull : null;
      const recom = Calc.escolherVariante(todas.filter(v => v.bytes), maq, c.arch, S.ctx, c.params_b, S.kv, reserva);
      const aval = new Map(todas.map(v => [v.pull, avaliarVariante(c, v, maq, S.ctx, S.kv, reserva)]));
      const cabem = todas.filter(v => aval.get(v.pull).enc.nivel !== 'nao_cabe');
      const maisLeve = todas.length ? todas.reduce((m, v) => (v.bytes < m.bytes ? v : m)) : null;
      const maiorQueCabe = cabem.filter(v => aval.get(v.pull).enc.nivel === 'confortavel').reduce((m, v) => (m === null || v.bytes > m.bytes ? v : m), null);
      if (!S.sel || !aval.has(S.sel)) S.sel = (recom && recom.pull) || (maisLeve && maisLeve.pull) || null;
      const escolhida = todas.find(v => v.pull === S.sel);
      const ctxSel = h('select', { onchange: e => { S.ctx = Number(e.target.value); desenhar(); } }, CTXS.map(x => h('option', { value: x, selected: x === S.ctx }, fmtCtx(x) + ' de contexto')));
      const kvSel = h('select', { onchange: e => { S.kv = e.target.value; desenhar(); } }, KVS.map(x => h('option', { value: x, selected: x === S.kv }, 'cache ' + KV_ROTULO[x])));
      zona.replaceChildren(
        h('div', { class: 'filtros', style: 'margin:0' }, ctxSel, kvSel, h('span', { class: 'sub' }, `para ${rotuloMaquina || maq.nome}`),
          buscarMais ? h('button', { class: 'btn mini', disabled: S.buscando, onclick: async () => { S.buscando = true; desenhar(); try { const r = await buscarMais(); S.extras = r.fontes || []; S.aviso = r.aviso || null; } catch (e) { S.aviso = e.message; } S.buscando = false; desenhar(); } }, S.buscando ? 'Consultando o Hugging Face…' : 'Buscar mais quantizações no Hugging Face') : null),
        idInstalado ? h('div', { class: 'ok-caixa', style: 'padding:8px 12px' }, '✔ Você já tem instalada a quantização ', h('code', {}, idInstalado), '. Para comparar com outra quantização abaixo, clique em ', h('b', {}, '⚔ Duelo vs instalada'), ' ou ', h('b', {}, 'Baixar e testar'), '.') : null,
        S.aviso ? h('div', { class: 'aviso-caixa' }, S.aviso) : null);
      tabelas.replaceChildren(...grupos.map(g => {
        const linhas = g.variantes.map(v => {
          const a = aval.get(v.pull), st = NIVEL_TXT[a.enc.nivel];
          const inst = estaInstalada(v.pull);
          const tag = [inst ? chip('✔ instalada', 'medido', 'Esta quantização exata já está baixada no seu Ollama') : null,
            recom && recom.pull === v.pull ? chip('★ recomendada', 'ok', 'A de maior qualidade que cabe com folga nesse contexto e cache') : null,
            maisLeve && maisLeve.pull === v.pull ? chip('mais leve', 'neutro') : null, maiorQueCabe && maiorQueCabe.pull === v.pull && !(recom && recom.pull === v.pull) ? chip('maior que cabe', 'neutro') : null];
          const botoes = [];
          if (aoTestar && a.enc.nivel !== 'nao_cabe' && !a.hib) {
            if (inst) {
              botoes.push(h('button', { class: 'btn mini', onclick: ev => { ev.stopPropagation(); aoTestar(v.pull); } }, 'Testar instalada'));
            } else {
              botoes.push(h('button', { class: 'btn mini' + (!idInstalado ? ' primario' : ''), onclick: ev => { ev.stopPropagation(); aoTestar(v.pull); } }, 'Baixar e testar'));
              if (aoInstalar) botoes.push(h('button', { class: 'btn mini', title: 'Só baixa, sem medir', onclick: ev => { ev.stopPropagation(); aoInstalar(v.pull); } }, 'Instalar'));
              if (aoDuelo && idInstalado) {
                botoes.push(h('button', { class: 'btn mini primario', title: `Baixa ${v.pull} e roda duelo direto contra ${idInstalado}`, onclick: ev => { ev.stopPropagation(); aoDuelo(idInstalado, v.pull); } }, '⚔ Duelo vs instalada'));
              }
            }
          }
          return h('tr', { class: S.sel === v.pull ? 'destaque' : '', style: 'cursor:pointer', onclick: () => { S.sel = v.pull; desenhar(); } },
            h('td', {}, h('b', {}, v.quant === 'padrão' ? v.tag : v.quant), ' ', tag, g.nome.startsWith('Biblioteca') ? h('div', { class: 'sub' }, v.tag + (v.aliases && v.aliases.length ? ' · também: ' + v.aliases.join(', ') : '')) : null),
            h('td', { class: 'num' }, fmtGB(a.peso)), h('td', { class: 'num' }, fmtN(a.bpw, 1)),
            h('td', {}, a.qual[0]),
            h('td', {}, a.hib ? chip('usa RAM (' + a.hib.pct_gpu + '% na GPU)', 'warn', 'Cabe só dividindo o modelo entre GPU e RAM: bem mais lento') : chip(st[0], st[1])),
            h('td', { class: 'num' }, a.enc.ctx_max ? fmtCtx(a.enc.ctx_max) : '—'),
            h('td', { class: 'num' }, a.hib ? '~' + fmtTps(a.hib.tps_est) : a.enc.nivel === 'nao_cabe' ? '—' : '~' + fmtTps(a.tps)),
            h('td', {}, botoes.length ? h('div', { class: 'linha', style: 'justify-content:flex-end;gap:5px;flex-wrap:nowrap' }, ...botoes) : null));
        });
        return h('div', {}, h('div', { class: 'linha', style: 'margin-bottom:6px' }, h('h4', { class: 'quebra' }, g.nome, g.confianca ? h('span', { class: 'sub' }, ` · ${g.confianca}`) : null),
            g.url ? linkExterno(g.url, 'abrir página') : null),
          h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Quantização', 'Tamanho', 'bits/peso', 'Qualidade', 'Cabe?', 'Contexto máx.', 'tok/s', ''].map((t, i) => h('th', { class: i === 1 || i === 2 || i >= 5 ? 'num' : '' }, t)))), h('tbody', {}, linhas))));
      }));
      const guia = escolhida ? Calc.kvGuia({ arch: c.arch }, escolhida, maq, S.ctx, reserva) : null;
      corpoSel.replaceChildren(escolhida ? [
        h('h3', {}, 'Memória com ', h('code', {}, escolhida.quant), ` e ${fmtCtx(S.ctx)} de contexto `, CHIP_ESTIMADO()),
        barraMemoria(c, escolhida, maq, S.ctx, S.kv, reserva),
        h('h3', {}, 'Cache de contexto (KV): qual usar?'),
        h('div', { class: 'tabela-wrap' }, h('table', { class: 'kvtab' }, h('thead', {}, h('tr', {}, ['Cache', 'Ocupa', 'Total na memória', 'Cabe?', 'Contexto máx.'].map((t, i) => h('th', { class: i ? 'num' : '' }, t)))),
          h('tbody', {}, guia.tabela.map(l => h('tr', { class: l.tipo === guia.recomendado ? 'destaque' : '' },
            h('td', { class: l.tipo === guia.recomendado ? 'rec' : '' }, KV_ROTULO[l.tipo], l.tipo === guia.recomendado ? ' ← recomendado' : ''), h('td', { class: 'num' }, fmtN(l.kv_gb, 2) + ' GB'),
            h('td', { class: 'num' }, fmtN(l.total_gb, 1) + ' GB'), h('td', { class: 'num' }, l.confortavel ? 'com folga' : l.cabe ? 'justo' : 'não'), h('td', { class: 'num' }, l.ctx_max ? fmtCtx(l.ctx_max) : '—')))))),
        h('div', { class: guia.recomendado ? 'info-caixa' : 'aviso-caixa' }, guia.porque),
        h('h3', {}, 'Como usar essa quantização'), comandosDe(escolhida.pull, S.ctx, guia.recomendado || S.kv, c.nome)] : h('div', { class: 'vazio' }, 'Nenhuma quantização conhecida.'));
    }
    const corpoSel = h('div', { class: 'empilha' });
    const links = linksDoModelo(c).map(([t, u]) => linkExterno(u, t)).filter(Boolean);
    corpo.replaceChildren(
      h('div', {}, h('h2', { class: 'quebra' }, c.nome), h('div', { class: 'sub' }, `${c.params_b}B${c.ativos_b ? ' · MoE com ' + c.ativos_b + 'B ativos' : ''} · contexto nativo ${fmtCtx(c.ctx_max)}${c.licenca ? ' · licença ' + c.licenca : ''}`),
        c.descricao ? h('div', { class: 'sub', style: 'margin-top:4px' }, c.descricao) : null),
      h('div', { class: 'chips' }, ...(c.caps || []).filter(x => x !== 'completion' && x !== 'cloud').map(x => chip(x)), c.confianca === 'comunidade' ? chip('comunidade', 'warn', 'Ajuste de terceiros: pode ter perdido qualidade') : null),
      links.length ? h('div', { class: 'filtros', style: 'margin:0' }, ...links) : null,
      zona, tabelas, corpoSel,
      h('div', { class: 'info-caixa' }, 'Tudo aqui é ', h('b', {}, 'ESTIMADO'), ': tamanho real dos arquivos + conta de memória e de banda. A velocidade em CPU vale ±2×. Clique numa linha para ver os comandos daquela quantização.'),
      h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar')));
    abrirDialogo(corpo);
    const d = document.getElementById('dlg'); if (d) d.classList.add('largo');
    desenhar();
    if (buscarMais) { S.buscando = true; desenhar(); buscarMais().then(r => { S.extras = r.fontes || []; S.aviso = r.aviso || null; }).catch(e => { S.aviso = 'Não consegui consultar o Hugging Face: ' + e.message; }).finally(() => { S.buscando = false; desenhar(); }); }
  }

  // ---------------------------------------------------------------- cartões de resultado
  function chipsDoModelo(c) {
    return [c.moe ? chip(`MoE · ${c.ativos_b || '?'}B ativos`, 'neutro', 'Só uma parte dos parâmetros trabalha a cada token: ocupa memória como o total, roda mais rápido') : null,
      (c.caps || []).includes('vision') ? chip('visão', 'neutro') : null, (c.caps || []).includes('tools') ? chip('ferramentas', 'neutro') : null,
      (c.caps || []).includes('thinking') ? chip('raciocínio', 'neutro') : null, c.confianca === 'comunidade' ? chip('comunidade', 'warn') : null];
  }
  function blocoEscolha(rotulo, e, papel, maq, op, dados, ctxRotulo) {
    if (!e) return h('div', { class: 'escolha vazia' }, h('div', { class: 'rotulo' }, rotulo), 'Nada que caiba aqui com esse hardware e contexto.');
    const c = e.c, v = e.enc.variante, med = c.medido && (c.medido.papeis[papel.id === 'contexto' ? 'chat_pt' : papel.id]);
    const peso = v.bytes + Math.trunc(v.extra_bytes || 0), reserva = maq.reserva_vram_gb ?? 1.3, kv = op.kv;
    const ctxEf = e.offload ? e.ctx : Math.min(e.ctx, e.enc.encaixe.ctx_max || e.ctx);   // o contexto que ele de fato alcança
    const usado = e.offload ? e.enc.encaixe.usado_ctx_alvo_gb : r1gb(Calc.vramTotal(peso, c.arch, ctxEf, kv));
    const L = linksDoModelo(c), linkOl = L.find(l => /Ollama/.test(l[0])), linkHf = L.find(l => /Hugging Face/.test(l[0]));
    return h('div', { class: 'escolha' },
      h('div', { class: 'rotulo' }, rotulo),
      h('div', {}, h('div', { class: 'nome' }, c.nome), h('div', { class: 'sub' }, `${c.params_b}B${c.ativos_b ? ' (' + c.ativos_b + 'B ativos)' : ''}${c.dias != null ? ' · ' + fmtIdade(c.dias) : ''}`)),
      h('div', { class: 'chips' }, ...chipsDoModelo(c)),
      h('div', { class: 'grande' }, '~' + fmtTps(e.enc.tps_est), h('small', {}, ' tok/s '), CHIP_ESTIMADO()),
      h('div', { class: 'chips' }, chip(Calc.classeTps(e.enc.tps_est)[0], Calc.classeTps(e.enc.tps_est)[1], 'Leitura humana confortável é ~5–8 tok/s; abaixo de 6 só serve em lote')),
      h('div', { class: 'metricas' }, h('span', {}, h('b', {}, v.quant), ' · ', fmtGB(peso)), h('span', {}, 'qualidade ', h('b', {}, e.enc.qualidade)),
        e.offload ? h('span', {}, '⚠ ', h('b', {}, e.enc.pct_gpu + '% na GPU'), ` · ${fmtN(e.enc.ram_usada_gb, 1)} GB na RAM (bem mais lento)`)
          : h('span', {}, 'contexto até ', h('b', {}, fmtCtx(e.enc.encaixe.ctx_max))),
        h('span', {}, 'usa ', h('b', {}, fmtN(usado, 1) + ' GB'), ` com ${fmtCtx(ctxEf)}`)),
      !e.offload && e.enc.encaixe.nivel === 'justo' ? h('div', { class: 'aviso-caixa', style: 'padding:6px 10px;font-size:.8rem' }, `Apertado: não alcança ${fmtCtx(e.ctx)} de contexto com folga.`) : null,
      med ? h('div', { class: 'metricas' }, CHIP_MEDIDO(), h('span', {}, 'nota ', h('b', {}, fmtN(med.nota, 0)), med.ic ? ` ± ${Math.round((med.ic[1] - med.ic[0]) / 2)}` : '', ` (${c.medido.modelo})`)) : null,
      h('div', { class: 'rodape' }, h('button', { class: 'btn mini primario', onclick: () => dialogoModelo({ c, maq, op, papelId: papel.id, buscarMais: dados._buscarMais ? () => dados._buscarMais(c) : null, aoTestar: (dados._aoTestar && maq.local) ? pull => dados._aoTestar(c, papel.id, pull) : null, aoDuelo: (dados._aoDuelo && maq.local) ? (a, b) => dados._aoDuelo(a, b, papel.id) : null, instalados: dados._instalados ? dados._instalados() : [], rotuloMaquina: maq.nome }) }, 'Quantizações e comandos'),
        ...[linkOl, linkHf].filter(Boolean).map(([t, u]) => linkExterno(u, /Ollama/.test(t) ? 'Ollama' : 'Hugging Face'))));
  }
  function cartaoAtividade(papel, r, maq, op, dados) {
    const rot = papel.id === 'contexto' ? ROT_CTX : ROT;
    const vazio = !r.parrudo && !r.equilibrado && !r.leve;
    return h('div', { class: 'cartao atividade' },
      h('div', { class: 'atividade-topo' }, h('div', { class: 'papel-icone' }, papel.icone), h('div', { class: 'grow' }, h('h3', {}, papel.rotulo), h('div', { class: 'sub' }, papel.descricao),
        papel.id === 'contexto' ? h('div', { class: 'sub' }, `Meta de contexto: ${fmtCtx(op.ctx || papel.ctx_alvo)}. Modelo de atenção linear ou com janela deslizante guarda pouco cache: é o que mais rende aqui.`) : null)),
      vazio ? h('div', { class: 'aviso-caixa' }, 'Nenhum modelo do radar cabe nessa atividade com esse hardware' + (op.ctx ? ` e ${fmtCtx(op.ctx)} de contexto` : '') + '. Tente um contexto menor' + (maq.gpu && !maq.unificada && !op.offload ? ' ou permita usar a RAM do PC.' : '.'))
        : h('div', { class: 'escolhas' }, blocoEscolha(rot.parrudo, r.parrudo, papel, maq, op, dados), blocoEscolha(rot.equilibrado, r.equilibrado, papel, maq, op, dados), blocoEscolha(rot.leve, r.leve, papel, maq, op, dados)),
      papel.nota ? h('div', { class: 'sub', style: 'margin-top:12px' }, 'ℹ ' + papel.nota) : null);
  }

  // ---------------------------------------------------------------- guia, "cabe um modelo qualquer?" e mapa
  function cartaoGuia(maq, op, dados) {
    const gb = (p, b) => fmtN(p * 1e9 * b / 8 / 1e9, 1);
    const linhas = [['Q3_K_M', 'boa, perda pequena — só vale se o modelo maior em Q3 ainda for melhor que o menor em Q4'], ['Q4_K_M', 'ótima: o padrão; perda pequena com 1/4 do tamanho'], ['Q5_K_M', 'excelente: use quando sobrar memória'],
      ['Q6_K', 'quase sem perda'], ['Q8_0', 'praticamente igual ao original (e o dobro do Q4)']];
    return h('div', { class: 'grade g2' },
      h('div', { class: 'cartao' }, h('h3', {}, '1. Quantização do modelo (os pesos)'),
        h('p', { class: 'sub', style: 'margin-top:6px' }, 'Comprime os números do modelo. Menos bits = arquivo menor e mais rápido, com um pouco menos de qualidade. Tamanho aproximado:'),
        h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Formato', 'bits/peso', '8B', '14B', '32B', 'Qualidade'].map((t, i) => h('th', { class: i > 0 && i < 5 ? 'num' : '' }, t)))),
          h('tbody', {}, linhas.map(([q, obs]) => h('tr', {}, h('td', {}, h('b', {}, q)), h('td', { class: 'num' }, Calc.BPW_QUANT[q]), h('td', { class: 'num' }, gb(8, Calc.BPW_QUANT[q])), h('td', { class: 'num' }, gb(14, Calc.BPW_QUANT[q])), h('td', { class: 'num' }, gb(32, Calc.BPW_QUANT[q])), h('td', { class: 'sub' }, obs)))))),
        h('ul', { class: 'sub', style: 'padding-left:18px;margin:10px 0 0' }, h('li', {}, 'Comece em ', h('b', {}, 'Q4_K_M'), '; suba para Q5/Q6 se sobrar memória livre depois do contexto.'),
          h('li', {}, 'Abaixo de ~3 bits por peso a qualidade cai de forma visível: prefira um modelo menor em Q4.'),
          h('li', {}, 'Formatos “I” (IQ3_S, IQ4_XS) e “UD-” (unsloth) guardam mais qualidade por tamanho, mas são um pouco mais lentos em CPU.'))),
      h('div', { class: 'cartao' }, h('h3', {}, '2. Quantização do cache de contexto (KV)'),
        h('p', { class: 'sub', style: 'margin-top:6px' }, 'O cache guarda a conversa já lida e cresce com o tamanho do contexto. Em modelos de atenção cheia, 32k de contexto pode custar vários GB — além do peso do modelo.'),
        h('ul', { class: 'sub', style: 'padding-left:18px;margin:6px 0' }, h('li', {}, h('b', {}, 'f16'), ': sem perda; ocupa o dobro do q8_0.'), h('li', {}, h('b', {}, 'q8_0'), ': metade do tamanho, perda desprezível na prática. É o ponto de equilíbrio.'),
          h('li', {}, h('b', {}, 'q4_0'), ': um quarto do tamanho, mas a perda em contextos longos é maior. Só se a memória apertar.'),
          h('li', {}, 'Modelos de atenção linear/janela (Qwen 3.5/3.8, Gemma 4, gpt-oss) têm cache pequeno: quantizar quase não economiza.')),
        h('div', { class: 'info-caixa' }, 'No Ollama o cache quantizado exige Flash Attention ligada e vale para o servidor inteiro. Onde ligar:'),
        h('div', { class: 'empilha', style: 'margin-top:10px' },
          h('div', {}, h('div', { class: 'sub' }, 'Ollama no Windows (PowerShell) — depois reinicie o Ollama'), blocoComando('setx OLLAMA_FLASH_ATTENTION 1\nsetx OLLAMA_KV_CACHE_TYPE q8_0')),
          h('div', {}, h('div', { class: 'sub' }, 'Ollama no Linux (systemd)'), blocoComando('sudo systemctl edit ollama\n# acrescente em [Service]:\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\nEnvironment="OLLAMA_KV_CACHE_TYPE=q8_0"')),
          h('div', {}, h('div', { class: 'sub' }, 'Ollama no macOS'), blocoComando('launchctl setenv OLLAMA_FLASH_ATTENTION 1\nlaunchctl setenv OLLAMA_KV_CACHE_TYPE q8_0')),
          h('div', {}, h('div', { class: 'sub' }, 'llama.cpp (versões antigas: só “-fa”)'), blocoComando('llama-server -m modelo.gguf -c 32768 -ngl 99 -fa on -ctk q8_0 -ctv q8_0')),
          h('div', { class: 'sub' }, 'LM Studio: nas configurações do modelo, ligue “Flash Attention” e escolha o tipo de quantização do cache K e V.'))));
  }
  const GPUS_REF = ['rtx-4060', 'rtx-3060-12', 'rtx-5060-ti-16', 'rtx-4090', 'rtx-5090'];
  function cartaoUpgrade(maq, op, dados, E) {
    if (maq.unificada) return h('div', { class: 'vazio' }, 'Memória unificada não troca de placa: compare escolhendo outro chip acima.');
    const hw = dados.hardware, sis = { reserva_vram_gb: 1.3, reserva_ram_gb: maq.reserva_so_gb ?? 4 };
    const cpuRef = { simd: maq.simd }, memRef = { bw_min: maq.bw_gbs_min || 40, bw_max: maq.bw_gbs_max || 50 };
    const linhas = [];
    const pic = (m, id) => { const r = Calc.escolher(dados, m, dados.papeis.find(p => p.id === id), op).parrudo; return r ? h('td', {}, h('b', {}, r.c.nome), h('div', { class: 'sub' }, `${r.enc.variante.quant} · ~${fmtTps(r.enc.tps_est)} tok/s`)) : h('td', { class: 'sub' }, '—'); };
    const linha = (rot, m, atual) => h('tr', { class: atual ? 'destaque' : '' }, h('td', {}, h('b', {}, rot), atual ? chip('o seu', 'ok') : null, h('div', { class: 'sub' }, m.gpu ? `${fmtN(m.gpu.vram_gb, 0)} GB · ${m.gpu.bw_gbs} GB/s` : `${fmtN(m.ram_gb, 0)} GB de RAM`)),
      pic(m, 'chat_pt'), pic(m, 'codigo'), pic(m, 'contexto'));
    linhas.push(linha(maq.gpu ? maq.nome : (maq.nome || 'Seu computador (sem GPU)'), maq, true));
    for (const id of GPUS_REF) {
      const g = hw.gpus.find(x => x.id === id);
      if (!g || (maq.gpu && maq.gpu.nome === g.nome)) continue;
      linhas.push(linha(g.nome, Calc.perfilGpu({ gpu: g, n: 1, ram_gb: maq.ram_gb || 16, mem: memRef, cpu: cpuRef, sistema: sis }), false));
    }
    return h('div', { class: 'tabela-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Hardware', 'Conversa: o mais capaz', 'Código: o mais capaz', 'Muito contexto: o mais capaz'].map(t => h('th', {}, t)))), h('tbody', {}, linhas)),
      h('div', { class: 'sub', style: 'padding:10px 14px' }, 'Mesma RAM, processador e opções acima; só a placa muda. ESTIMADO. Placas de referência: popular de entrada, 12 GB, 16 GB, 24 GB e 32 GB.'));
  }
  function cartaoModeloLivre(maq) {
    const E = { params: '14', ativos: '', quant: 'Q4_K_M', ctx: 16384, kv: 'q8_0' };
    const saida = h('div', { class: 'empilha' });
    const campo = (r, el) => h('label', { class: 'campo' }, r, el);
    function calcular() {
      const p = num(E.params, 0), a = E.ativos ? num(E.ativos, 0) : null;
      if (!p) { saida.replaceChildren(h('div', { class: 'sub' }, 'Informe o número de parâmetros (em bilhões).')); return; }
      const b = Calc.BPW_QUANT[E.quant], r = Calc.modeloLivre({ params_b: p, ativos_b: a, bpw: b, ctx: E.ctx, kv: E.kv }, maq, maq.reserva_vram_gb ?? 1.3);
      saida.replaceChildren(
        h('div', { class: r.confortavel ? 'ok-caixa' : r.cabe ? 'aviso-caixa' : 'aviso-caixa' }, h('b', {}, r.confortavel ? 'Cabe com folga.' : r.cabe ? 'Cabe, mas apertado.' : 'Não cabe.'),
          ` Pesos ${fmtN(r.peso_gb, 1)} GB + cache ${fmtN(r.kv_gb, 1)} GB + buffers = ${fmtN(r.total_gb, 1)} GB, para ${fmtN(r.orcamento_gb, 1)} GB disponíveis (folga ${fmtN(r.folga_gb, 1)} GB).`),
        h('div', { class: 'metricas' }, h('span', {}, 'contexto máximo ', h('b', {}, r.ctx_max ? fmtCtx(r.ctx_max) : 'menos de 2k')), r.tps_est ? h('span', {}, '~', h('b', {}, fmtTps(r.tps_est)), ' tok/s (estimado)') : null,
          h('span', { class: 'sub' }, 'cálculo com uma arquitetura típica: o cache real varia por modelo (±30%)')));
    }
    const ctlQ = h('select', { onchange: e => { E.quant = e.target.value; calcular(); } }, Object.keys(Calc.BPW_QUANT).map(q => h('option', { value: q, selected: q === E.quant }, `${q} (~${Calc.BPW_QUANT[q]} bits)`)));
    const ctlC = h('select', { onchange: e => { E.ctx = Number(e.target.value); calcular(); } }, CTXS.map(x => h('option', { value: x, selected: x === E.ctx }, fmtCtx(x))));
    const ctlK = h('select', { onchange: e => { E.kv = e.target.value; calcular(); } }, KVS.map(x => h('option', { value: x, selected: x === E.kv }, KV_ROTULO[x])));
    const ip = h('input', { type: 'text', value: E.params, inputmode: 'decimal', oninput: e => { E.params = e.target.value; calcular(); } });
    const ia = h('input', { type: 'text', value: E.ativos, placeholder: 'só se for MoE', inputmode: 'decimal', oninput: e => { E.ativos = e.target.value; calcular(); } });
    calcular();
    return h('div', { class: 'cartao' }, h('div', { class: 'campos', style: 'margin-top:0' }, campo('Parâmetros (bilhões)', ip), campo('Ativos por token (MoE, opcional)', ia), campo('Quantização', ctlQ), campo('Contexto', ctlC), campo('Cache de contexto', ctlK)), h('div', { style: 'margin-top:14px' }, saida));
  }
  function cartaoMapa(maq, op) {
    const m = Calc.mapaTamanhos(maq, op.kv, maq.reserva_vram_gb ?? 1.3);
    return h('div', { class: 'cartao' },
      h('div', { class: 'tabela-wrap' }, h('table', { class: 'mapa' }, h('thead', {}, h('tr', {}, h('th', {}, 'Maior modelo denso que cabe com folga'), ...m.ctxs.map(c => h('th', {}, fmtCtx(c) + ' de contexto')))),
        h('tbody', {}, m.quants.map((q, i) => h('tr', {}, h('td', {}, h('b', {}, q)), ...m.valores[i].map(v => h('td', { class: 'num' }, v < 0.5 ? '—' : '~' + fmtN(v, v < 10 ? 1 : 0) + 'B'))))))),
      h('div', { class: 'sub', style: 'margin-top:10px' }, `Cache em ${op.kv}. Modelos MoE ocupam memória pelo total de parâmetros (ex.: 35B-A3B pesa como 35B). Arquitetura típica de modelo denso; modelos de atenção linear/janela cabem com mais contexto.`));
  }

  // ---------------------------------------------------------------- montagem
  function montar(el, dados, opts = {}) {
    Calc.configurar(dados.constantes);
    window.LI_DADOS_PAPEIS = dados.papeis || [];
    const hw = dados.hardware;
    const salvo = lembrar();
    const cpu0 = cpuPadrao(hw);
    const E = { modo: 'gpu', gpuId: 'rtx-4070', gpuFiltro: '', nGpus: 1, vram: 12, bw: 500, ramGb: 32, cpuId: cpu0.id, memId: cpu0.mem, canais: cpu0.canais, memTocada: false, bwCustom: '', sisId: 'windows', chipId: 'm4-pro', chipRam: 24,
      preset: '', ctx: 0, kv: 'q8_0', comunidade: false, antigos: false, offload: false, ...salvo };
    if (opts.solo) { try { const m = /[#&]c=([^&]+)/.exec(location.hash); if (m) Object.assign(E, JSON.parse(decodeURIComponent(escape(atob(m[1])))), { preset: '' }); } catch (x) { /* link inválido: segue com o padrão */ } }
    if (!salvo.modo && !E.preset && dados.esta_maquina && !/[#&]c=/.test(opts.solo ? location.hash : '')) E.preset = dados.esta_maquina;
    if (E.preset && !(dados.maquinas || []).some(m => m.id === E.preset)) E.preset = '';
    if (!hw.cpus.some(c => c.id === E.cpuId)) { E.cpuId = cpu0.id; E.memId = cpu0.mem; E.canais = cpu0.canais; E.memTocada = false; }
    if (!hw.memorias_ram.some(m => m.id === E.memId)) E.memId = cpu0.mem;
    const zonaHw = h('div'), zonaRes = h('div', { class: 'empilha' }), zonaResumo = h('div'), zonaGeral = h('div'), zonaUpgrade = h('div');
    const campo = (r, el) => h('label', { class: 'campo' }, r, el);
    const sel = (lista, valor, aoMudar, rot) => h('select', { onchange: ev => { aoMudar(ev.target.value); } }, lista.map(x => h('option', { value: x.id, selected: x.id === valor }, rot ? rot(x) : x.nome)));
    const entrada = (valor, aoMudar, ph) => h('input', { type: 'text', value: valor, placeholder: ph, inputmode: 'decimal', oninput: ev => aoMudar(ev.target.value) });
    const mudou = (estrutura) => { guardar(E); if (estrutura) desenharHw(); desenharResumo(); desenharRes(); };

    // --- campos reutilizáveis
    function campoGpu() {
      const caixa = h('select', { onchange: ev => { E.gpuId = ev.target.value; mudou(true); } });
      const preencher = () => {
        const f = E.gpuFiltro.trim().toLowerCase();
        const grupos = new Map();
        for (const g of hw.gpus) if (g.id === E.gpuId || !f || (g.nome + ' ' + g.fab + ' ' + g.vram_gb + 'gb').toLowerCase().includes(f)) { const k = grupoGpu(g); (grupos.get(k) || grupos.set(k, []).get(k)).push(g); }
        caixa.replaceChildren(...[...grupos].map(([k, lst]) => h('optgroup', { label: k }, lst.map(g => h('option', { value: g.id, selected: g.id === E.gpuId }, `${g.nome} — ${g.vram_gb} GB · ${g.bw_gbs} GB/s`)))),
          h('option', { value: 'custom', selected: E.gpuId === 'custom' }, 'Outra (informar VRAM e banda)'));
      };
      preencher();
      const filtro = h('input', { type: 'search', value: E.gpuFiltro, placeholder: 'Filtrar: 4070, laptop, 16gb, radeon…', oninput: ev => { E.gpuFiltro = ev.target.value; preencher(); } });
      return [h('label', { class: 'campo', style: 'grid-column: span 2' }, 'Placa de vídeo (' + hw.gpus.length + ' modelos)', filtro, caixa),
        ...(E.gpuId === 'custom' ? [campo('VRAM (GB)', entrada(E.vram, v => { E.vram = v; mudou(false); })), campo('Banda de memória (GB/s)', entrada(E.bw, v => { E.bw = v; mudou(false); }, 'ex.: 448'))] : []),
        campo('Quantidade de placas', h('select', { onchange: ev => { E.nGpus = Number(ev.target.value); mudou(false); } }, [1, 2, 3, 4, 6, 8].map(n => h('option', { value: n, selected: n === E.nGpus }, n))))];
    }
    function campoRam() {
      const lista = hw.ram_opcoes_gb || [4, 8, 16, 32, 64, 128];
      const atual = Number(E.ramGb);
      const ops = lista.includes(atual) ? lista : [...lista, atual].sort((a, b) => a - b);
      return campo('Memória RAM do computador', h('select', { onchange: ev => { E.ramGb = Number(ev.target.value); mudou(false); } }, ops.map(n => h('option', { value: n, selected: n === atual }, n + ' GB'))));
    }
    function campoCpu() {
      const grupos = new Map();
      for (const c of hw.cpus) (grupos.get(c.grupo) || grupos.set(c.grupo, []).get(c.grupo)).push(c);
      return campo('Processador (' + hw.cpus.length + ' opções)', h('select', { onchange: ev => { const c = hw.cpus.find(x => x.id === ev.target.value); E.cpuId = c.id; E.memId = c.mem; E.canais = c.canais; E.memTocada = false; E.bwCustom = ''; mudou(true); } },
        [...grupos].map(([g, lst]) => h('optgroup', { label: g }, lst.map(c => h('option', { value: c.id, selected: c.id === E.cpuId }, c.nome + (c.nucleos ? ` · ${c.nucleos}` : '')))))));
    }
    function camposMemoria() {
      const cpu = hw.cpus.find(c => c.id === E.cpuId) || cpu0, gens = new Map();
      for (const m of hw.memorias_ram) (gens.get(m.gen) || gens.set(m.gen, []).get(m.gen)).push(m);
      const fixa = cpu.bw && !E.memTocada;
      return [campo('Tipo de memória RAM' + (fixa ? ' (padrão do processador)' : ''), h('select', { onchange: ev => { E.memId = ev.target.value; E.memTocada = true; mudou(true); } },
          [...gens].map(([g, lst]) => h('optgroup', { label: g }, lst.map(m => h('option', { value: m.id, selected: m.id === E.memId }, m.nome + ' (' + m.mts + ' MT/s)')))))),
        campo('Canais de memória (pentes em paralelo)', h('select', { onchange: ev => { E.canais = Number(ev.target.value); E.memTocada = true; mudou(true); } }, (hw.canais_opcoes || [1, 2, 4]).map(n => h('option', { value: n, selected: n === Number(E.canais) }, n + (n === 1 ? ' canal' : ' canais'))))),
        campo('Banda da RAM em GB/s (opcional: sobrescreve)', entrada(E.bwCustom, v => { E.bwCustom = v; mudou(false); }, 'ex.: 51 — se você mediu'))];
    }
    const campoSis = () => campo('Sistema operacional', sel(hw.sistemas, E.sisId, v => { E.sisId = v; mudou(false); }));

    function desenharHw() {
      const camposPrincipais = [];
      const camposAvancados = [];
      if (E.preset) {
        const m = dados.maquinas.find(x => x.id === E.preset);
        camposPrincipais.push(h('div', { class: 'info-caixa', style: 'grid-column:1/-1' }, `Usando o perfil da máquina “${m ? m.nome : E.preset}” (${m ? m.cpu : ''}). `, h('button', { class: 'btn mini', onclick: () => { E.preset = ''; mudou(true); } }, 'Informar o hardware manualmente')));
      } else if (E.modo === 'gpu') {
        camposPrincipais.push(...campoGpu(), campoRam());
        camposAvancados.push(campoCpu(), ...camposMemoria(), campoSis());
      } else if (E.modo === 'unificada') {
        camposPrincipais.push(campo('Chip', h('select', { onchange: ev => { E.chipId = ev.target.value; const c = hw.unificadas.find(x => x.id === E.chipId); if (c && !c.ram_opcoes.includes(Number(E.chipRam))) E.chipRam = c.ram_opcoes[0]; mudou(true); } },
          ['Apple', 'NVIDIA', 'AMD'].map(f => h('optgroup', { label: f }, hw.unificadas.filter(c => c.fab === f).map(c => h('option', { value: c.id, selected: c.id === E.chipId }, `${c.nome} — ${c.bw_gbs} GB/s`)))), h('option', { value: 'custom', selected: E.chipId === 'custom' }, 'Outro (informar banda)'))));
        const chip = hw.unificadas.find(x => x.id === E.chipId);
        camposPrincipais.push(campo('Memória unificada (GB)', chip ? h('select', { onchange: ev => { E.chipRam = Number(ev.target.value); mudou(false); } }, chip.ram_opcoes.map(n => h('option', { value: n, selected: n === Number(E.chipRam) }, n + ' GB'))) : entrada(E.chipRam, v => { E.chipRam = v; mudou(false); })));
        if (E.chipId === 'custom') camposPrincipais.push(campo('Banda de memória (GB/s)', entrada(E.bw, v => { E.bw = v; mudou(false); }, 'ex.: 273')));
        camposPrincipais.push(h('div', { class: 'sub', style: 'grid-column:1/-1' }, 'A GPU enxerga só uma parte da memória unificada (no macOS ≈ 2/3 até 36 GB e 3/4 acima).'));
      } else {
        camposPrincipais.push(campoCpu(), campoRam());
        camposAvancados.push(...camposMemoria(), campoSis());
      }
      const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Tipo de hardware' }, [['gpu', 'Placa de vídeo'], ['unificada', 'Mac / memória unificada'], ['cpu', 'Só processador']].map(([id, t]) =>
        h('button', { 'aria-pressed': String(E.modo === id), onclick: () => { E.modo = id; E.preset = ''; mudou(true); } }, t)));
      const presets = (dados.maquinas || []).length ? campo('Ou escolha uma máquina conhecida', h('select', { onchange: ev => { E.preset = ev.target.value; const m = (dados.maquinas || []).find(x => x.id === E.preset); if (m) E.modo = m.gpu ? 'gpu' : 'cpu'; mudou(true); } }, h('option', { value: '' }, 'Personalizado (informar manualmente)'), dados.maquinas.map(m => h('option', { value: m.id, selected: m.id === E.preset }, m.nome + (m.gpu ? ` — ${m.gpu.nome}` : ' — só CPU'))))) : null;
      zonaHw.replaceChildren(h('div', { class: 'cartao calc-card-hw' },
        h('div', { class: 'linha', style: 'flex-wrap:wrap;gap:8px' }, h('h3', {}, h('span', { class: 'passo-n' }, '1'), 'Seu hardware'), seg),
        h('div', { class: 'campos' }, ...camposPrincipais, presets),
        camposAvancados.length ? h('details', { class: 'dica-clean', style: 'margin-top:10px' },
          h('summary', {}, '⚙ Detalhes opcionais do PC (processador, DDR4/DDR5, canais de RAM…)'),
          h('div', { class: 'campos', style: 'margin-top:10px' }, ...camposAvancados)) : null,
        zonaResumo));
    }
    function desenharResumo() { zonaResumo.className = 'resumo-hw'; zonaResumo.replaceChildren(...resumoHw(perfilDe(E, dados))); }
    const CTX_HUMANO = {
      0: '✨ Automático por atividade (recomendado — você não precisa configurar)',
      4096: '💬 Conversas curtas e rápidas (4k — ~3 mil palavras)',
      8192: '📝 Conversas e textos do dia a dia (8k — ~6 mil palavras)',
      16384: '📄 Documentos e scripts médios (16k — ~12 mil palavras)',
      32768: '💻 Projetos de código e PDFs longos (32k — ~25 mil palavras)',
      65536: '📚 Múltiplos arquivos ou relatórios extensos (64k — ~50 mil palavras)',
      131072: '📖 Livros inteiros ou repositórios grandes (128k — ~100 mil palavras)',
      262144: '🏛️ Arquivos gigantes / base completa (256k — ~200 mil palavras)',
    };
    const opcoes = () => h('div', { class: 'cartao calc-card-uso' },
      h('h3', {}, h('span', { class: 'passo-n' }, '2'), 'Como você vai usar'),
      h('p', { class: 'sub', style: 'font-size:.81rem;margin:4px 0 10px' },
        'Não sabe o que é KV cache ou contexto? Deixe no ', h('b', {}, 'Automático'), ' — nós já configuramos o equilíbrio ideal para você.'),
      h('div', { class: 'empilha', style: 'gap:10px' },
        campo('Tamanho das conversas / arquivos que vai enviar', h('select', { onchange: ev => { E.ctx = Number(ev.target.value); mudou(false); } },
          h('option', { value: 0, selected: !E.ctx }, CTX_HUMANO[0]),
          CTXS.map(x => h('option', { value: x, selected: x === E.ctx }, CTX_HUMANO[x] || (fmtCtx(x) + ' de contexto'))))),
        h('div', { class: 'calc-auto-pill' },
          h('span', {}, '✔ ', h('b', {}, 'Modo Inteligente Ativo: '), `Memória da conversa otimizada (${E.kv === 'q8_0' ? 'q8_0 equilibrado' : E.kv}) · Catálogo online Ollama + Hugging Face`)),
        h('details', { class: 'dica-clean', style: 'margin-top:2px' },
          h('summary', {}, '⚙ Ajustes técnicos avançados (KV cache, usar RAM do PC…)'),
          h('div', { class: 'empilha', style: 'gap:8px;margin-top:8px' },
            campo('Compressão da memória da conversa (KV Cache)', h('select', { onchange: ev => { E.kv = ev.target.value; mudou(false); } }, KVS.map(x => h('option', { value: x, selected: x === E.kv }, KV_ROTULO[x] + (x === 'q8_0' ? ' — recomendado' : ''))))),
            h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: E.offload, onchange: ev => { E.offload = ev.target.checked; mudou(false); } }), 'Permitir transbordar para a RAM do PC (cabe modelo maior, mas fica bem mais lento)'),
            h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: E.comunidade, onchange: ev => { E.comunidade = ev.target.checked; mudou(false); } }), 'Incluir fine-tunes da comunidade'),
            h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: E.antigos, onchange: ev => { E.antigos = ev.target.checked; mudou(false); } }), 'Incluir modelos antigos (> 1 ano)')))));
    const zonaStatusCalc = h('div');
    const zonaAbasAtiv = h('div', { style: 'margin-bottom:14px' });
    let filtroAtividade = 'todas';

    function desenharRes() {
      const maq = perfilDe(E, dados), op = { kv: E.kv, ctx: E.ctx || null, comunidade: E.comunidade, antigos: E.antigos, offload: E.offload };
      const orcGb = Calc.orcamentoBytes(maq, maq.reserva_vram_gb ?? 1.3) / Calc.GIB;

      // Calcular escolhas para todas as atividades
      const resultadosPorPapel = new Map();
      for (const id of ATIVIDADES) {
        const papel = dados.papeis.find(p => p.id === id);
        if (papel) {
          resultadosPorPapel.set(id, { papel, res: Calc.escolher(dados, maq, papel, op) });
        }
      }

      // Card de Feedback e Status Reativo
      const geralRes = resultadosPorPapel.get('chat_pt')?.res;
      const rapidoRes = resultadosPorPapel.get('rapido')?.res;
      const topParrudo = geralRes?.parrudo?.c ? nomeAmigavelModelo(geralRes.parrudo.c.nome) : null;
      const topRapido = rapidoRes?.leve?.c ? nomeAmigavelModelo(rapidoRes.leve.c.nome) : (rapidoRes?.equilibrado?.c ? nomeAmigavelModelo(rapidoRes.equilibrado.c.nome) : null);

      zonaStatusCalc.replaceChildren(
        h('div', { class: 'cartao destaque pulso-calc', style: 'border-left:4px solid var(--ok, #10b981);margin-bottom:16px;background:var(--surface)' },
          h('div', { class: 'linha' },
            h('div', {},
              h('div', { class: 'linha', style: 'justify-content:flex-start;gap:8px;margin-bottom:4px' },
                chip('⚡ Atualizado agora para o seu hardware', 'ok'),
                h('b', { style: 'font-size:.95rem' }, maq.gpu ? (maq.gpu.nome || maq.nome) : maq.nome)),
              h('div', { class: 'sub' },
                `${fmtN(orcGb, 1)} GB disponíveis para o modelo · Contexto: ${op.ctx ? fmtCtx(op.ctx) : 'Padrão da atividade'} · Cache KV: ${op.kv}`)),
            (topParrudo || topRapido) ? h('div', { class: 'chips', style: 'align-items:center' },
              topParrudo ? chip('🏆 Campeão Geral: ' + topParrudo, 'neutro') : null,
              topRapido ? chip('⚡ Mais Veloz: ' + topRapido, 'neutro') : null) : null)));

      // Barra de Abas / Filtro Rápido de Atividades
      const abas = [
        ['todas', 'Todas as atividades (8)'],
        ['chat_pt', '💬 Geral / Conversa'],
        ['codigo', '💻 Código'],
        ['rapido', '⚡ Tarefas Rápidas'],
        ['raciocinio', '🧠 Raciocínio'],
        ['visao', '👁️ Visão'],
        ['contexto', '📚 Muito Contexto'],
        ['agente', '🛠️ Agentes'],
      ];

      zonaAbasAtiv.replaceChildren(
        h('div', { class: 'seg', role: 'group', 'aria-label': 'Filtrar atividade' },
          abas.map(([id, tit]) => h('button', {
            'aria-pressed': String(filtroAtividade === id),
            onclick: () => { filtroAtividade = id; desenharRes(); }
          }, tit))));

      // Renderizar apenas a atividade selecionada ou todas
      const ativsParaMostrar = filtroAtividade === 'todas'
        ? ATIVIDADES
        : [filtroAtividade];

      const cartoes = ativsParaMostrar
        .map(id => resultadosPorPapel.get(id))
        .filter(Boolean)
        .map(({ papel, res }) => cartaoAtividade(papel, res, maq, op, dados));

      zonaRes.replaceChildren(...cartoes);
      zonaGeral.replaceChildren(resumoGeral(maq, op));
      zonaUpgrade.replaceChildren(cartaoUpgrade(maq, op, dados, E));
      zonaGuia.replaceChildren(cartaoGuia(maq, op, dados));
      zonaLivre.replaceChildren(cartaoModeloLivre(maq));
      zonaMapa.replaceChildren(cartaoMapa(maq, op));
    }
    const zonaGuia = h('div'), zonaLivre = h('div'), zonaMapa = h('div');
    const cab = opts.solo ? h('div', { class: 'solo-topo' }, h('h1', {}, 'Calculadora de hardware para IA local'),
      h('p', { class: 'sub', style: 'max-width:70ch;margin-top:6px' }, 'Escolha sua placa de vídeo (ou Mac, ou só o processador) e veja que modelos de IA rodam nela, em qual quantização, com quanto contexto e a que velocidade — para cada tipo de uso. Funciona offline: nada sai do seu computador.'),
      h('div', { class: 'legenda', style: 'margin-top:8px' }, `Catálogo de ${dados.candidatos.length} modelos da varredura de ${fmtData(dados.radar)} · gerado em ${fmtData(dados.gerado)}`, dados.n_medidos ? chip(`${dados.n_medidos} com nota MEDIDA`, 'medido') : null))
      : h('div', { class: 'pagina-topo' },
          h('div', { class: 'eyebrow-tech' }, 'LOCAL INTELLIGENCE // HARDWARE & MODEL ADVISOR'),
          h('h1', {}, 'Calculadora de hardware'),
          h('p', { class: 'sub' }, 'Informe sua placa/memória nos cartões abaixo e veja instantaneamente o feed de modelos recomendados com base nos catálogos online do Ollama e Hugging Face.'));
    const linkAtual = () => { const e = { ...E, preset: '' }; return location.href.split('#')[0] + '#c=' + btoa(unescape(encodeURIComponent(JSON.stringify(e)))); };
    const botaoExportar = opts.aoExportar ? h('button', { class: 'btn', onclick: opts.aoExportar }, 'Baixar como arquivo para compartilhar')
      : opts.solo ? h('button', { class: 'btn', onclick: () => copiar(linkAtual()) }, 'Copiar link desta configuração') : null;
    el.replaceChildren(h('div', { class: 'calc' }, cab, botaoExportar ? h('div', { style: 'margin:-12px 0 18px' }, botaoExportar) : null,
      h('div', { class: 'calc-topo-grid' }, zonaHw, opcoes()),
      zonaGeral,
      titulo(`Feed de Recomendações (${dados.candidatos.length} modelos do Ollama + Hugging Face)`, 'Calculado em tempo real para o seu hardware: o mais capaz que cabe, o melhor equilíbrio e o mais rápido em cada atividade.'),
      zonaStatusCalc, zonaAbasAtiv,
      zonaRes,
      h('details', { class: 'painel-colapsavel', style: 'margin-top:24px' },
        h('summary', {},
          h('div', { class: 'linha', style: 'gap:10px' },
            h('h2', {}, 'Simulador de Upgrade, Modelo Livre e Guia Técnico'),
            chip('Ferramentas extras', 'neutro')),
          h('span', { class: 'colapsavel-dica' }, 'Clique para expandir')),
        h('div', { class: 'painel-conteudo empilha' },
          titulo('E se eu trocasse a placa?', 'O mesmo computador com outras placas de referência: quanto modelo a mais cabe e a que velocidade.'), zonaUpgrade,
          titulo('Cabe um modelo que não está na lista?', 'Digite os parâmetros de um modelo novo e veja se cabe no hardware escolhido.'), zonaLivre,
          titulo('Que tamanho cabe?', 'O maior modelo denso que cabe com folga, por quantização e contexto.'), zonaMapa,
          titulo('Guia: Quantização do modelo e do cache de contexto (KV)', 'O que mudar para caber mais modelo ou mais contexto — e onde ligar cada coisa.'), zonaGuia)),
      h('div', { class: opts.solo ? 'rodape-solo' : '', style: opts.solo ? '' : 'margin-top:28px' }, h('h3', {}, 'Como isto é calculado — e o que não sabe'),
        h('ul', { class: 'sub', style: 'padding-left:18px;max-width:80ch' },
          h('li', {}, 'Cabe = tamanho real do arquivo + cache de contexto (conta por arquitetura) + buffers. Em GPU a conta bate com o medido em ±1,5 GB (sempre para o lado seguro).'),
          h('li', {}, 'Velocidade = banda de memória ÷ bytes lidos por token × eficiência. Em GPU é confiável; em CPU vale ±2×; com RAM + GPU é só ordem de grandeza.'),
          h('li', {}, '“Mais capaz” ordena pelo porte efetivo (MoE = raiz de total × ativos), descontando quantização agressiva e geração antiga. É regra de bolso, não nota de qualidade.'),
          h('li', {}, 'Nota MEDIDA só existe para os modelos que o autor testou no protocolo v2 (9 testes públicos, mesmos itens para todos). Para os outros, teste no seu uso real.'),
          h('li', {}, 'Especificações de placas vêm das fichas dos fabricantes; se algo estiver errado ou faltar, informe os valores manualmente.')))));
    desenharHw(); desenharResumo(); desenharRes();
  }
  /* Deixa a calculadora já apontada para uma máquina do parque (usado pelo botão "Abrir na calculadora"). */
  function definirPreset(id, semGpu) { const e = lembrar(); e.modo = semGpu ? 'cpu' : 'gpu'; e.preset = id; guardar(e); }
  return { montar, dialogoModelo, avaliarVariante, gruposDeVariantes, linksDoModelo, comandosDe, perfilDe, definirPreset };
})();
