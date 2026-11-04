/* Modo público: a calculadora usa o catálogo estático; chamadas que exigem PC/Ollama são bloqueadas. */
window.LI_PUBLIC_MODE = true;
if (!location.hash) location.hash = '#calculadora';
window.api = async function (path) {
  if (path.startsWith('/api/calc/dados')) return window.LI_DADOS;
  if (path.startsWith('/api/maquinas')) return { remotas: [], parque: [] };
  if (path.startsWith('/api/saude')) return { protocolo: 'estimado', ollama: { no_ar: false, url: 'somente app local' }, gpu: null };
  if (path.startsWith('/api/jobs')) return { jobs: [], externa: null };
  if (path.startsWith('/api/mesa')) return null;
  throw new Error('Este recurso precisa do painel local e do Ollama. Baixe o projeto para usar benchmarks e dados do seu computador.');
};
