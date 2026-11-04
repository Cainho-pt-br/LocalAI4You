'use strict';
// Propriedades do motor de escolhas (sem comparar com o Python): monotonia e coerência em três hardwares.
const path = require('path');
const fs = require('fs');
const Calc = require(path.join(__dirname, '..', '..', 'web', 'calc.js'));
let entrada = '';
process.stdin.on('data', d => (entrada += d));
process.stdin.on('end', () => {
  const dados = JSON.parse(entrada);
  Calc.configurar(dados.constantes);
  const hw = dados.hardware;
  const erros = [];
  const ok = (cond, msg) => { if (!cond) erros.push(msg); };
  const win = hw.sistemas.find(s => s.id === 'windows'), avx2 = hw.cpus.find(c => /Ryzen 7000 \(Zen 4\)/.test(c.nome));
  const ddr4 = Calc.memBw(hw.memorias_ram.find(m => m.id === 'ddr4-3200'), 2);
  const gpu = id => hw.gpus.find(g => g.id === id);
  const p16 = Calc.perfilGpu({ gpu: gpu('rtx-5060-ti-16'), ram_gb: 32, mem: ddr4, cpu: avx2, sistema: win });
  const p24 = Calc.perfilGpu({ gpu: gpu('rtx-4090'), ram_gb: 64, mem: ddr4, cpu: avx2, sistema: win });
  const p8 = Calc.perfilGpu({ gpu: gpu('rtx-4060'), ram_gb: 16, mem: ddr4, cpu: avx2, sistema: win });
  const pcpu = Calc.perfilCpu({ ram_gb: 16, mem: ddr4, cpu: avx2, sistema: win });
  const papel = id => dados.papeis.find(p => p.id === id);
  const cap = (maq, id) => { const r = Calc.escolher(dados, maq, papel(id), {}); return r.parrudo ? r.parrudo.cap.valor : 0; };

  ok(cap(p24, 'chat_pt') >= cap(p16, 'chat_pt'), 'mais VRAM não pode render um modelo menos capaz');
  ok(cap(p16, 'chat_pt') >= cap(p8, 'chat_pt'), '16 GB >= 8 GB');
  for (const maq of [p16, p24, p8, pcpu]) {
    for (const p of dados.papeis) {
      const r = Calc.escolher(dados, maq, p, {});
      const ids = [r.parrudo, r.equilibrado, r.leve].filter(Boolean).map(e => e.c.id);
      ok(new Set(ids).size === ids.length, `escolhas repetidas em ${maq.nome}/${p.id}: ${ids}`);
      for (const e of [r.parrudo, r.equilibrado, r.leve].filter(Boolean)) {
        ok(e.enc.cabe, 'escolha que não cabe');
        const g = Calc.kvGuia(e.c, e.enc.variante, maq, e.ctx, maq.reserva_vram_gb);
        const t = Object.fromEntries(g.tabela.map(x => [x.tipo, x]));
        ok(t.q4_0.total_gb <= t.q8_0.total_gb && t.q8_0.total_gb <= t.f16.total_gb, 'o cache menor tem de ocupar menos');
        ok(t.q4_0.ctx_max >= t.q8_0.ctx_max && t.q8_0.ctx_max >= t.f16.ctx_max, 'cache menor tem de caber mais contexto');
      }
    }
  }
  const sem = Calc.escolher(dados, p8, papel('chat_pt'), { offload: false }).total;
  const com = Calc.escolher(dados, p8, papel('chat_pt'), { offload: true }).total;
  ok(com >= sem, 'permitir RAM não pode reduzir as opções');
  // monotonia do mapa e do modelo livre
  const m = Calc.mapaTamanhos(p16, 'q8_0', 1.3);
  for (let q = 0; q < m.quants.length; q++) for (let c = 1; c < m.ctxs.length; c++) ok(m.valores[q][c] <= m.valores[q][c - 1], 'mais contexto => modelo máximo menor');
  for (let q = 1; q < m.quants.length; q++) for (let c = 0; c < m.ctxs.length; c++) ok(m.valores[q][c] <= m.valores[q - 1][c], 'mais bits => modelo máximo menor');
  const a = Calc.modeloLivre({ params_b: 14, bpw: 4.85, ctx: 8192, kv: 'q8_0' }, p16), b = Calc.modeloLivre({ params_b: 14, bpw: 4.85, ctx: 65536, kv: 'q8_0' }, p16);
  ok(b.total_gb > a.total_gb, 'mais contexto usa mais memória');
  ok(Calc.modeloLivre({ params_b: 400, bpw: 4.85, ctx: 8192, kv: 'q8_0' }, p16).cabe === false, '400B não cabe em 16 GB');
  process.stdout.write(JSON.stringify({ erros }));
});
