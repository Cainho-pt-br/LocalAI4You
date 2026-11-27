'use strict';
/* Local Intelligence — Efeito visual de fundo inspirado em antigravity.google.
   Nuvem fluida de micro-cápsulas, traços geométricos e pontos orientados em campo vetorial 3D/2D,
   com gravidade zero, órbita magnética e onda de deslocamento suave ao redor do cursor. */

(function () {
  const canvas = document.createElement('canvas');
  canvas.id = 'bg-antigravity';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);

  const ctx = canvas.getContext('2d', { alpha: true });
  let w = 0, h = 0, dpr = 1;
  const pointer = {
    x: -9999, y: -9999,
    tx: -9999, ty: -9999,
    vx: 0, vy: 0,
    active: false,
    timer: null
  };

  // Paleta fiel ao Google Antigravity (Google Blue, Indigo, Violet, Cyan, Coral/Amber)
  const PALETTES = {
    dark: [
      { r: 66,  g: 133, b: 244 }, // Google Blue
      { r: 138, g: 180, b: 248 }, // Ice Blue
      { r: 161, g: 66,  b: 244 }, // Deepmind Violet
      { r: 36,  g: 193, b: 224 }, // Quantum Cyan
      { r: 234, g: 67,  b: 53  }, // Coral Red accent
      { r: 251, g: 188, b: 4   }  // Solar Amber accent
    ],
    light: [
      { r: 26,  g: 115, b: 232 }, // Google Blue
      { r: 66,  g: 133, b: 244 }, // Sky Blue
      { r: 147, g: 52,  b: 230 }, // Vivid Purple
      { r: 18,  g: 181, b: 203 }, // Teal Cyan
      { r: 234, g: 67,  b: 53  }, // Google Red
      { r: 249, g: 171, b: 0   }  // Google Yellow
    ]
  };

  const particles = [];

  function redimensionar() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function criarCampo() {
    particles.length = 0;
    // Grade espacial com jitter orgânico para distribuição equilibrada estilo antigravity.google
    const espaco = w < 768 ? 58 : 48;
    const cols = Math.ceil(w / espaco) + 1;
    const rows = Math.ceil(h / espaco) + 1;

    let idx = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const jx = (Math.random() - 0.5) * espaco * 0.85;
        const jy = (Math.random() - 0.5) * espaco * 0.85;
        const bx = c * espaco + jx;
        const by = r * espaco + jy;

        // Profundidade Z simulada (0.35 a 1.15) para parallax e foco
        const z = 0.35 + Math.random() * 0.8;
        // 72% cápsulas orientadas (dashes), 20% micro-esferas, 8% cruzes/diamantes sutis
        const rnd = Math.random();
        const shape = rnd < 0.72 ? 'pill' : (rnd < 0.92 ? 'dot' : 'ring');

        // Distribuição de cores: predominância de azuis/violetas/cianos com toques pontuais de coral/âmbar
        const corPool = [0, 0, 1, 1, 2, 2, 3, 3, 4, 5];
        const corIdx = corPool[idx % corPool.length];
        idx++;

        particles.push({
          bx, by,
          x: bx, y: by,
          vx: 0, vy: 0,
          z,
          shape,
          len: (shape === 'pill' ? (7 + Math.random() * 9) : (2.4 + Math.random() * 2.4)) * z,
          thick: (shape === 'pill' ? (2.1 + Math.random() * 1.1) : (2.2 + Math.random() * 1.5)) * z,
          angle: Math.random() * Math.PI * 2,
          phase: Math.random() * Math.PI * 2,
          corIdx,
          energy: 0
        });
      }
    }
  }

  window.addEventListener('resize', () => {
    redimensionar();
    criarCampo();
  }, { passive: true });

  window.addEventListener('mousemove', e => {
    pointer.tx = e.clientX;
    pointer.ty = e.clientY;
    if (!pointer.active) {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
    }
    pointer.active = true;
    clearTimeout(pointer.timer);
    pointer.timer = setTimeout(() => { pointer.active = false; }, 2800);
  }, { passive: true });

  window.addEventListener('mouseleave', () => {
    pointer.active = false;
  });

  let t0 = performance.now();
  function animar(agora) {
    requestAnimationFrame(animar);
    if (document.hidden) return;

    const dt = Math.min((agora - t0) / 1000, 0.05);
    t0 = agora;
    const tempo = agora * 0.00055;

    ctx.clearRect(0, 0, w, h);

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark' ||
      (!document.documentElement.getAttribute('data-theme') && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);

    const paleta = isDark ? PALETTES.dark : PALETTES.light;

    // Suavização cinemática do cursor
    if (pointer.active) {
      const nvx = pointer.tx - pointer.x;
      const nvy = pointer.ty - pointer.y;
      pointer.vx = pointer.vx * 0.75 + nvx * 0.25;
      pointer.vy = pointer.vy * 0.75 + nvy * 0.25;
      pointer.x += nvx * 0.22;
      pointer.y += nvy * 0.22;
    } else {
      pointer.vx *= 0.9;
      pointer.vy *= 0.9;
    }

    // Aura ambiental difusa no fundo (estilo spotlight tech)
    if (pointer.active) {
      const auraR = 320;
      const gAura = ctx.createRadialGradient(pointer.x, pointer.y, 10, pointer.x, pointer.y, auraR);
      if (isDark) {
        gAura.addColorStop(0, 'rgba(66, 133, 244, 0.09)');
        gAura.addColorStop(0.5, 'rgba(161, 66, 244, 0.04)');
        gAura.addColorStop(1, 'rgba(0, 0, 0, 0)');
      } else {
        gAura.addColorStop(0, 'rgba(26, 115, 232, 0.06)');
        gAura.addColorStop(0.5, 'rgba(147, 52, 230, 0.025)');
        gAura.addColorStop(1, 'rgba(255, 255, 255, 0)');
      }
      ctx.fillStyle = gAura;
      ctx.fillRect(0, 0, w, h);
    }

    const raioCampo = 230;
    const velCursor = Math.min(28, Math.hypot(pointer.vx, pointer.vy));

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      const c = paleta[p.corIdx];

      // Campo vetorial harmônico (fluxo sem gravidade)
      const nx = p.bx * 0.0028 + tempo * 0.9;
      const ny = p.by * 0.0028 - tempo * 0.7;
      const flowAngle = Math.sin(nx) * Math.cos(ny) * Math.PI * 1.6 + Math.cos(nx * 0.7 - ny) * 0.8;

      const floatX = Math.cos(flowAngle + p.phase) * (10 * p.z);
      const floatY = Math.sin(flowAngle + p.phase) * (10 * p.z) - Math.sin(tempo * 1.4 + p.phase) * (4 * p.z);

      const alvoX = p.bx + floatX;
      const alvoY = p.by + floatY;

      let alvoAngulo = flowAngle;

      // Interação física Antigravity com o cursor (anel de suspensão + alinhamento tangencial/radial)
      if (pointer.active) {
        const dx = p.x - pointer.x;
        const dy = p.y - pointer.y;
        const dist = Math.hypot(dx, dy);

        if (dist < raioCampo && dist > 0.5) {
          const u = 1 - dist / raioCampo;
          const ease = u * u * (3 - 2 * u); // smoothstep

          // Empuxo antigravitacional radial + leve vórtex magnético
          const push = ease * (24 + velCursor * 0.8) * p.z;
          const ux = dx / dist;
          const uy = dy / dist;
          // Componente tangencial sutil
          const tx = -uy * 0.28;
          const ty = ux * 0.28;

          p.vx += (ux + tx) * push * 0.14;
          p.vy += (uy + ty) * push * 0.14;
          p.energy = Math.min(1, p.energy + ease * 0.22);

          // As cápsulas se orientam suavemente acompanhando o campo ao redor do cursor
          const angCursor = Math.atan2(dy, dx) + Math.PI * 0.18;
          const diffAng = Math.atan2(Math.sin(angCursor - alvoAngulo), Math.cos(angCursor - alvoAngulo));
          alvoAngulo += diffAng * ease * 0.85;
        }
      }

      // Mola elástica de retorno para a posição de levitação
      p.vx += (alvoX - p.x) * 0.055;
      p.vy += (alvoY - p.y) * 0.055;
      p.vx *= 0.86;
      p.vy *= 0.86;

      p.x += p.vx;
      p.y += p.vy;
      p.energy *= 0.93;

      // Interpolação suave do ângulo da cápsula
      const dAng = Math.atan2(Math.sin(alvoAngulo - p.angle), Math.cos(alvoAngulo - p.angle));
      p.angle += dAng * 0.12;

      // Opacidade equilibrada para não poluir a leitura das tabelas, mas brilhar ao interagir
      const baseAlpha = isDark ? (0.18 * p.z) : (0.15 * p.z);
      const alpha = Math.min(0.85, baseAlpha + p.energy * (isDark ? 0.52 : 0.42));

      ctx.save();
      ctx.translate(p.x, p.y);

      if (p.shape === 'pill') {
        ctx.rotate(p.angle);
        const comp = p.len * (1 + p.energy * 0.55);
        const esp = p.thick * (1 + p.energy * 0.2);
        ctx.beginPath();
        ctx.moveTo(-comp * 0.5, 0);
        ctx.lineTo(comp * 0.5, 0);
        ctx.strokeStyle = `rgba(${c.r}, ${c.g}, ${c.b}, ${alpha.toFixed(3)})`;
        ctx.lineWidth = esp;
        ctx.lineCap = 'round';
        ctx.stroke();
      } else if (p.shape === 'dot') {
        const raio = p.thick * (0.9 + p.energy * 0.45);
        ctx.beginPath();
        ctx.arc(0, 0, raio, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${c.r}, ${c.g}, ${c.b}, ${alpha.toFixed(3)})`;
        ctx.fill();
      } else {
        const raio = p.thick * (1.2 + p.energy * 0.4);
        ctx.beginPath();
        ctx.arc(0, 0, raio, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${c.r}, ${c.g}, ${c.b}, ${(alpha * 0.9).toFixed(3)})`;
        ctx.lineWidth = 1.25;
        ctx.stroke();
      }

      ctx.restore();
    }
  }

  redimensionar();
  criarCampo();
  requestAnimationFrame(animar);
})();
