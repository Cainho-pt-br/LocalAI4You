'use strict';
/* Página "Parque": Seleção interativa e direta de máquinas (PC Principal, Notebook, Raspberry Pi, etc.),
   hardware real, kit essencial de 1 clique e recomendações por função. */

async function pParque() {
  const raiz = $('#p-parque');
  const topo = h('div', { class: 'pagina-topo' },
    h('h1', {}, 'Parque de Máquinas'),
    h('p', { class: 'sub' }, 'Escolha uma máquina para ver instantaneamente o que cabe nela, o kit essencial e os melhores modelos por função.'));
  raiz.replaceChildren(topo, h('div', { class: 'sub' }, 'Carregando máquinas do parque…'));

  let d;
  try { d = await api('/api/parque'); } catch (e) { raiz.append(h('div', { class: 'aviso-caixa' }, e.message)); return; }

  const f = d.fontes;
  const maquinas = d.maquinas || [];
  if (!maquinas.length) {
    raiz.replaceChildren(topo, h('div', { class: 'vazio' }, 'Nenhuma máquina cadastrada no parque.'));
    return;
  }

  // Estado da máquina selecionada
  const maqIdAtual = S.parqueMaq || (S.parqueMaq = maquinas[0].maquina.id);
  const entradaAtual = maquinas.find(e => e.maquina.id === maqIdAtual) || maquinas[0];

  // Barra Seletora de Máquinas
  const seletor = h('div', { class: 'seg', style: 'margin-bottom:18px' },
    maquinas.map(e => {
      const m = e.maquina;
      const ehAtiva = m.id === entradaAtual.maquina.id;
      const icone = m.gpu ? '🖥️' : (m.id.includes('pi') ? '🍓' : '💻');
      return h('button', {
        'aria-pressed': String(ehAtiva),
        onclick: () => { S.parqueMaq = m.id; pParque(); },
        title: `${m.nome}: ${m.ram_gb} GB RAM` + (m.gpu ? ` · ${m.gpu.nome}` : '')
      }, `${icone} ${m.nome}`);
    }));

  const m = entradaAtual.maquina;
  const g = m.gpu;
  const ehCpu = !g || !g.vram_gb;

  // Compilar candidatos únicos ajustados para esta máquina
  const mapaCand = new Map();
  for (const [pid, lst] of Object.entries(entradaAtual.papeis || {})) {
    for (const c of lst) {
      if (!mapaCand.has(c.id)) {
        mapaCand.set(c.id, { ...c, papeisAtende: [pid] });
      } else {
        mapaCand.get(c.id).papeisAtende.push(pid);
      }
    }
  }
  const candidatos = Array.from(mapaCand.values());

  // Seleção Inteligente: Modelo Campeão Geral (Coringa) e Alternativa de Máxima Fluidez
  // Ordenar por equilíbrio técnico ajustado ao hardware
  let campeaoGeral = null;
  let maisVeloz = null;

  if (candidatos.length) {
    // 1. Campeão Geral: modelo mais capaz e equilibrado que cabe com folga para todas as funções
    const candidatosGerais = [...candidatos].sort((a, b) => {
      // Prioridade: cabe com folga, tamanho equilibrado para o hardware, cobrindo papéis principais
      const folgaA = a.encaixe.encaixe.folga_gb || 0;
      const folgaB = b.encaixe.encaixe.folga_gb || 0;
      const tpsA = a.encaixe.tps_est ? (a.encaixe.tps_est[0] + a.encaixe.tps_est[1]) / 2 : 0;
      const tpsB = b.encaixe.tps_est ? (b.encaixe.tps_est[0] + b.encaixe.tps_est[1]) / 2 : 0;
      const paramsA = a.params_b || 0;
      const paramsB = b.params_b || 0;

      if (ehCpu) {
        // Em CPU: modelos entre 2B e 5B com tps > 6 são o sweet spot absoluto
        const bomCpuA = paramsA >= 2.0 && paramsA <= 5.0 && tpsA >= 5;
        const bomCpuB = paramsB >= 2.0 && paramsB <= 5.0 && tpsB >= 5;
        if (bomCpuA !== bomCpuB) return bomCpuA ? -1 : 1;
        return (b.prioridade?.pontos || 0) - (a.prioridade?.pontos || 0);
      } else {
        // Em GPU: prefere modelos de alta capacidade (14B a 27B) que deixem pelo menos 1.5 GB de folga
        const cabeFolgaA = folgaA >= 1.2;
        const cabeFolgaB = folgaB >= 1.2;
        if (cabeFolgaA !== cabeFolgaB) return cabeFolgaA ? -1 : 1;
        // Prioriza maior capacidade com prioridade alta
        return (paramsB * 2 + (b.prioridade?.pontos || 0)) - (paramsA * 2 + (a.prioridade?.pontos || 0));
      }
    });

    campeaoGeral = candidatosGerais[0] || null;

    // 2. Alternativa Mais Veloz / Fluida: maior tok/s mantendo qualidade mínima (>= 1B)
    const candidatosVelozes = [...candidatos]
      .filter(c => c.id !== campeaoGeral?.id)
      .sort((a, b) => {
        const tpsA = a.encaixe.tps_est ? (a.encaixe.tps_est[0] + a.encaixe.tps_est[1]) / 2 : 0;
        const tpsB = b.encaixe.tps_est ? (b.encaixe.tps_est[0] + b.encaixe.tps_est[1]) / 2 : 0;
        return tpsB - tpsA;
      });

    maisVeloz = candidatosVelozes[0] || null;
  }

  // Card Resumo de Hardware da Máquina Selecionada
  const cardHardware = h('div', { class: 'cartao', style: 'border-left:4px solid var(--ink);margin-bottom:20px' },
    h('div', { class: 'linha' },
      h('div', {},
        h('h2', {}, m.nome, ' ', chip(m.online ? 'online' : 'perfil salvo', m.online ? 'ok' : 'neutro')),
        h('div', { class: 'sub', style: 'margin-top:2px' }, m.papel || 'Máquina do seu ambiente')),
      h('div', { class: 'linha', style: 'gap:8px' },
        h('button', { class: 'btn mini', onclick: () => { S.filtroRadar.maquina = m.id; irPara('radar'); } }, 'Ver no Radar'),
        h('button', { class: 'btn mini primario', onclick: () => { LI_CALC_UI.definirPreset(m.id, !g); irPara('calculadora'); } }, 'Simular na Calculadora'))),
    h('div', { class: 'resumo-hw', style: 'margin-top:12px' },
      h('span', {}, 'CPU: ', h('b', {}, m.cpu)),
      h('span', {}, 'Memória: ', h('b', {}, `${m.ram_gb} GB RAM`)),
      g ? h('span', {}, 'GPU: ', h('b', {}, `${g.nome} (${g.vram_gb} GB)`)) : h('span', { class: 'sub' }, 'GPU: nenhuma (processamento via CPU e RAM)'),
      h('span', {}, 'Teto p/ modelo: ', h('b', {}, g ? `${g.vram_gb} GiB VRAM` : `${m.max_modelo_gb ?? (m.ram_gb - m.reserva_so_gb).toFixed(1)} GB RAM`)),
      m.runtime ? h('span', {}, 'Runtime: ', h('b', {}, m.runtime)) : null));

  // Blocos de Destaque: Modelo Campeão Geral + Alternativa de Fluidez
  let blocoDestaques = null;
  if (campeaoGeral || maisVeloz) {
    const cardGeral = campeaoGeral ? (() => {
      const v = campeaoGeral.encaixe.variante;
      const e = campeaoGeral.encaixe.encaixe;
      const nomeL = nomeAmigavelModelo(campeaoGeral.nome);
      const tpsEst = campeaoGeral.encaixe.tps_est ? fmtTps(campeaoGeral.encaixe.tps_est) : '—';
      return h('div', { class: 'cartao destaque', style: 'border:2px solid var(--accent, #3b82f6);background:var(--surface)' },
        h('div', { class: 'linha topo' },
          h('div', {},
            chip('🏆 Recomendado Geral · Todas as Funções', 'ok'),
            h('h3', { style: 'font-size:1.15rem;margin:8px 0 2px' }, nomeL),
            h('div', { class: 'sub' }, `${campeaoGeral.params_b}B · Quantização ${v.quant} · ${fmtGB(v.bytes)}`)),
          h('div', { style: 'text-align:right' },
            h('div', { class: 'num', style: 'font-size:1.3rem;font-weight:700;color:var(--text)' }, `~${tpsEst}`),
            h('div', { class: 'sub', style: 'font-size:.75rem' }, 'tok/s estimados'))),
        h('p', { class: 'sub', style: 'margin:10px 0 12px;line-height:1.5' },
          ehCpu
            ? `Modelo equilibrado perfeito para CPU: entrega qualidade em conversas, código e tarefas gerais sem sobrecarregar a RAM de ${m.ram_gb} GB.`
            : `Modelo coringa mais capaz para esta máquina: roda 100% na VRAM com folga de ${fmtN(e.folga_gb, 1)} GB e suporta contexto confortável até ${fmtCtx(e.ctx_max)} tokens.`),
        h('div', { class: 'metricas', style: 'margin-bottom:12px' },
          h('span', {}, 'Memória: ', h('b', {}, fmtGB(v.bytes))),
          h('span', {}, 'Contexto: ', h('b', {}, `até ${fmtCtx(e.ctx_max)}`)),
          h('span', {}, 'Folga: ', h('b', {}, `${fmtN(e.folga_gb, 1)} GB`))),
        cmd('ollama pull ' + v.pull));
    })() : null;

    const cardRapido = maisVeloz ? (() => {
      const v = maisVeloz.encaixe.variante;
      const e = maisVeloz.encaixe.encaixe;
      const nomeL = nomeAmigavelModelo(maisVeloz.nome);
      const tpsEst = maisVeloz.encaixe.tps_est ? fmtTps(maisVeloz.encaixe.tps_est) : '—';
      return h('div', { class: 'cartao', style: 'border:1px solid var(--line-strong);background:var(--surface)' },
        h('div', { class: 'linha topo' },
          h('div', {},
            chip('⚡ Máxima Fluidez · Resposta Instantânea', 'neutro'),
            h('h3', { style: 'font-size:1.15rem;margin:8px 0 2px' }, nomeL),
            h('div', { class: 'sub' }, `${maisVeloz.params_b}B · Quantização ${v.quant} · ${fmtGB(v.bytes)}`)),
          h('div', { style: 'text-align:right' },
            h('div', { class: 'num', style: 'font-size:1.3rem;font-weight:700;color:var(--ok)' }, `~${tpsEst}`),
            h('div', { class: 'sub', style: 'font-size:.75rem' }, 'tok/s ultrarrápido'))),
        h('p', { class: 'sub', style: 'margin:10px 0 12px;line-height:1.5' },
          'Excelente para uso em tempo real, automações, triagem e respostas rápidas. Consumo levíssimo de memória e resposta instantânea.'),
        h('div', { class: 'metricas', style: 'margin-bottom:12px' },
          h('span', {}, 'Memória: ', h('b', {}, fmtGB(v.bytes))),
          h('span', {}, 'Contexto: ', h('b', {}, `até ${fmtCtx(e.ctx_max)}`)),
          h('span', {}, 'Velocidade: ', h('b', {}, `~${tpsEst} tok/s`))),
        cmd('ollama pull ' + v.pull));
    })() : null;

    blocoDestaques = h('div', { class: 'grade g2', style: 'margin-bottom:24px' }, cardGeral, cardRapido);
  }

  // Tabela Comparativa de Outras Boas Opções Viáveis para a Máquina
  let blocoTabela = null;
  if (candidatos.length > 2) {
    const outrasOpcoes = candidatos
      .filter(c => c.id !== campeaoGeral?.id && c.id !== maisVeloz?.id)
      .slice(0, 8);

    if (outrasOpcoes.length) {
      const linhas = outrasOpcoes.map(c => {
        const v = c.encaixe.variante;
        const e = c.encaixe.encaixe;
        const nomeL = nomeAmigavelModelo(c.nome);
        const tpsEst = c.encaixe.tps_est ? fmtTps(c.encaixe.tps_est) : '—';
        return h('tr', {},
          h('td', {},
            h('b', {}, nomeL),
            h('div', { class: 'sub' }, `${c.params_b}B · ${v.quant}`)),
          h('td', { class: 'num' }, fmtGB(v.bytes)),
          h('td', { class: 'num' }, `~${tpsEst}`),
          h('td', { class: 'num' }, fmtCtx(e.ctx_max)),
          h('td', { class: 'num' }, `${fmtN(e.folga_gb, 1)} GB`),
          h('td', {}, cmd('ollama pull ' + v.pull)));
      });

      blocoTabela = h('div', { class: 'cartao', style: 'margin-bottom:20px' },
        h('h3', {}, 'Outras opções técnicas viáveis para ' + m.nome),
        h('p', { class: 'sub', style: 'margin-bottom:12px' }, 'Modelos alternativos que cabem na memória desta máquina com boa velocidade.'),
        h('div', { class: 'tabela-wrap' },
          h('table', { class: 'tabela-compacta' },
            h('thead', {},
              h('tr', {},
                h('th', {}, 'Modelo'),
                h('th', { class: 'num' }, 'Tamanho'),
                h('th', { class: 'num' }, 'tok/s'),
                h('th', { class: 'num' }, 'Contexto'),
                h('th', { class: 'num' }, 'Folga'),
                h('th', {}, 'Comando'))),
            h('tbody', {}, linhas))));
    }
  }

  // Dica recolhível de medição e broker
  const dicaInfo = h('details', { class: 'dica-clean', style: 'margin-top:18px' },
    h('summary', {}, 'ℹ Informações de inventário e como calibrar outras máquinas'),
    h('div', { class: 'sub', style: 'margin-top:6px;line-height:1.6' },
      `Fontes do hardware: ${f.broker ? 'inventário ao vivo do broker ✔' : 'broker offline (usando o perfil salvo da rede)'}${f.local ? ' · detecção local em ' + f.local : ''}. `,
      'Para medir e calibrar uma nova máquina com CPU/RAM/VRAM reais, execute nela: ',
      h('code', {}, 'python deploy/medir-maquina.py --texto')));

  raiz.replaceChildren(topo, seletor, cardHardware, blocoDestaques, blocoTabela, dicaInfo);
}

// ---------------------------------------------------------------- OFFLINE
async function pOffline() {
  const raiz = $('#p-offline');
  const topo = h('div', { class: 'pagina-topo' },
    h('h1', {}, 'Prontidão offline'),
    h('p', { class: 'sub' }, 'Se a internet cair — ou você precisar de inteligência local sem nuvem — o que você tem?'));
  raiz.replaceChildren(topo, h('div', { class: 'sub' }, 'Verificando…'));

  let d;
  try { d = await api('/api/offline'); } catch (e) { raiz.append(h('div', { class: 'aviso-caixa' }, e.message)); return; }

  const ic = { ok: '✅', atencao: '⚠️', falta: '❌', info: 'ℹ️' };
  const dest = h('input', {
    type: 'text',
    value: d.kit?.destino || '',
    placeholder: 'Ex.: E:\\kit-offline  (HD externo ou outro disco)',
    style: 'width:min(460px,100%)'
  });

  const sel = new Set(Object.values(d.cobertura || {}).map(c => c.modelo).filter(Boolean));
  const instal = (S.mesa?.instalados || []);
  const checks = instal.map(x => {
    const c = h('input', { type: 'checkbox', checked: sel.has(x.id), value: x.id });
    return h('label', { class: 'chk' }, c, `${formatarNomeModelo(x.id)} (${fmtGB(x.bytes)})`);
  });

  raiz.replaceChildren(
    topo,
    h('div', { class: d.nivel === 'pronto' ? 'ok-caixa' : 'aviso-caixa' }, h('b', {}, d.resumo)),
    h('div', { class: 'checklist', style: 'margin-top:14px' },
      (d.itens || []).map(i => h('div', { class: 'item' },
        h('div', { class: 'ic' }, ic[i.status] || 'ℹ️'),
        h('div', {},
          h('b', {}, i.titulo),
          h('div', { class: 'sub' }, i.detalhe),
          i.acao ? h('div', { class: 'acao-txt' }, '→ ' + i.acao) : null)))),
    titulo('Kit offline (segunda cópia)', 'Copia manifestos + arquivos dos modelos escolhidos para outra pasta/disco, com um guia de restauração e um .bat que usa o kit direto.'),
    h('div', { class: 'cartao' },
      h('div', { class: 'filtros' }, dest),
      h('div', { class: 'filtros' }, checks),
      h('div', { class: 'dlg-acoes' },
        h('button', { class: 'btn primario', onclick: async () => {
          const ms = checks.map(l => l.firstChild).filter(c => c.checked).map(c => c.value);
          try {
            await api('/api/offline/exportar', { destino: dest.value, modelos: ms });
            toast('Exportação iniciada.');
            await carregarJobs();
          } catch (e) {
            toast(e.message, 9000);
          }
        } }, 'Exportar kit'))),
    titulo('Verificação profunda', 'Recalcula o SHA-256 de cada arquivo (lê todos os GB do modelo — leva minutos).'),
    h('div', { class: 'cartao flat' },
      instal.map(x => h('div', { class: 'acao', style: 'background:none;padding-left:0;padding-right:0' },
        h('div', {},
          h('b', {}, formatarNomeModelo(x.id)),
          h('span', {}, d.integridade?.[x.id]?.ok ? 'arquivos presentes com o tamanho certo' : (d.integridade?.[x.id]?.motivo || ''))),
        h('button', { class: 'btn mini', onclick: async () => {
          try {
            await api('/api/offline/verificar', { modelo: x.id });
            toast('Verificação iniciada.');
            await carregarJobs();
          } catch (e) {
            toast(e.message, 8000);
          }
        } }, 'Verificar')))));
}

