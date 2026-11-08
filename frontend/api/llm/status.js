// GET /api/llm/status -> { configured, provider, model }   (never includes the key)
import { settings, send, sameOrigin } from '../_shared.js';

export default function handler(req, res) {
  if (req.method !== 'GET') return send(res, 405, { error: 'method not allowed' });
  if (!sameOrigin(req)) return send(res, 403, { error: 'Cross-origin requests are not allowed.' });
  const s = settings();
  return send(res, 200, { configured: s.configured, provider: s.provider, model: s.model });
}
