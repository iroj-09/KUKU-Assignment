// POST /api/llm/complete  body: { prompt }  -> { text }
// Uses the model and key from the deployment's environment variables. The model is fixed by the server (the
// visitor cannot pick another), prompts are size-capped and calls are limited per visitor.
import { callModel } from '../../src/utils/llmClient.js';
import { settings, send, sameOrigin, allowCall } from '../_shared.js';

const MAX_PROMPT_CHARS = 60_000;

export default async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { error: 'method not allowed' });
  if (!sameOrigin(req)) return send(res, 403, { error: 'Cross-origin requests are not allowed.' });

  const s = settings();
  if (!s.configured) {
    return send(res, 400, { error: 'No API key is set on this deployment. Open "AI Model" and enter your own.', status: 400 });
  }
  if (!allowCall(req)) {
    return send(res, 429, { error: 'Too many AI calls from this connection. Try again later or use your own key.', status: 429 });
  }

  // Vercel parses JSON bodies; accept a raw string too.
  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch {
      body = null;
    }
  }
  const prompt = body?.prompt;
  if (typeof prompt !== 'string' || !prompt) return send(res, 400, { error: 'prompt is required', status: 400 });
  if (prompt.length > MAX_PROMPT_CHARS) return send(res, 413, { error: 'prompt is too long', status: 413 });

  try {
    const text = await callModel({ provider: s.provider, model: s.model, apiKey: s.apiKey, baseUrl: s.baseUrl, prompt });
    return send(res, 200, { text });
  } catch (err) {
    const status = Number.isInteger(err.status) && err.status >= 400 && err.status < 600 ? err.status : 502;
    return send(res, status, { error: err.message || 'model call failed', status });
  }
}
