'use strict';
/* Motor da calculadora de hardware. JavaScript puro, sem dependências, sem DOM: roda no painel, no arquivo HTML autônomo
   e no Node (tests/test_calc.py confere que dá os mesmos números do li/fit.py e do li/decide.py).

   Tudo aqui é ESTIMATIVA (conta de memória e de banda). Os números de calibração (overheads, eficiências) vêm de li/fit.py:
   o painel os injeta com Calc.configurar(dados.constantes); os valores abaixo são o padrão para uso isolado. */
(function (raiz, fabrica) {
  if (typeof module === 'object' && module.exports) module.exports = fabrica();
  else raiz.Calc = fabrica();
})(typeof self !== 'undefined' ? self : this, function () {
  const GB = 1e9, GIB = 1024 ** 3;
  const K = {
    KV_BYTES: { f16: 2.0, q8_0: 1.0625, q4_0: 0.5625 },
    OVERHEAD_FIXO_GB: 0.15, OVERHEAD_POR_CTX_GB: 0.000004, ESTADO_LINEAR_GB: 0.10,
    EFICIENCIA: { gpu_denso: 0.78, gpu_moe: 0.50, cpu_avx512: 0.50, cpu_avx2: 0.45, cpu_avx: 0.40, cpu_neon: 0.60, cpu_sse: 0.25 },
    MIN_BPW: 3.2, CTX_DEGRAUS: [2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576], RAPIDO_MAX_GB: 5.0,
  };
  const configurar = c => { if (c) Object.assign(K, c); return K; };
  const trunc = Math.trunc;
  const r1 = x => Math.round(x * 10) / 10, r2 = x => Math.round(x * 100) / 100;
  const ou = (v, padrao) => (v === undefined || v === null ? padrao : v);

  // ---------------------------------------------------------------- memória
  function camadasPorTipo(arch) {
    if (arch.camadas_tipo) return arch.camadas_tipo;
    const n = trunc(arch.camadas || 0), tipos = arch.layer_types;
    if (tipos && tipos.length) {
      const cheias = tipos.filter(t => t.includes('full')).length;
      const desliz = tipos.filter(t => t.includes('sliding') || t.includes('local')).length;
      return [cheias, desliz, Math.max(tipos.length - cheias - desliz, 0)];
    }
    if (arch.intervalo_atencao_cheia) { const c = Math.max(1, Math.floor(n / arch.intervalo_atencao_cheia)); return [c, 0, n - c]; }
    if (arch.janela) {
      const frac = (arch.arquitetura || '').toLowerCase().includes('gemma') ? 1 / 6 : 1 / 2;
      const c = Math.max(1, Math.round(n * frac));
      return [c, n - c, 0];
    }
    return [n, 0, 0];
  }
  function kvBytes(arch, ctx, tipo = 'q8_0') {
    if (!arch || !arch.camadas || !arch.kv_heads) return 0;
    const [cheias, desliz0, lineares] = camadasPorTipo(arch);
    const b = ou(K.KV_BYTES[tipo], 1.0625);
    const kl = arch.key_len || 128, vl = arch.val_len || kl;
    const porToken = trunc(arch.kv_heads) * (kl + vl) * b;
    const porTokenCheia = (arch.kv_heads_global && arch.head_dim_global)
      ? trunc(arch.kv_heads_global) * trunc(arch.head_dim_global) * (arch.k_eq_v ? 1 : 2) * b : porToken;
    const desliz = Math.max(0, desliz0 - trunc(arch.kv_compartilhadas || 0));
    const janela = trunc(arch.janela || ctx);
    let total = cheias * porTokenCheia * ctx + desliz * porToken * Math.min(ctx, janela);
    if (lineares) total += K.ESTADO_LINEAR_GB * GB;
    return trunc(total);
  }
  const vramTotal = (peso, arch, ctx, tipo = 'q8_0') => trunc(peso + kvBytes(arch, ctx, tipo) + (K.OVERHEAD_FIXO_GB + K.OVERHEAD_POR_CTX_GB * ctx) * GB);

  function orcamentoBytes(maq, reservaVram = 1.3) {
    const gpu = maq.gpu;
    if (gpu && gpu.vram_gb) return trunc(Math.max(gpu.vram_gb - reservaVram, 0) * GIB);
    const ram = Number(maq.ram_gb || 0), teto = maq.max_modelo_gb;
    let reservaSo = Number(ou(maq.reserva_so_gb, 1.5));
    if (Math.abs(reservaVram - 1.3) > 1e-9) reservaSo = reservaVram;   // “memória livre” definida no painel vale também sem GPU (mesma regra de fit.py)
    let livre = ram - reservaSo;
    if (teto) livre = Math.min(livre, Number(teto));
    return trunc(Math.max(livre, 0) * GIB);
  }
  function ctxMaximo(peso, arch, orcamento, tipo, limite) {
    let melhor = 0;
    const temArch = arch && Object.keys(arch).length;
    const teto = temArch ? Math.min(limite || 1e9, trunc(arch.ctx_max || 1048576)) : (limite || 32768);
    for (const c of K.CTX_DEGRAUS) {
      if (c > teto) break;
      if (vramTotal(peso, arch || {}, c, tipo) <= orcamento) melhor = c;
    }
    return melhor;
  }
  function avaliarEncaixe(peso, arch, maq, ctxAlvo, tipo = 'q8_0', reservaVram = 1.3) {
    const orc = orcamentoBytes(maq, reservaVram);
    const ctxOk = ctxMaximo(peso, arch, orc, tipo);
    const usado = vramTotal(peso, arch || {}, ctxAlvo, tipo);
    let nivel;
    if (ctxOk >= ctxAlvo && usado <= orc * 0.92) nivel = 'confortavel';
    else if (ctxOk >= 4096) nivel = 'justo';
    else nivel = 'nao_cabe';
    return { nivel, ctx_max: ctxOk, usado_ctx_alvo_gb: r2(usado / GB), orcamento_gb: r2(orc / GB), folga_gb: r2((orc - usado) / GB), ctx_alvo: ctxAlvo };
  }

  // ---------------------------------------------------------------- quantização
  const bpw = (bytes, paramsB) => (paramsB ? (bytes * 8) / (paramsB * 1e9) : 0);
  function faixaQualidade(b) {
    if (b >= 6.0) return ['quase sem perda', 'praticamente igual ao original; gasta memória à toa em máquina apertada'];
    if (b >= 4.5) return ['excelente', 'perda muito pequena; ótimo quando sobra memória'];
    if (b >= 3.9) return ['ótima (padrão Q4)', 'o ponto de equilíbrio mais usado: perda pequena com 1/4 do tamanho'];
    if (b >= 3.0) return ['boa', 'perda pequena; aceitável quando é o que cabe (comparar com um modelo menor em Q4)'];
    if (b >= 2.3) return ['reduzida', 'perda perceptível em lógica/código; só vale se nada melhor couber'];
    return ['degradada', 'perda grande; prefira um modelo menor em Q4'];
  }
  // bits por peso típicos de cada formato GGUF (aproximados; o tamanho REAL do arquivo sempre vence quando conhecido)
  const BPW_QUANT = { IQ1_S: 1.6, IQ2_XXS: 2.1, IQ2_XS: 2.4, IQ2_S: 2.6, Q2_K: 3.0, IQ3_XXS: 3.1, IQ3_XS: 3.3, IQ3_S: 3.45, Q3_K_S: 3.5, Q3_K_M: 3.9, Q3_K_L: 4.2,
    IQ4_XS: 4.3, MXFP4: 4.25, Q4_0: 4.5, Q4_K_S: 4.6, Q4_K_M: 4.85, Q5_K_S: 5.5, Q5_K_M: 5.7, Q6_K: 6.6, Q8_0: 8.5, F16: 16, BF16: 16 };

  const simdDaMaquina = maq => {
    const s = new Set(maq.simd || []);
    return s.has('avx512') ? 'cpu_avx512' : s.has('avx2') ? 'cpu_avx2' : s.has('avx') ? 'cpu_avx' : s.has('neon') ? 'cpu_neon' : 'cpu_sse';
  };
  function estimarTps(pesoAtivoBytes, maq, moe = false) {
    if (pesoAtivoBytes <= 0) return null;
    const gpu = maq.gpu;
    let bwLo, bwHi, ef;
    if (gpu && gpu.bw_gbs) { bwLo = bwHi = Number(gpu.bw_gbs); ef = K.EFICIENCIA[moe ? 'gpu_moe' : 'gpu_denso']; }
    else {
      bwLo = Number(maq.bw_gbs_min || maq.bw_gbs || 0); bwHi = Number(maq.bw_gbs_max || maq.bw_gbs || bwLo);
      if (!bwLo) return null;
      ef = K.EFICIENCIA[simdDaMaquina(maq)] * (moe ? 0.8 : 1.0);
    }
    return [r1(ef * 0.75 * bwLo * 1e9 / pesoAtivoBytes), r1(ef * 1.2 * bwHi * 1e9 / pesoAtivoBytes)];
  }
  function pesoAtivo(pesoBytes, paramsB, ativosB) {
    if (paramsB && ativosB && ativosB < paramsB) return trunc(pesoBytes * Math.min(1.0, ativosB / paramsB + 0.04));
    return pesoBytes;
  }
  function escolherVariante(variantes, maq, arch, ctxAlvo, paramsB, tipo = 'q8_0', reservaVram = 1.3) {
    const gpu = !!(maq.gpu && maq.gpu.vram_gb);
    const teto = gpu ? 6.7 : 5.0;
    const av = variantes.map(v => ({ ...v, bpw: r2(bpw(v.bytes, paramsB)), encaixe: avaliarEncaixe(v.bytes + trunc(v.extra_bytes || 0), arch, maq, ctxAlvo, tipo, reservaVram) }));
    const cabem = av.filter(a => a.encaixe.nivel !== 'nao_cabe');
    const conf = cabem.filter(a => a.encaixe.nivel === 'confortavel');
    const maior = lst => lst.reduce((m, a) => (m === null || a.bpw > m.bpw ? a : m), null);
    const faixa = conf.filter(a => a.bpw >= K.MIN_BPW && a.bpw <= teto);
    if (faixa.length) return maior(faixa);
    const acima = conf.filter(a => a.bpw > teto);
    if (acima.length && !av.some(a => a.bpw <= teto)) return acima.reduce((m, a) => (m === null || a.bpw < m.bpw ? a : m), null);
    const justas = cabem.filter(a => a.bpw >= K.MIN_BPW && a.bpw <= teto);
    return justas.length ? maior(justas) : null;
  }

  // ---------------------------------------------------------------- candidato do radar numa máquina
  function ctxPara(maq, papel, ctxPedido) {
    let alvo = trunc(ctxPedido || papel.ctx_alvo || 8192);
    if (!(maq.gpu && maq.gpu.vram_gb) && !ctxPedido) {
      alvo = Math.min(alvo, (maq.ram_gb || 0) >= 8 ? 8192 : 4096);
      if (ou(maq.max_modelo_gb, 99) <= 2) alvo = Math.min(alvo, 4096);
    }
    return alvo;
  }
  function encaixeCandidato(c, maq, papel, cfg, ctxPedido) {
    const variantes = c.variantes.filter(v => v.bytes);
    if (!variantes.length) return null;
    let ctx = ctxPara(maq, papel, ctxPedido);
    if (c.ctx_max) ctx = Math.max(1024, Math.min(ctx, trunc(c.ctx_max)));   // mesma regra de decide.py: o modelo não aceita mais que isso
    const reserva = ou(cfg.reserva_vram_gb, 1.3), kv = cfg.kv_cache || 'q8_0';
    const v = escolherVariante(variantes, maq, c.arch, ctx, c.params_b, kv, reserva);
    if (!v) {
      const menor = variantes.reduce((m, x) => (x.bytes < m.bytes ? x : m));
      const enc = avaliarEncaixe(menor.bytes, c.arch, maq, ctx, kv, reserva);
      return { cabe: false, motivo: `nem a menor quantização (${menor.quant}) cabe: orçamento ${enc.orcamento_gb} GB`, variante: menor, encaixe: enc };
    }
    const tps = estimarTps(pesoAtivo(v.bytes, c.params_b, c.ativos_b), maq, !!c.moe);
    const q = faixaQualidade(v.bpw);
    return { cabe: true, variante: v, encaixe: v.encaixe, tps_est: tps, qualidade: q[0], qualidade_obs: q[1], ctx };
  }
  function fatorVelocidade(maq, tps) {
    if (!tps) return 1.0;
    const mid = (tps[0] + tps[1]) / 2;
    if (!(maq.gpu && maq.gpu.vram_gb)) return mid < 1.5 ? 0.35 : mid < 3 ? 0.6 : mid < 6 ? 0.85 : mid < 12 ? 1.0 : 1.1;
    return mid < 15 ? 0.7 : mid < 35 ? 0.96 : mid < 65 ? 1.04 : 1.12;
  }
  function prioridade(c, papelId, enc, maq) {
    const b = (c.prio || {})[papelId];
    if (!b) return 0;
    let escala = b.escala;
    const bp = enc && enc.variante ? ou(enc.variante.bpw, 4.5) : 4.5;
    if (bp < 3.0) escala *= 0.7; else if (bp < 3.5) escala *= 0.85;
    let pts = escala + b.resto;
    if (enc && enc.cabe) {
      pts *= fatorVelocidade(maq, enc.tps_est);
      if (enc.encaixe.nivel === 'justo') pts *= 0.8;
    }
    if (papelId === 'rapido' && (c.params_b || 0) >= 3.0 && (c.params_b || 0) <= 5.0) pts += 8;
    return Math.round(Math.max(0, Math.min(100, pts)));
  }

  // ---------------------------------------------------------------- o que é novo da calculadora
  function capacidade(c, v) {
    const eff = c.ativos_b ? (c.params_b * 0.70 + c.ativos_b * 0.30) : c.params_b;
    const b = v.bpw;
    const fq = b >= 6 ? 1.0 : b >= 4.5 ? 0.99 : b >= 3.9 ? 0.97 : b >= 3.5 ? 0.92 : b >= 3.2 ? 0.85 : 0.7;
    const d = c.dias;
    const fr = d == null ? 0.85 : d <= 120 ? 1.0 : d <= 300 ? 0.92 : d <= 500 ? 0.82 : 0.65;
    return { efetivo_b: r1(eff), fator_quant: fq, fator_geracao: fr, valor: eff * fq * fr };
  }

  function kvGuia(c, v, maq, ctx, reservaVram = 1.3) {
    const orc = orcamentoBytes(maq, reservaVram);
    const peso = v.bytes + trunc(v.extra_bytes || 0);
    const linhas = ['f16', 'q8_0', 'q4_0'].map(t => {
      const kv = kvBytes(c.arch, ctx, t), total = vramTotal(peso, c.arch, ctx, t);
      return { tipo: t, kv_gb: r2(kv / GB), total_gb: r2(total / GB), cabe: total <= orc, confortavel: total <= orc * 0.92, ctx_max: ctxMaximo(peso, c.arch, orc, t) };
    });
    const f16 = linhas[0];
    const pequeno = f16.kv_gb <= 0.8 || f16.kv_gb <= 0.06 * (orc / GB);
    let rec, porque;
    if (f16.total_gb <= 0.85 * (orc / GB)) {
      rec = 'f16';
      porque = pequeno ? `o cache desse modelo é pequeno (${f16.kv_gb} GB em ${ctx >= 1024 ? Math.round(ctx / 1024) + 'k' : ctx}): quantizá-lo quase não economiza.`
        : 'cabe com folga sem quantizar o cache; quantizar só vale se você precisar de mais contexto.';
    } else if (linhas[1].confortavel) {
      rec = 'q8_0'; porque = `com f16 não cabe com folga; q8_0 corta o cache quase pela metade (${f16.kv_gb} → ${linhas[1].kv_gb} GB) com perda desprezível na prática.`;
    } else if (linhas[2].cabe) {
      rec = 'q4_0'; porque = `só cabe com o cache em q4_0 (${linhas[2].kv_gb} GB). Funciona, mas a perda em contextos longos é maior: considere contexto menor ou uma quantização do modelo mais leve.`;
    } else { rec = null; porque = 'não cabe nesse contexto nem com o cache em q4_0: reduza o contexto ou escolha uma quantização/modelo menor.'; }
    return { tabela: linhas, recomendado: rec, porque, cache_pequeno: pequeno };
  }

  function hibridoVariante(c, v, maq, ctx, kv = 'q8_0', reservaVram = 1.3) {
    if (!(maq.gpu && maq.gpu.vram_gb) || maq.unificada) return null;
    const orcGpu = orcamentoBytes(maq, reservaVram);
    const orcRam = Math.max(Number(maq.ram_gb || 0) - Number(ou(maq.reserva_so_gb, 4)), 0) * GIB;
    const tot = vramTotal(v.bytes + trunc(v.extra_bytes || 0), c.arch, ctx, kv);
    if (tot <= orcGpu || tot > orcGpu + orcRam * 0.9) return null;
    const fg = Math.max(0, Math.min(1, orcGpu / tot)), ativo = pesoAtivo(v.bytes, c.params_b, c.ativos_b);
    const efG = K.EFICIENCIA[c.moe ? 'gpu_moe' : 'gpu_denso'], efC = K.EFICIENCIA[simdDaMaquina(maq)] * (c.moe ? 0.8 : 1.0);
    const bwG = Number(maq.gpu.bw_gbs || 0) * 1e9, bwCLo = Number(maq.bw_gbs_min || maq.bw_gbs || 0) * 1e9, bwCHi = Number(maq.bw_gbs_max || maq.bw_gbs || 0) * 1e9;
    if (!bwG || !bwCLo) return null;
    const tps = (fator, bwC) => 1 / (fg * ativo / (efG * fator * bwG) + (1 - fg) * ativo / (efC * fator * bwC));
    return { pct_gpu: Math.round(fg * 100), ram_usada_gb: r1(Math.max(tot - orcGpu, 0) / GB), total_gb: r2(tot / GB), tps_est: [r1(tps(0.75, bwCLo)), r1(tps(1.2, bwCHi || bwCLo))] };
  }
  function encaixeHibrido(c, maq, papel, cfg, ctxPedido) {
    if (!(maq.gpu && maq.gpu.vram_gb) || maq.unificada) return null;
    const reserva = ou(cfg.reserva_vram_gb, 1.3), kv = cfg.kv_cache || 'q8_0';
    const ctx = ctxPara(maq, papel, ctxPedido);
    const vs = c.variantes.filter(v => v.bytes).map(v => ({ ...v, bpw: r2(bpw(v.bytes, c.params_b)) })).filter(v => v.bpw >= K.MIN_BPW && v.bpw <= 6.7);
    const ok = vs.map(v => ({ v, h: hibridoVariante(c, v, maq, ctx, kv, reserva) })).filter(x => x.h);
    if (!ok.length) return null;
    const q4 = ok.filter(x => x.v.bpw <= 5.0);
    const esc = q4.length ? q4.reduce((m, x) => (x.v.bpw > m.v.bpw ? x : m)) : ok.reduce((m, x) => (x.v.bytes < m.v.bytes ? x : m));
    const { v, h } = esc, orcGpu = orcamentoBytes(maq, reserva);
    const enc = { nivel: 'justo', ctx_max: ctx, usado_ctx_alvo_gb: h.total_gb, orcamento_gb: r2(orcGpu / GB), folga_gb: r2(orcGpu / GB - h.total_gb), ctx_alvo: ctx };
    const q = faixaQualidade(v.bpw);
    return { cabe: true, offload: true, variante: { ...v, encaixe: enc }, encaixe: enc, pct_gpu: h.pct_gpu, ram_usada_gb: h.ram_usada_gb, tps_est: h.tps_est, qualidade: q[0], qualidade_obs: q[1], ctx };
  }

  // ---------------------------------------------------------------- escolhas por atividade
  const PADRAO_OPCOES = { kv: 'q8_0', ctx: null, comunidade: false, antigos: false, offload: false };
  function elegivel(c, papel, op) {
    if (c.confianca === 'comunidade' && !op.comunidade) return false;
    if (!op.antigos && (c.dias || 0) > 270) return false;
    if (c.origem === 'hf' && (c.pop || 0) < 4000) return false;
    const idPrio = papel.id === 'contexto' ? 'chat_pt' : papel.id;
    if (c.especializado && !(papel.id === 'visao' && c.especializado === 'ocr')) return false;
    if (!(c.papeis || []).includes(idPrio)) return false;
    if (c.origem === 'ollama' && (papel.exige || []).some(e => !(c.caps || []).includes(e))) return false;
    return true;
  }
  function avaliar(dados, maq, papel, opcoes) {
    const op = { ...PADRAO_OPCOES, ...(opcoes || {}) };
    const cfg = { kv_cache: op.kv, reserva_vram_gb: ou(maq.reserva_vram_gb, 1.3) };
    const idPrio = papel.id === 'contexto' ? 'chat_pt' : papel.id;
    const ctxPedido = op.ctx || (papel.id === 'contexto' ? papel.ctx_alvo : null);
    const out = [];
    for (const c of dados.candidatos) {
      if (!elegivel(c, papel, op)) continue;
      let enc = encaixeCandidato(c, maq, papel, cfg, ctxPedido);
      if ((!enc || !enc.cabe) && op.offload) enc = encaixeHibrido(c, maq, papel, cfg, ctxPedido);
      if (!enc || !enc.cabe) continue;
      const ctxNec = ctxPedido || enc.ctx;
      const alcanca = enc.offload ? true : enc.encaixe.ctx_max >= ctxNec;
      if (papel.id === 'contexto' && (!alcanca || (c.ctx_max && c.ctx_max < ctxNec))) continue;
      if (op.ctx && !alcanca) continue;
      out.push({ c, enc, prio: prioridade(c, idPrio, enc, maq), cap: capacidade(c, enc.variante), ctx: enc.ctx, offload: !!enc.offload });
    }
    return out;
  }
  const tpsMid = e => (e.enc.tps_est ? (e.enc.tps_est[0] + e.enc.tps_est[1]) / 2 : 0);
  const melhor = (lst, chave) => lst.reduce((m, x) => (m === null || chave(x) > chave(m) ? x : m), null);

  /* Três escolhas por atividade: a mais capaz que cabe, a de melhor equilíbrio e a leve/rápida. Sempre modelos distintos. */
  function escolher(dados, maq, papel, opcoes) {
    const op = { ...PADRAO_OPCOES, ...(opcoes || {}) };
    const lista = avaliar(dados, maq, papel, op);
    const gpu = !!(maq.gpu && maq.gpu.vram_gb);
    const usavel = e => (e.offload ? tpsMid(e) >= 2 : gpu ? tpsMid(e) >= 8 : tpsMid(e) >= 2);
    const orc = orcamentoBytes(maq, ou(maq.reserva_vram_gb, 1.3));
    const peso = e => e.enc.variante.bytes + trunc(e.enc.variante.extra_bytes || 0);
    const r = { parrudo: null, equilibrado: null, leve: null, total: lista.length, lista };
    const usados = new Set();
    const tomar = (nome, cand, chave) => {
      const livres = cand.filter(e => !usados.has(e.c.id));
      const m = melhor(livres, chave);
      if (m) { r[nome] = m; usados.add(m.c.id); }
    };
    const confort = lista.filter(e => !e.offload && e.enc.encaixe.nivel === 'confortavel' && usavel(e));
    const pool = lista.filter(e => usavel(e) && (e.offload || e.enc.encaixe.nivel === 'confortavel'));
    const poolParrudo = pool.length ? pool : lista.filter(usavel);
    tomar('parrudo', poolParrudo, e => e.cap.valor * 1000 + e.prio);

    const pesoParrudo = r.parrudo ? peso(r.parrudo) : orc;
    const tpsParrudo = r.parrudo ? tpsMid(r.parrudo) : 30;
    const ehCloneOuAntigoDominado = e => {
      if (!r.parrudo) return false;
      const pC = r.parrudo.c;
      const mesmaFam = (e.c.familia && pC.familia && (e.c.familia.startsWith(pC.familia.slice(0, 4)) || pC.familia.startsWith(e.c.familia.slice(0, 4))));
      const mesmoPorte = Math.abs(e.c.params_b - pC.params_b) / Math.max(e.c.params_b, pC.params_b) < 0.25;
      return mesmaFam && mesmoPorte && (e.c.dias || 0) > (pC.dias || 0);
    };

    // "melhor equilíbrio": prioriza modelos de porte intermediário que ocupam visivelmente menos VRAM que o parrudo
    // (≤75% do peso do parrudo e ≤66% do orçamento da GPU, ex.: gemma4:12b ou qwen3.5:9b em 16 GB).
    // Só cai para MoE de peso similar se não houver bom intermediário nessa faixa.
    const poolEquilLeve = confort.filter(e => {
      if (ehCloneOuAntigoDominado(e)) return false;
      return peso(e) <= 0.76 * pesoParrudo && peso(e) <= 0.66 * orc && e.c.params_b >= (gpu ? 6.0 : 2.5);
    });
    const poolEquilMoe = confort.filter(e => {
      if (ehCloneOuAntigoDominado(e)) return false;
      return e.c.moe && tpsMid(e) >= 1.45 * tpsParrudo && peso(e) <= 0.92 * pesoParrudo;
    });
    const poolEquilFinal = poolEquilLeve.length ? poolEquilLeve : (poolEquilMoe.length ? poolEquilMoe : confort.filter(e => !ehCloneOuAntigoDominado(e)));

    if (papel.id === 'contexto') {
      tomar('equilibrado', poolEquilFinal.length ? poolEquilFinal : confort, e => e.prio * 1000 + e.cap.valor);
      const leves = lista.filter(e => !e.offload && peso(e) <= 0.3 * orc && usavel(e) && e.c.params_b >= 3);
      tomar('leve', leves.length ? leves : confort, e => e.enc.encaixe.ctx_max * 1000 + e.prio);
    } else {
      tomar('equilibrado', poolEquilFinal.length ? poolEquilFinal : confort, e => e.prio * 1000 + e.cap.valor);
      const leves = lista.filter(e => !e.offload && peso(e) <= 0.38 * orc && usavel(e) && (papel.id === 'rapido' ? true : e.c.params_b >= 1.0));
      tomar('leve', leves.length ? leves : confort, e => (leves.length ? e.prio * 1000 : 0) + tpsMid(e));
    }
    r.alternativas = lista.filter(e => !usados.has(e.c.id)).sort((a, b) => b.prio - a.prio).slice(0, 4);
    return r;
  }

  // ---------------------------------------------------------------- perfis de hardware (formato do parque.json)
  function perfilGpu({ gpu, n = 1, ram_gb, mem, cpu, sistema }) {
    return { nome: (n > 1 ? n + '× ' : '') + gpu.nome, gpu: { nome: gpu.nome, vram_gb: gpu.vram_gb * n, bw_gbs: gpu.bw_gbs }, n_gpus: n,
      ram_gb, bw_gbs_min: mem.bw_min, bw_gbs_max: mem.bw_max, simd: cpu.simd, reserva_so_gb: sistema.reserva_ram_gb, reserva_vram_gb: sistema.reserva_vram_gb };
  }
  function perfilUnificado({ chip, ram_gb, cpu, sistema }) {
    const frac = chip.frac_gpu || (ram_gb <= 36 ? 0.67 : 0.75);
    return { nome: `${chip.nome} · ${ram_gb} GB`, unificada: true, gpu: { nome: chip.nome, vram_gb: r1(ram_gb * frac), bw_gbs: chip.bw_gbs }, ram_gb,
      bw_gbs_min: chip.bw_gbs, bw_gbs_max: chip.bw_gbs, simd: (cpu && cpu.simd) || ['neon'], reserva_so_gb: 0, reserva_vram_gb: 2.0 };
  }
  function perfilCpu({ ram_gb, mem, cpu, sistema, max_modelo_gb }) {
    return { nome: `Só CPU · ${ram_gb} GB`, gpu: null, ram_gb, bw_gbs_min: mem.bw_min, bw_gbs_max: mem.bw_max, simd: cpu.simd,
      reserva_so_gb: sistema.reserva_ram_gb, reserva_vram_gb: 0, max_modelo_gb: max_modelo_gb || null };
  }

  function memBw(mem, canais) {
    const th = mem.mts * 8 * canais / 1000;
    return { bw_min: r1(0.78 * th), bw_max: r1(th), teorica: r1(th) };
  }
  function classeTps(t) {
    if (!t) return ['?', 'neutro'];
    const m = (t[0] + t[1]) / 2;
    return m >= 40 ? ['muito rápido', 'ok'] : m >= 15 ? ['fluido', 'ok'] : m >= 6 ? ['usável', 'warn'] : ['lento — só em lote', 'bad'];
  }

  function archGenerica(paramsB) {
    return { arquitetura: 'generica', camadas: trunc(24 + 1.6 * Math.pow(paramsB, 0.9)), kv_heads: 8, key_len: 128, val_len: 128, ctx_max: 262144, generica: true };
  }
  function modeloLivre({ params_b, ativos_b, bpw: b, ctx, kv }, maq, reservaVram = 1.3) {
    const peso = trunc(params_b * 1e9 * b / 8), arch = archGenerica(params_b);
    const orc = orcamentoBytes(maq, reservaVram), total = vramTotal(peso, arch, ctx, kv);
    return { peso_gb: r2(peso / GB), kv_gb: r2(kvBytes(arch, ctx, kv) / GB), total_gb: r2(total / GB), orcamento_gb: r2(orc / GB), cabe: total <= orc, confortavel: total <= orc * 0.92,
      ctx_max: ctxMaximo(peso, arch, orc, kv), tps_est: estimarTps(pesoAtivo(peso, params_b, ativos_b), maq, !!ativos_b), folga_gb: r2((orc - total) / GB) };
  }
  function mapaTamanhos(maq, kv = 'q8_0', reservaVram = 1.3) {
    const orc = orcamentoBytes(maq, reservaVram);
    const quants = [['Q3_K_M', BPW_QUANT.Q3_K_M], ['Q4_K_M', BPW_QUANT.Q4_K_M], ['Q5_K_M', BPW_QUANT.Q5_K_M], ['Q8_0', BPW_QUANT.Q8_0]];
    const ctxs = [8192, 32768, 131072];
    const maxParams = (b, ctx) => {
      let lo = 0, hi = 2000;
      for (let i = 0; i < 40; i++) {
        const m = (lo + hi) / 2;
        const total = vramTotal(trunc(m * 1e9 * b / 8), archGenerica(m), ctx, kv);
        if (total * (1 / 0.92) <= orc) lo = m; else hi = m;
      }
      return Math.floor(lo * 10) / 10;
    };
    return { quants: quants.map(q => q[0]), ctxs, valores: quants.map(([, b]) => ctxs.map(ctx => maxParams(b, ctx))) };
  }

  return { K, configurar, GB, GIB, BPW_QUANT, camadasPorTipo, kvBytes, vramTotal, orcamentoBytes, ctxMaximo, avaliarEncaixe, bpw, faixaQualidade,
    simdDaMaquina, estimarTps, pesoAtivo, escolherVariante, ctxPara, encaixeCandidato, fatorVelocidade, prioridade, capacidade, kvGuia,
    hibridoVariante, encaixeHibrido, elegivel, avaliar, escolher, perfilGpu, perfilUnificado, perfilCpu, memBw, classeTps, archGenerica, modeloLivre, mapaTamanhos };
});
