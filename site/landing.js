'use strict';
/* Página inicial: números do catálogo, prévia ao vivo do Radar (mesmo motor, calc.js) e eventos anônimos. */
(function () {
  const D = window.LI_DADOS;
  const $ = s => document.querySelector(s);
  const ev = (tipo, dados) => { if (typeof registrarEvento === 'function') registrarEvento(tipo, dados); };

  /* tema (mesma chave do app) */
  $('#l-tema').addEventListener('click', () => {
    const r = document.documentElement;
    const escuro = r.getAttribute('data-theme') ? r.getAttribute('data-theme') === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    const t = escuro ? 'light' : 'dark';
    r.setAttribute('data-theme', t);
    try { localStorage.setItem('li-tema', t); } catch (e) {}
  });

  /* links e eventos */
  if (typeof LINK_DOWNLOAD === 'string') $('#l-baixar').href = LINK_DOWNLOAD;
  if (typeof LINK_ZIP === 'string') $('#l-zip').href = LINK_ZIP;
  if (typeof NO_WINDOWS !== 'undefined' && !NO_WINDOWS) { const a = $('#l-alt-win'); if (a) a.textContent = 'Baixe o ZIP, extraia e dê dois cliques em “Abrir Local AI 4 You” (Mac e Linux).'; }
  if (typeof LINK_REPO === 'string') $('#l-github').href = LINK_REPO;
  if (typeof abrirApoio === 'function') $('#l-apoio').addEventListener('click', e => { e.preventDefault(); abrirApoio(); });
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-ev]');
    if (a) ev(a.dataset.ev === 'download' ? 'download' : 'cta', { origem: 'inicio-' + a.dataset.ev });
  });
  ev('pagina', { aba: 'inicio' });

  /* revelar seções ao rolar */
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(x => { if (x.isIntersecting) { x.target.classList.add('visto'); io.unobserve(x.target); } }), { threshold: 0.12 }) : null;
  document.querySelectorAll('.l-main > section:not(.l-hero)').forEach(s => { if (io) { s.classList.add('revelar'); io.observe(s); } });

  if (!D || typeof Calc === 'undefined') return;
  Calc.configurar(D.constantes);
  const hw = D.hardware;
  const cand = (D.candidatos || []).filter(c => !(c.caps || []).includes('decision'));
  const fmt = n => n.toLocaleString('pt-BR');
  $('#n-modelos').textContent = fmt(cand.length);
  $('#k-modelos').textContent = fmt(cand.length);
  $('#k-placas').textContent = fmt((hw.gpus || []).length + (hw.unificadas || []).length);
  $('#k-usos').textContent = (D.papeis || []).filter(p => !p.sem_nota).length;
  if (D.gerado) {
    const g = new Date(D.gerado), hoje = new Date();
    const dias = Math.floor((hoje - g) / 864e5);
    $('#k-data').textContent = dias <= 0 ? 'hoje' : dias === 1 ? 'ontem' : g.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
  }

  /* prévia: computadores de exemplo */
  const sis = (hw.sistemas || []).find(s => s.id === 'windows') || hw.sistemas[0];
  const mac = (hw.sistemas || []).find(s => s.id === 'macos') || sis;
  const cpu = hw.cpus.find(c => /Zen 4/.test(c.nome)) || hw.cpus[0];
  const memPerfil = cpu.bw ? { bw_min: cpu.bw[0], bw_max: cpu.bw[1] }
    : Calc.memBw(hw.memorias_ram.find(m => m.id === cpu.mem) || hw.memorias_ram[0], cpu.canais || 2);
  const gpu = id => hw.gpus.find(g => g.id === id);
  const chip = id => hw.unificadas.find(u => u.id === id);
  const EXEMPLOS = [
    ['Só CPU · 16 GB', () => Calc.perfilCpu({ ram_gb: 16, mem: memPerfil, cpu, sistema: sis })],
    ['RTX 3060 12 GB', () => gpu('rtx-3060-12') && Calc.perfilGpu({ gpu: gpu('rtx-3060-12'), n: 1, ram_gb: 32, mem: memPerfil, cpu, sistema: sis })],
    ['RTX 4060 8 GB', () => gpu('rtx-4060') && Calc.perfilGpu({ gpu: gpu('rtx-4060'), n: 1, ram_gb: 32, mem: memPerfil, cpu, sistema: sis })],
    ['RTX 4090 24 GB', () => gpu('rtx-4090') && Calc.perfilGpu({ gpu: gpu('rtx-4090'), n: 1, ram_gb: 64, mem: memPerfil, cpu, sistema: sis })],
    ['Mac M2 · 16 GB', () => chip('m2') && Calc.perfilUnificado({ chip: chip('m2'), ram_gb: 16, cpu: null, sistema: mac })],
  ];
  let atual = 2;
  const chips = $('#demo-chips');
  EXEMPLOS.forEach(([rot], i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = rot;
    b.addEventListener('click', () => { atual = i; desenhar(); ev('cta', { origem: 'inicio-demo-chip', perfil: rot }); });
    chips.appendChild(b);
  });
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const tps = e => { const t = Array.isArray(e.enc.tps_est) ? e.enc.tps_est[0] : e.enc.tps_est; return t >= 10 ? Math.round(t) : (Math.round(t * 10) / 10).toLocaleString('pt-BR'); };
  const USO = Object.fromEntries((D.papeis || []).map(p => [p.id, p.icone || '']));

  function desenhar() {
    [...chips.children].forEach((b, i) => b.setAttribute('aria-pressed', String(i === atual)));
    const lista = $('#demo-lista');
    let rk = [];
    try {
      const perfil = EXEMPLOS[atual][1]();
      if (perfil) {
        perfil.reserva_vram_gb = perfil.reserva_vram_gb ?? D.reserva_vram_gb ?? 1.3;
        const ids = (D.papeis || []).filter(p => !p.sem_nota).map(p => p.id);
        rk = Calc.ranking(D, perfil, ids, { kv: 'q8_0' });
        $('#demo-resumo').innerHTML = `<b>${fmt(rk.length)}</b> modelos cabem. Os 3 melhores:`;
      }
    } catch (e) { console.warn(e); }
    if (!rk.length) { lista.innerHTML = '<li class="l-carregando">Abra o Radar para ver a lista para o seu computador.</li>'; return; }
    const max = rk[0].nota || 100;
    lista.innerHTML = rk.slice(0, 3).map((e, i) => {
      const v = e.enc.variante || {};
      const usos = (e.papeis || []).slice(0, 4).map(p => USO[p] || '').join(' ');
      return `<li class="l-pos p${i + 1}" style="--d:${i * 70}ms">
        <span class="medalha m${i + 1}">${i + 1}</span>
        <div class="l-pos-info"><b>${esc(e.c.nome)}</b><span class="sub">${esc(v.quant || '')} · ~${tps(e)} tok/s ${usos ? '· ' + usos : ''}</span>
          ${v.pull ? `<code class="l-pull">ollama pull ${esc(v.pull)}</code>` : ''}</div>
        <div class="l-pos-nota"><span>${Math.round(e.nota)}</span><i style="--w:${Math.max(8, Math.round(100 * e.nota / max))}%"></i></div>
      </li>`;
    }).join('');
  }
  desenhar();
})();
