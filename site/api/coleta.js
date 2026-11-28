// Intermediário da coleta (função do Vercel). O site e o app chamam /api/coleta; a chave do Supabase fica só no
// servidor, nas variáveis de ambiente do Vercel (SUPABASE_URL e SUPABASE_KEY), nunca no código público.
// Só repassa as duas funções de gravação e o resumo do painel interno (que exige senha no banco); o banco continua validando tudo (o papel anônimo só insere).
const PERMITIDAS = new Set(['registrar_evento', 'enviar_benchmark', 'painel_resumo', 'painel_acao', 'comunidade_resumo']);
const LIMITE_BYTES = 64 * 1024;
// Hosts de produção: o domínio novo (canônico) e o antigo .vercel.app, que as versões já instaladas do app ainda usam.
const HOSTS_PRODUCAO = new Set(['localai4you.com.br', 'www.localai4you.com.br', 'localai4you.vercel.app']);
// Pré-visualizações do Vercel (um endereço novo a cada deploy) são testes: não entram na métrica.
const ehTeste = (host) => typeof host === 'string' && /\.vercel\.app$/i.test(host) && !HOSTS_PRODUCAO.has(host.toLowerCase());
const crypto = require('crypto');
// O banco limita as tentativas de senha do painel por origem. Mandamos um HMAC do IP (com a chave do servidor),
// nunca o IP: não dá para voltar ao endereço, e o mesmo IP dá sempre o mesmo valor. O Vercel preenche x-real-ip.
function origemDoCliente(req, segredo) {
  const ip = String(req.headers['x-real-ip'] || (req.headers['x-forwarded-for'] || '').split(',')[0] || '').trim();
  return ip ? crypto.createHmac('sha256', segredo).update(ip).digest('hex').slice(0, 32) : '?';
}
const FUNCOES_PAINEL = new Set(['painel_resumo', 'painel_acao']);

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');          // o app local roda em http://127.0.0.1
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ message: 'use POST' });

  const url = process.env.SUPABASE_URL, chave = process.env.SUPABASE_KEY;
  if (!url || !chave) return res.status(503).json({ message: 'coleta desligada' });

  let corpo = req.body;
  if (typeof corpo === 'string') { try { corpo = JSON.parse(corpo); } catch (e) { corpo = null; } }
  const fn = corpo && corpo.fn, dados = corpo && corpo.dados;
  if (!PERMITIDAS.has(fn) || !dados || typeof dados !== 'object') return res.status(400).json({ message: 'pedido inválido' });
  if (fn === 'registrar_evento' && ehTeste(dados.p_host)) return res.status(200).setHeader('Content-Type', 'application/json').end('null');   // descartado de propósito
  const texto = JSON.stringify(dados);
  if (texto.length > LIMITE_BYTES) return res.status(413).json({ message: 'grande demais' });

  try {
    const r = await fetch(`${url.replace(/\/$/, '')}/rest/v1/rpc/${fn}`, {
      method: 'POST',
      headers: { apikey: chave, 'Content-Type': 'application/json', 'x-cliente-ip': origemDoCliente(req, chave) },
      body: texto });
    const saida = await r.text();
    // O painel recusa senha devolvendo {"erro": "..."} (exceção desfaria o registro da tentativa): vira 401/429 aqui.
    if (r.ok && FUNCOES_PAINEL.has(fn)) {
      let j = null; try { j = JSON.parse(saida); } catch (e) { /* segue */ }
      if (j && typeof j.erro === 'string') return res.status(/tentativas/i.test(j.erro) ? 429 : 401).json({ message: j.erro });
    }
    res.status(r.status).setHeader('Content-Type', 'application/json');
    return res.end(saida || 'null');
  } catch (e) {
    return res.status(502).json({ message: 'banco indisponível' });
  }
};
