'use strict';
/* Página "Radar": o que existe de novo, o que cabe em cada máquina, e o explorador de quantizações (Ollama + Hugging Face). */

// Links para as páginas do modelo: Ollama E Hugging Face (modelo-base ou, se não achamos, a busca por GGUF).
function linksDoCandidato(c) {
  const L = [];
  if (c.origem === 'ollama' && c.familia) L.push(linkExterno(`https://ollama.com/library/${c.familia}`, 'Ollama'));
  const repo = c.repo || (c.origem === 'hf' ? String(c.id).replace(/^hf:/, '') : null);
  if (repo) L.push(linkExterno(urlHF(repo), 'Hugging Face'));
  else L.push(linkExterno(`https://huggingface.co/models?search=${encodeURIComponent(c.nome + ' gguf')}&sort=downloads`, 'Buscar no Hugging Face'));
  return L.filter(Boolean);
}

async function garantirCalc() {
  if (S.calc && Date.now() - S.calcT < 60000) return S.calc;
  const d = await api('/api/calc/dados');
  if (d.vazio) throw new Error('O radar ainda não rodou: faça a primeira varredura.');
  d._buscarMais = c => api('/api/quants?candidato=' + encodeURIComponent(c.id));
  d._aoTestar = async (c, papelId, pull) => { fecharDialogo(); if (await irParaMaquina(S.filtroRadar.maquina)) abrirTeste(c.id, papelId, pull); };
  d._aoInstalar = async (c, papelId, pull) => { fecharDialogo(); if (await irParaMaquina(S.filtroRadar.maquina)) abrirInstalar(c.id, papelId, pull); };
  d._aoDuelo = (a, b, papelId) => { fecharDialogo(); iniciarDueloRapido(a, b, papelId); };
  d._instalados = () => (S.mesa?.instalados || []).map(x => x.id);
  S.calc = d; S.calcT = Date.now();
  return d;
}

/* Quantizações de UM modelo, calculadas para a máquina escolhida: tabela com tamanho, qualidade, se cabe, contexto máximo e
   velocidade estimada; cache de contexto (f16/q8_0/q4_0); comandos prontos. Consulta o Hugging Face para listar também os GGUF
   dos quantizadores conhecidos (unsloth, bartowski…), que o Ollama baixa com `hf.co/repo:quantização`. */
async function abrirQuants(candId, papelId, maquinaId) {
  let dados;
  try { dados = await garantirCalc(); } catch (e) { toast(e.message, 8000); return; }
  const c = dados.candidatos.find(x => x.id === candId);
  if (!c) { toast('Esse modelo não está no catálogo da última varredura.'); return; }
  const m = (dados.maquinas || []).find(x => x.id === (maquinaId || S.filtroRadar.maquina)) || dados.maquinas[0];
  const maq = { ...m, reserva_vram_gb: dados.reserva_vram_gb ?? 1.3 };
  Calc.configurar(dados.constantes);
  window.LI_DADOS_PAPEIS = dados.papeis;
  LI_CALC_UI.dialogoModelo({ c, maq, op: { kv: dados.kv_cache_ollama || 'q8_0', ctx: null }, papelId: papelId || (c.papeis[0] || 'chat_pt'),
    buscarMais: () => dados._buscarMais(c), aoTestar: pull => dados._aoTestar(c, papelId || c.papeis[0], pull), aoInstalar: pull => dados._aoInstalar(c, papelId || c.papeis[0], pull),
    aoDuelo: maq.local && dados._aoDuelo ? (a, b) => dados._aoDuelo(a, b, papelId || c.papeis[0]) : null,
    instalados: dados._instalados ? dados._instalados() : [], rotuloMaquina: m.nome });
}

// ---------------------------------------------------------------- RADAR
async function pRadar() {
  const raiz = $('#p-radar'), f = S.filtroRadar;
  if (window.LI_PUBLIC_MODE) {
    const dados = await garantirCalc();
    Calc.configurar(dados.constantes);
    let salvo = {}; try { salvo = JSON.parse(localStorage.getItem('li-calculadora-v1') || '{}'); } catch (_) {}
    if (!salvo.modo && !salvo.gpuId && !salvo.cpuId && !salvo.chipId) {
      raiz.replaceChildren(h('div',{class:'pagina-topo'},h('h1',{},'Radar de modelos para o seu hardware'),h('p',{class:'sub'},'O Radar estima quais modelos do catálogo cabem no computador que você configurar. Primeiro informe sua placa de vídeo, memória ou processador.')),
        h('div',{class:'public-empty'},h('div',{class:'public-empty-icon'},'⌁'),h('h2',{},'Ainda falta configurar seu computador'),h('p',{},'A calculadora salva sua configuração neste navegador. Depois volte aqui para ver modelos estimados para sua máquina.'),h('button',{class:'btn primario',onclick:()=>irPara('calculadora')},'Configurar hardware'))); return;
    }
    const perfil=LI_CALC_UI.perfilDe(salvo,dados), reserva=dados.reserva_vram_gb??1.3;
    const ranked=new Map();
    for (const papel of (dados.papeis||[]).filter(p=>!p.sem_nota)) {
      const escolhas=Calc.escolher(dados,perfil,papel,{kv:'q8_0',ctx:null,comunidade:false,antigos:false,offload:false});
      for (const [tipo,item] of [['Mais capaz',escolhas.parrudo],['Melhor equilíbrio',escolhas.equilibrado],['Leve e rápido',escolhas.leve],...(escolhas.alternativas||[]).map(x=>['Alternativa',x])]) {
        if (!item) continue;
        const id=item.c.id, prev=ranked.get(id), score=(item.cap?.valor||0)*100+(item.prio||0)+(tipo==='Melhor equilíbrio'?12:tipo==='Mais capaz'?8:0);
        if (!prev||score>prev.score) ranked.set(id,{c:item.c,enc:item.enc,papel:papel.rotulo,tipo,score});
      }
    }
    const top=[...ranked.values()].sort((a,b)=>b.score-a.score).slice(0,5);
    const card=({c,enc,papel,tipo},i)=>{
      const v=enc.variante, variants=c.variantes||[];
      return h('article',{class:'radar-modelo'},h('div',{class:'radar-modelo-topo'},h('div',{},h('span',{class:'chip'},`ESCOLHA ${i+1} · ${tipo.toUpperCase()}`),h('h2',{},c.nome),h('p',{class:'sub'},`${c.params_b}B parâmetros${c.ativos_b?` · ${c.ativos_b}B ativos`:''} · ${papel}`)),h('div',{class:'radar-fit'},h('b',{},v.quant),h('span',{},`${fmtN(v.bytes/1e9,1)} GB`))),
        h('p',{},c.descricao||'Descrição do modelo não disponível.'),h('div',{class:'radar-tags'},(c.caps||[]).map(x=>h('span',{class:'chip neutro'},x)),c.licenca?h('span',{class:'chip neutro'},`Licença: ${c.licenca}`):null,c.ctx_max?h('span',{class:'chip neutro'},`Contexto declarado: ${fmtCtx(c.ctx_max)}`):null),
        h('p',{class:'sub'},`Estimativa para ${perfil.nome}: ${enc.encaixe?.nivel==='confortavel'?'cabe com folga':'cabe no limite'} · contexto de ${fmtCtx(enc.ctx||8192)}${enc.tps_est?` · ${fmtN(enc.tps_est[0],1)}–${fmtN(enc.tps_est[1],1)} tok/s estimados`:''}.`),
        h('details',{},h('summary',{},`Ver todas as ${variants.length} quantizações e tamanhos`),h('div',{class:'radar-variantes'},variants.map(q=>h('div',{class:'radar-variante'},h('b',{},q.quant),` · ${fmtN(q.bytes/1e9,1)} GB · ${q.pull}`))),h('div',{class:'radar-links'},c.repo?h('a',{href:`https://huggingface.co/${c.repo}`,target:'_blank',rel:'noopener'},'Hugging Face ↗'):null,c.repo_gguf?h('a',{href:`https://huggingface.co/${c.repo_gguf}`,target:'_blank',rel:'noopener'},'GGUF ↗'):null,c.familia?h('a',{href:`https://ollama.com/library/${c.familia}`,target:'_blank',rel:'noopener'},'Ollama ↗'):null)));
    };
    raiz.replaceChildren(h('div',{class:'pagina-topo'},h('h1',{},'Os 5 melhores para '+perfil.nome),h('p',{class:'sub'},`${top.length} recomendações estimadas pelo motor de decisão do app: capacidade, encaixe e equilíbrio. Dados do catálogo ${dados.radar?.slice(0,10)||''}; notas de qualidade não são medidas no site.`),h('button',{class:'btn mini',onclick:()=>irPara('calculadora')},'Ajustar meu hardware')),
      top.length?h('div',{class:'radar-estimado-lista'},top.map(card)):h('div',{class:'public-empty'},h('h2',{},'Não achei modelos que caibam com esses critérios'),h('p',{},'Tente aumentar a memória disponível ou reduzir o contexto na Calculadora.'))); return;
  }
  if (!S.mesa) return;
  const maquinas = (S.calc?.maquinas || []).map(x => x.id);
  const ids = maquinas.length ? maquinas : ['boss', 'aspire5', 'raspberrypi', 'celeron', 'i3'];
  const maqSel = h('select', {}, ids.map(id => h('option', { value: id, selected: id === f.maquina }, id)));
  const papSel = h('select', {}, h('option', { value: '' }, 'Todas as funções'), S.mesa.papeis.map(p => h('option', { value: p.id, selected: p.id === f.papel }, p.rotulo)));
  const cCom = h('input', { type: 'checkbox', checked: f.comunidade }), cAnt = h('input', { type: 'checkbox', checked: f.antigos });
  const capSel = h('select', {}, [['', 'Qualquer'], ['vision', '👁 Visão (imagens)'], ['tools', '🛠 Ferramentas'], ['thinking', '🧠 Raciocínio'], ['audio', '🔊 Áudio']].map(([v, t]) => h('option', { value: v, selected: v === f.cap }, t)));
  const ordSel = h('select', {}, [['prioridade', 'Prioridade de teste'], ['capacidades', 'Mais capacidades declaradas'], ['menor', 'Menor tamanho primeiro'], ['rapido', 'Mais rápido (estimado)'], ['recente', 'Mais recente']].map(([v, t]) => h('option', { value: v, selected: v === f.ordem }, t)));
  const recarregar = () => { f.maquina = maqSel.value; f.papel = papSel.value; f.comunidade = cCom.checked; f.antigos = cAnt.checked; f.cap = capSel.value; f.ordem = ordSel.value; f.pagina = 0; pRadar(); };
  [maqSel, papSel, cCom, cAnt, capSel, ordSel].forEach(e => e.addEventListener('change', recarregar));
  const rd = S.mesa.radar;
  const topo = [
    h('div', { class: 'pagina-topo' }, h('div', { class: 'linha topo' }, h('div', {}, h('h1', {}, 'Radar de modelos'), h('p', { class: 'sub' }, 'Varre a biblioteca do Ollama e os laboratórios no Hugging Face e calcula o que CABE em cada máquina.')),
      h('div', { class: 'linha' }, rd.existe ? h('span', { class: 'sub' }, `Última varredura ${fmtIdade(rd.idade_dias)} · ${rd.total} candidatos`) : null,
        h('button', { class: 'btn primario', onclick: () => varrer(true) }, rd.existe ? 'Varrer de novo' : 'Primeira varredura')))),
    rd.existe ? null : h('div', { class: 'vazio' }, 'O radar ainda não rodou. Clique em “Primeira varredura” (leva ~30 segundos).'),
    (S.mesa.ritmo || []).length ? h('details', { class: 'dica-clean', style: 'margin-bottom:18px' },
      h('summary', {}, '📈 Ritmo de lançamentos das famílias que você usa'),
      h('div', { style: 'margin-top:6px' },
        S.mesa.ritmo.map(r => h('div', { class: 'sub', style: 'margin-top:5px' }, h('b', {}, r.familia), ': ' + r.versoes.map(v => `${v.nome} (${v.lancamento})`).join(' → '),
          r.intervalo_medio_dias ? ` · nova a cada ~${fmtN(r.intervalo_medio_dias / 30, 1)} meses` : ' · 1 versão no radar',
          ` · última há ${r.dias_desde_a_ultima} dias`,
          r.proxima_em_dias != null ? (r.proxima_em_dias > 0 ? ` → próxima em ~${r.proxima_em_dias} dias` : ' → janela aberta p/ lançamento') : '')),
        h('div', { class: 'sub', style: 'margin-top:6px;font-size:.76rem' }, 'Tendência estimada via datas reais de lançamento do Hugging Face.'))) : null,
    h('div', { class: 'filtros' }, h('label', { class: 'campo' }, 'Para a máquina', maqSel), h('label', { class: 'campo' }, 'Função', papSel), h('label', { class: 'campo', title: 'O que o modelo DECLARA aceitar (o Ollama informa por tamanho: o gemma3 270M não enxerga imagens, o 4B sim)' }, 'Declara', capSel), h('label', { class: 'campo' }, 'Ordenar por', ordSel),
      h('label', { class: 'chk' }, cCom, 'incluir ajustes de comunidade'), h('label', { class: 'chk' }, cAnt, 'incluir modelos com mais de 9 meses'))];
  raiz.replaceChildren(...topo, h('div', { id: 'radar-lista' }, h('div', { class: 'sub' }, 'Carregando…')));
  garantirCalc().then(() => { /* só aquece o catálogo para abrir as quantizações sem espera */ }).catch(() => { });
  if (!rd.existe) return;
  try {
    const [r, info] = await Promise.all([api(`/api/radar?maquina=${f.maquina}&papel=${f.papel}&comunidade=${f.comunidade ? 1 : 0}&antigos=${f.antigos ? 1 : 0}&limite=400`), api('/api/radar/info')]);
    S.radarInfo = info;
    const lista = $('#radar-lista');
    if (!lista) return;
    const novos = info.primeira_varredura ? [] : (info.apareceram || []);
    const chaveNovos = (info.desde || '') + '|' + novos.map(x => x.id || x.nome).sort().join(',');
    let jaViuNovos = false;
    try { jaViuNovos = localStorage.getItem('li-radar-novos-vistos') === chaveNovos; } catch (x) {}

    let bannerNovos = null;
    if (info.primeira_varredura) {
      bannerNovos = h('div', { class: 'info-caixa' }, 'Esta varredura é a linha de base. Da próxima vez, aqui aparece tudo que surgiu desde hoje.');
    } else if (novos.length && !jaViuNovos) {
      bannerNovos = h('div', { class: 'aviso-caixa', style: 'display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap' },
        h('div', {},
          h('b', {}, `✨ ${novos.length} modelo(s) novo(s) desde ${(info.desde || '').slice(0, 10)}: `),
          novos.slice(0, 10).map(x => nomeAmigavelModelo(x.nome)).join(', '),
          h('span', { class: 'sub', style: 'margin-left:6px' }, '(destacados com ★ NOVO no feed abaixo)')),
        h('button', {
          class: 'btn mini',
          title: 'Marcar como visto e ocultar esta notificação até a próxima novidade',
          onclick: () => {
            try { localStorage.setItem('li-radar-novos-vistos', chaveNovos); } catch (x) {}
            bannerNovos.remove();
          }
        }, '✓ Já vi (ocultar aviso)'));
    }

    const ordenar = {
      prioridade: (a, b) => b.prioridade.pontos - a.prioridade.pontos,
      capacidades: (a, b) => (b.caps || []).length - (a.caps || []).length || b.prioridade.pontos - a.prioridade.pontos,
      menor: (a, b) => (a.encaixe.variante?.bytes || 0) - (b.encaixe.variante?.bytes || 0),
      rapido: (a, b) => ((b.encaixe.tps_est?.[0] || 0) + (b.encaixe.tps_est?.[1] || 0)) - ((a.encaixe.tps_est?.[0] || 0) + (a.encaixe.tps_est?.[1] || 0)),
      recente: (a, b) => (a.dias ?? 1e9) - (b.dias ?? 1e9)
    }[f.ordem] || ((a, b) => 0);
    const todos = r.candidatos.filter(c => !f.cap || (c.caps || []).includes(f.cap)).sort(ordenar);
    const POR_PAGINA = 12, paginas = Math.max(1, Math.ceil(todos.length / POR_PAGINA));
    f.pagina = Math.min(Math.max(f.pagina || 0, 0), paginas - 1);
    const fatia = todos.slice(f.pagina * POR_PAGINA, (f.pagina + 1) * POR_PAGINA);
    const irPagina = n => { f.pagina = n; pRadar(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
    const nav = () => paginas > 1 ? h('div', { class: 'linha', style: 'justify-content:center;gap:8px;margin:14px 0' },
      h('button', { class: 'btn mini', disabled: f.pagina === 0, onclick: () => irPagina(f.pagina - 1) }, '← Anterior'),
      h('span', { class: 'sub' }, `Página ${f.pagina + 1} de ${paginas} · ${todos.length} modelos`),
      h('button', { class: 'btn mini', disabled: f.pagina >= paginas - 1, onclick: () => irPagina(f.pagina + 1) }, 'Próxima →')) : null;
    lista.replaceChildren(
      bannerNovos,
      titulo(`Melhores opções para ${f.maquina}`, 'Cada cartão mostra a comparação direta com o seu Titular Atual naquela função para você saber na hora se vale a pena testar. Clique no nome para ver o mesmo modelo em outros tamanhos.'),
      fatia.length ? [h('div', { class: 'radar-grid-3' }, fatia.map(cartaoCandidato)), nav()] : h('div', { class: 'vazio' }, 'Nenhum candidato cabe nessa máquina com esses filtros.'));
  } catch (e) { $('#radar-lista')?.replaceChildren(h('div', { class: 'aviso-caixa' }, e.message)); }
}
function classeCorPrio(pr) {
  if (pr >= 75) return 'prio-alta';
  if (pr >= 45) return 'prio-media';
  return 'prio-baixa';
}

function obterModelosDispensados() {
  try { return new Set(JSON.parse(localStorage.getItem('li-modelos-dispensados') || '[]')); } catch (e) { return new Set(); }
}

function alternarDispensarModelo(id) {
  const s = obterModelosDispensados();
  if (s.has(id)) s.delete(id); else s.add(id);
  try { localStorage.setItem('li-modelos-dispensados', JSON.stringify([...s])); } catch (e) {}
}

function diagnosticoValeTestar(c) {
  const m = S.mesa;
  const pr = c.prioridade?.pontos || 0;
  const v = c.encaixe?.variante || {};
  const tpsCand = c.encaixe?.tps_est ? (c.encaixe.tps_est[0] + c.encaixe.tps_est[1]) / 2 : null;
  const bytesCand = v.bytes || 0;
  const pap = papelPorId(c.papel);
  const titId = m?.titulares?.[c.papel];
  const tit = titId ? (m?.instalados || []).find(x => x.id === titId) : null;
  const notaTit = tit?.medido?.papeis?.[c.papel]?.nota;
  const tpsTit = tit?.medido?.tps_mediana;
  const bytesTit = tit?.bytes || 0;
  const nomeTit = tit ? nomeAmigavelModelo(tit.id) : null;

  if (c.instalado_como) {
    return {
      selo: '✔ Já na sua esquadra',
      cor: 'ok',
      resumo: `Instalado como ${nomeAmigavelModelo(c.instalado_como)}. Veja outras quantizações se quiser mais velocidade ou menos VRAM.`,
      titularTxt: nomeTit ? `Titular em ${pap?.rotulo || c.papel}: ${nomeTit}${notaTit != null ? ' (nota ' + fmtN(notaTit, 0) + ')' : ''}` : null
    };
  }

  let selo = '⚖ Opcional';
  let cor = 'neutro';
  let resumo = '';

  const maisRapido = tpsCand && tpsTit && tpsCand >= tpsTit * 1.25;
  const maisLeve = bytesCand && bytesTit && bytesCand <= bytesTit * 0.72;
  const porteSimilarOuMaior = (c.params_b || 0) >= 12 || (bytesCand && bytesTit && bytesCand >= bytesTit * 0.78);

  if (pr >= 75 || (pr >= 62 && (maisRapido || porteSimilarOuMaior))) {
    selo = '🔥 Vale a pena testar';
    cor = 'ok';
    if (maisRapido && tpsTit) {
      resumo = `Promete ~${fmtN(tpsCand / tpsTit, 1)}× mais velocidade que o titular atual com porte competitivo (${c.params_b}B).`;
    } else if (maisLeve) {
      resumo = `Mais enxuto (${fmtGB(bytesCand)} vs ${fmtGB(bytesTit)}) e alta prioridade técnica para desafiar ${nomeTit || 'o titular'}.`;
    } else {
      resumo = `Forte candidato recente (${c.params_b}B) com potencial real de disputar liderança em ${pap?.rotulo || c.papel}.`;
    }
  } else if (maisRapido || maisLeve) {
    selo = '⚡ Alternativa mais leve/rápida';
    cor = 'estimado';
    resumo = `Menor porte que ${nomeTit || 'o titular'}, mas útil se quiser economizar VRAM (${fmtGB(bytesCand)}) ou ganhar velocidade (~${fmtTps(c.encaixe.tps_est)} tok/s).`;
  } else if (pr < 48) {
    selo = '💤 Provavelmente não compensa';
    cor = 'neutro';
    resumo = nomeTit
      ? `Porte/velocidade abaixo do seu titular atual (${nomeTit}${tpsTit ? ', ' + fmtN(tpsTit, 0) + ' tok/s' : ''}).`
      : `Prioridade baixa (${pr}/100) frente às melhores opções da fila.`;
  } else {
    selo = '🔎 Teste secundário';
    cor = 'neutro';
    resumo = nomeTit
      ? `Competitivo no papel, mas ${nomeTit} já entrega barra alta (${notaTit != null ? 'nota ' + fmtN(notaTit, 0) : 'titular'}).`
      : `Candidato intermediário para ${pap?.rotulo || c.papel}.`;
  }

  const titularTxt = nomeTit
    ? `Titular atual (${pap?.rotulo || c.papel}): ${nomeTit} · ${notaTit != null ? 'nota ' + fmtN(notaTit, 0) + ' · ' : ''}${tpsTit ? fmtN(tpsTit, 0) + ' tok/s · ' : ''}${fmtGB(bytesTit)}`
    : null;

  return { selo, cor, resumo, titularTxt };
}

/* Instalar / Testar em todo cartão. O destino é a máquina CONTROLADA; se o cartão é de outra máquina do parque,
   o botão leva o controle para ela primeiro (só vale para máquina registrada: aba Parque → como registrar). */
function maquinaDoCartao() { return S.filtroRadar.maquina; }
function idDoAlvo() { return LI.alvo || S.mesa?.boss?.id || 'boss'; }
async function irParaMaquina(id) {
  if (id === idDoAlvo()) return true;
  const remota = (S.maquinas?.remotas || []).find(m => m.id === id);
  if (id === (S.mesa?.boss?.id || 'boss') && !LI.alvo) return true;
  if (!remota) { toast(`A máquina “${id}” ainda não está registrada para controle (ver cerebro/controle-remoto-do-parque.md).`, 9000); return false; }
  if (!remota.online) { toast(`A máquina “${id}” está desligada ou sem painel: ligue-a e tente de novo.`, 9000); return false; }
  await escolherAlvo(id); return true;
}
function botoesDeAcao(c) {
  const maq = maquinaDoCartao(), fora = maq !== idDoAlvo();
  const rot = fora ? ` em ${maq}` : '';
  if (c.instalado_como) return [h('span', { class: 'chip ok', title: c.instalado_como }, '✔ instalado')];
  return [
    h('button', { class: 'btn mini primario', title: 'Baixa o modelo e roda o benchmark contra o titular', onclick: async () => { if (await irParaMaquina(maq)) abrirTeste(c.id, c.papel); } }, 'Testar' + rot),
    h('button', { class: 'btn mini', title: 'Só baixa o modelo (sem medir)', onclick: async () => { if (await irParaMaquina(maq)) abrirInstalar(c.id, c.papel); } }, 'Instalar' + rot)];
}

const CAP_ROTULO = { vision: ['👁 imagens', 'declara aceitar imagens'], tools: ['🛠 ferramentas', 'declara chamada de ferramentas'], thinking: ['🧠 raciocínio', 'declara modo de raciocínio'], audio: ['🔊 áudio', 'declara aceitar áudio'], decision: ['⚖ decisão, não conversa', 'Modelo de decisão/classificação: responde perguntas tipadas (sim/não, escolha, nota) numa passada, sem gerar texto. Não roda no Ollama e não entra nas notas de conversa; precisa do llama-server do llama.cpp (/v1/systemone).'] };
const capsDeclaradas = c => (c.caps || []).filter(k => CAP_ROTULO[k]).map(k => chip(CAP_ROTULO[k][0], 'estimado', CAP_ROTULO[k][1]));

/* Todos os tamanhos da mesma família (catálogo completo, sem o corte de 9 meses), já calculados para a máquina escolhida. */
async function abrirFamilia(c) {
  let dados;
  try { dados = await garantirCalc(); } catch (e) { toast(e.message, 8000); return; }
  const m = (dados.maquinas || []).find(x => x.id === S.filtroRadar.maquina) || dados.maquinas[0];
  const maq = { ...m, reserva_vram_gb: dados.reserva_vram_gb ?? 1.3 };
  Calc.configurar(dados.constantes);
  const cfg = { reserva_vram_gb: maq.reserva_vram_gb, kv_cache: dados.kv_cache_ollama || 'q8_0' };
  const papelId = c.papel || (c.papeis && c.papeis[0]) || 'chat_pt';
  const papel = (dados.papeis || []).find(p => p.id === papelId) || (dados.papeis || [])[0];
  const familia = c.familia || c.nome.split(' ')[0];
  const irmaos = dados.candidatos.filter(x => x.origem === c.origem && (x.familia || x.nome.split(' ')[0]) === familia).sort((a, b) => a.params_b - b.params_b);
  const instalados = new Set(dados._instalados ? dados._instalados() : []);
  const linhas = irmaos.map(x => {
    const enc = Calc.encaixeCandidato(x, maq, papel, cfg);
    const v = enc?.variante;
    const tps = enc?.tps_est;
    const ja = (x.variantes || []).some(vv => instalados.has(vv.pull));
    return h('tr', { class: x.id === c.id ? 'destaque' : '' },
      h('td', {}, h('b', {}, x.tamanho ? x.tamanho.toUpperCase() : `${x.params_b}B`), x.id === c.id ? h('div', { class: 'sub' }, 'o que você abriu') : null),
      h('td', {}, h('div', { class: 'chips' }, ...capsDeclaradas(x), (x.caps || []).length ? null : h('span', { class: 'sub' }, 'só texto'))),
      h('td', { class: 'sub' }, `${fmtIdade(x.dias)}`, x.dias > 270 ? ' ' : '', x.dias > 270 ? chip('antigo', 'neutro') : null),
      h('td', { class: 'num' }, v ? `${fmtGB(v.bytes)} (${v.quant})` : '—'),
      h('td', {}, enc?.cabe ? chip('cabe · ctx ' + fmtCtx(enc.encaixe.ctx_max), 'ok') : chip('não cabe', 'bad', enc?.motivo || '')),
      h('td', { class: 'num' }, tps ? `~${fmtTps(tps)} tok/s` : '—'),
      h('td', {}, h('div', { class: 'linha', style: 'gap:4px;flex-wrap:nowrap;justify-content:flex-end' },
        ja ? chip('✔ instalado', 'ok') : [
          h('button', { class: 'btn mini primario', onclick: () => dados._aoTestar(x, papelId) }, 'Testar'),
          h('button', { class: 'btn mini', onclick: () => dados._aoInstalar(x, papelId) }, 'Instalar')],
        h('button', { class: 'btn mini', onclick: () => { fecharDialogo(); abrirQuants(x.id, papelId); } }, 'Quants'))));
  });
  abrirDialogo(h('div', { class: 'dlg-in', style: 'max-width:980px' },
    h('h2', {}, 'Família ' + familia), h('p', { class: 'sub' }, `Todos os tamanhos que o radar conhece, calculados para ${m.nome || m.id} (o corte de 9 meses não vale aqui).`),
    irmaos.length > 1 ? h('div', { class: 'tabela-wrap' }, h('table', { class: 'tabela-compacta' },
      h('thead', {}, h('tr', {}, ['Tamanho', 'Declara', 'Lançado', 'Menor que cabe', 'Cabe?', 'Velocidade', ''].map(t => h('th', {}, t)))), h('tbody', {}, linhas)))
      : h('div', { class: 'vazio' }, 'O radar só conhece este tamanho dessa família.'),
    h('div', { class: 'dlg-acoes' }, h('button', { class: 'btn', onclick: fecharDialogo }, 'Fechar'))));
}

function cartaoCandidato(c) {
  const v = c.encaixe.variante, e = c.encaixe.encaixe, pr = c.prioridade.pontos;
  const pap = papelPorId(c.papel);
  const tagInstalada = c.instalado_como ? c.instalado_como.split(':').pop() : null;
  const nomeL = nomeAmigavelModelo(c.nome);
  const dispensados = obterModelosDispensados();
  const ehDispensado = dispensados.has(c.id) || dispensados.has(c.nome);
  const diag = diagnosticoValeTestar(c);

  return h('div', { class: 'cartao empilha radar-card' + (c.novo ? ' radar-card-novo' : '') + (ehDispensado ? ' dispensado' : ''), style: 'gap:10px' },
    h('div', { class: 'linha topo' },
      h('div', { class: 'quebra grow' },
        h('h3', { style: 'font-size:1.05rem;margin:0;display:flex;align-items:center;gap:6px;flex-wrap:wrap' },
          h('a', { href: '#', class: 'nome-familia', title: 'Ver este modelo em outros tamanhos (inclusive os mais antigos)', style: 'color:inherit;text-decoration:underline dotted', onclick: ev => { ev.preventDefault(); abrirFamilia(c); } }, nomeL),
          c.novo ? chip('★ NOVO NA VARREDURA', 'novo-destaque') : null,
          ehDispensado ? chip('dispensado', 'neutro') : null,
          c.instalado_como ? chip('instalado: ' + tagInstalada, 'neutro', c.instalado_como) : null),
        h('div', { class: 'sub', style: 'font-size:.78rem;margin-top:3px' }, `${c.origem === 'ollama' ? 'Ollama' : 'Hugging Face'} · lançado ${fmtIdade(c.dias)}`)),
      h('span', { class: 'prio-badge ' + classeCorPrio(pr), title: c.prioridade.razoes.join('\n') }, `${pr}/100`)),
    h('div', { class: 'chips' },
      chip(diag.selo, diag.cor),
      chip(`${c.params_b}B${c.ativos_b ? ' (' + c.ativos_b + 'B)' : ''}`, 'neutro'),
      pap ? chip(pap.icone + ' ' + pap.rotulo, 'neutro') : null,
      ...capsDeclaradas(c),
      c.confianca === 'comunidade' ? chip('comunidade', 'neutro') : null),
    h('div', { class: 'radar-vs-titular' },
      h('div', { class: 'radar-vs-veredito' }, diag.resumo),
      diag.titularTxt ? h('div', { class: 'radar-vs-base' }, '👑 ', diag.titularTxt) : null),
    h('div', { class: 'linha', style: 'justify-content:flex-start;gap:8px;flex-wrap:wrap;margin:2px 0' },
      h('span', { class: 'metrica-grifada' }, 'Tamanho: ', h('b', {}, fmtGB(v.bytes)), ` (${v.quant})`),
      h('span', { class: 'metrica-grifada' }, 'Contexto: ', h('b', {}, fmtCtx(e.ctx_max))),
      c.encaixe.tps_est ? h('span', { class: 'metrica-grifada' }, 'Velocidade: ', h('b', {}, `~${fmtTps(c.encaixe.tps_est)} tok/s`)) : null,
      h('span', { class: 'sub' }, 'Folga: ', h('b', {}, `${fmtN(e.folga_gb, 1)} GB`))),
    c.prioridade?.razoes?.length ? h('div', { class: 'sub', style: 'font-size:.77rem;margin:0' }, '💡 ' + c.prioridade.razoes.slice(0, 2).join(' · ')) : null,
    cmd('ollama pull ' + v.pull),
    h('div', { class: 'linha', style: 'justify-content:space-between;gap:6px;padding-top:4px' },
      h('div', { class: 'linha', style: 'gap:6px' },
        h('button', { class: 'btn mini' + (c.instalado_como ? ' primario' : ''), onclick: () => abrirQuants(c.id, c.papel) }, c.instalado_como ? 'Outras quantizações' : 'Quantizações'),
        h('button', { class: 'btn mini', title: 'O mesmo modelo em outros tamanhos (1B, 4B, 12B…), mesmo os mais antigos', onclick: () => abrirFamilia(c) }, 'Outros tamanhos'),
        ...botoesDeAcao(c),
        ...linksDoCandidato(c).slice(0, 1)),
      h('button', {
        class: 'btn mini fantasma',
        style: 'font-size:.76rem;color:var(--muted)',
        title: ehDispensado ? 'Reativar recomendação deste modelo' : 'Dispensar este modelo (deixar acinzentado)',
        onclick: () => { alternarDispensarModelo(c.id); pRadar(); }
      }, ehDispensado ? '↩ Reativar' : '✕ Dispensar')));
}
