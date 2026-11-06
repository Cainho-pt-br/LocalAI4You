// Intermediário da coleta (função do Vercel). O site e o app chamam /api/coleta; a chave do Supabase fica só no
// servidor, nas variáveis de ambiente do Vercel (SUPABASE_URL e SUPABASE_KEY), nunca no código público.
// Só repassa as duas funções de gravação e o resumo do painel interno (que exige senha no banco); o banco continua validando tudo (o papel anônimo só insere).
const PERMITIDAS = new Set(['registrar_evento', 'enviar_benchmark', 'painel_resumo']);
const LIMITE_BYTES = 64 * 1024;

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
  const texto = JSON.stringify(dados);
  if (texto.length > LIMITE_BYTES) return res.status(413).json({ message: 'grande demais' });

  try {
    const r = await fetch(`${url.replace(/\/$/, '')}/rest/v1/rpc/${fn}`, {
      method: 'POST', headers: { apikey: chave, 'Content-Type': 'application/json' }, body: texto });
    const saida = await r.text();
    res.status(r.status).setHeader('Content-Type', 'application/json');
    return res.end(saida || 'null');
  } catch (e) {
    return res.status(502).json({ message: 'banco indisponível' });
  }
};
