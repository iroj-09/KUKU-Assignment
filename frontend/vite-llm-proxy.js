// Local-only proxy so the React app can use the model configured in the project's .env
// WITHOUT the key ever reaching the browser.
//
//   GET  /api/llm/status    -> { configured, provider, model }      (never includes the key)
//   POST /api/llm/complete  -> { text }   body: { prompt }
//
// It runs inside the Vite dev/preview server on this machine. Safety:
//   - only loopback connections are served (the dev server may listen on the LAN: host: true),
//   - browser requests from another origin are refused (no cross-site use of your key),
//   - .env is re-read on every request, so editing it needs no restart.
// A static deployment has no proxy; there the user enters a key in the "AI Model" dialog instead.

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadEnv } from 'vite';
import { callModel, resolveSettings } from './src/utils/llmClient.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(here, '..'); // the project root holds .env
const LOOPBACK = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i;

function currentSettings() {
  // '' prefix = every variable in .env (plus process.env), not just VITE_*.
  return resolveSettings(loadEnv('development', rootDir, ''));
}

function send(res, status, payload) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(payload));
}

function readBody(req, limit = 2_000_000) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > limit) {
        reject(new Error('request too large'));
        req.destroy();
      } else {
        chunks.push(c);
      }
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function attach(middlewares) {
  middlewares.use('/api/llm', async (req, res) => {
    if (!LOOPBACK.has(req.socket.remoteAddress || '')) {
      return send(res, 403, { error: 'The model proxy only answers requests from this computer.' });
    }
    if (!LOCAL_HOST.test(req.headers.host || '')) {
      return send(res, 403, { error: 'Open the app as http://localhost:<port> to use the model proxy.' });
    }
    const origin = req.headers.origin;
    if (origin) {
      let sameHost = false;
      try {
        sameHost = new URL(origin).host === req.headers.host;
      } catch {
        /* malformed origin */
      }
      if (!sameHost) return send(res, 403, { error: 'Cross-origin requests are not allowed.' });
    }

    const route = (req.url || '').split('?')[0];

    if (req.method === 'GET' && route === '/status') {
      const s = currentSettings();
      return send(res, 200, { configured: s.configured, provider: s.provider, model: s.model });
    }

    if (req.method === 'POST' && route === '/complete') {
      const s = currentSettings();
      if (!s.configured) {
        return send(res, 400, { error: 'No API key in .env. Run: python scripts/setup_model.py', status: 400 });
      }
      try {
        const { prompt } = JSON.parse((await readBody(req)) || '{}');
        if (typeof prompt !== 'string' || !prompt) return send(res, 400, { error: 'prompt is required', status: 400 });
        const text = await callModel({
          provider: s.provider,
          model: s.model,
          apiKey: s.apiKey,
          baseUrl: s.baseUrl,
          prompt,
        });
        return send(res, 200, { text });
      } catch (err) {
        const status = Number.isInteger(err.status) && err.status >= 400 && err.status < 600 ? err.status : 502;
        return send(res, status, { error: err.message || 'model call failed', status });
      }
    }

    return send(res, 404, { error: 'not found' });
  });
}

export default function llmProxy() {
  return {
    name: 'kuku-llm-proxy',
    configureServer(server) {
      attach(server.middlewares);
    },
    configurePreviewServer(server) {
      attach(server.middlewares);
    },
  };
}
