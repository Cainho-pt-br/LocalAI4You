'use strict';
// Lê os casos "de ouro" calculados pelo Python (li/fit.py, li/decide.py) em stdin e refaz cada um com web/calc.js.
// Imprime em stdout a lista de divergências (JSON). Vazia = o JS da calculadora dá os mesmos números do Python.
const path = require('path');
const Calc = require(path.join(__dirname, '..', '..', 'web', 'calc.js'));
let entrada = '';
process.stdin.on('data', d => (entrada += d));
process.stdin.on('end', () => {
  const g = JSON.parse(entrada);
  Calc.configurar(g.constantes);
  const diffs = [];
  const igual = (nome, caso, esperado, obtido, tol) => {
    const ok = (typeof esperado === 'number' && typeof obtido === 'number') ? Math.abs(esperado - obtido) <= tol
      : JSON.stringify(esperado) === JSON.stringify(obtido);
    if (!ok) diffs.push({ nome, caso, esperado, obtido });
  };
  const parSeq = (nome, caso, e, o, tol) => {
    if (e === null || o === null) return igual(nome, caso, e, o, tol);
    e.forEach((x, i) => igual(nome, caso, x, o[i], tol));
  };
  for (const c of g.casos) {
    if (c.tipo === 'kv') {
      igual('kv_bytes', c.id, c.kv_bytes, Calc.kvBytes(c.arch, c.ctx, c.kv), 0);
      igual('vram_total', c.id, c.vram_total, Calc.vramTotal(c.peso, c.arch, c.ctx, c.kv), 0);
    } else if (c.tipo === 'maquina') {
      igual('orcamento', c.id, c.orcamento, Calc.orcamentoBytes(c.maq, c.reserva), 0);
      const e = Calc.avaliarEncaixe(c.peso, c.arch, c.maq, c.ctx, c.kv, c.reserva);
      for (const k of ['nivel', 'ctx_max']) igual('encaixe.' + k, c.id, c.encaixe[k], e[k], 0);
      for (const k of ['usado_ctx_alvo_gb', 'orcamento_gb', 'folga_gb']) igual('encaixe.' + k, c.id, c.encaixe[k], e[k], 0.0101);
      parSeq('tps_denso', c.id, c.tps_denso, Calc.estimarTps(c.peso, c.maq, false), 0.101);
      parSeq('tps_moe', c.id, c.tps_moe, Calc.estimarTps(c.peso, c.maq, true), 0.101);
    } else if (c.tipo === 'variante') {
      const v = Calc.escolherVariante(c.variantes, c.maq, c.arch, c.ctx, c.params_b, c.kv, c.reserva);
      igual('escolher_variante', c.id, c.quant, v ? v.quant : null, 0);
    } else if (c.tipo === 'candidato') {
      const enc = Calc.encaixeCandidato(c.cand, c.maq, c.papel, { kv_cache: c.kv, reserva_vram_gb: c.reserva });
      igual('enc.cabe', c.id, c.enc.cabe, !!(enc && enc.cabe), 0);
      if (c.enc.cabe && enc && enc.cabe) {
        igual('enc.quant', c.id, c.enc.quant, enc.variante.quant, 0);
        igual('enc.nivel', c.id, c.enc.nivel, enc.encaixe.nivel, 0);
        igual('enc.ctx_max', c.id, c.enc.ctx_max, enc.encaixe.ctx_max, 0);
        parSeq('enc.tps', c.id, c.enc.tps, enc.tps_est, 0.101);
        igual('prioridade', c.id, c.prioridade, Calc.prioridade(c.cand, c.papel.id, enc, c.maq), 1);
      }
    } else if (c.tipo === 'estrutura') {
      // arquitetura bruta (Python) x compacta (JS): as camadas por tipo têm de coincidir
      igual('camadas_tipo', c.id, c.camadas_tipo, Calc.camadasPorTipo(c.arch_compacta), 0);
    }
  }
  process.stdout.write(JSON.stringify(diffs));
});
