// Shared helpers for the Vercel functions that let a deployed copy of the app use the model configured in the
// project's environment variables (LLM_API_KEY, LLM_MODEL, ...) without the key ever reaching the browser.
// Same contract as the local proxy in vite-llm-proxy.js. Files starting with "_" are not routed by Vercel.
import { resolveSettings } from '../src/utils/llmClient.js';

export const settings = () => resolveSettings(process.env);

export function send(res, status, payload) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(payload));
}

/** Refuse browser requests that come from another site, so nobody else's page can spend this key. */
export function sameOrigin(req) {
  const origin = req.headers.origin;
  if (!origin) return true; // same-origin GETs carry no Origin header
  try {
    return new URL(origin).host === req.headers.host;
  } catch {
    return false;
  }
}

// Best-effort limit per visitor (kept in memory, so it resets when the function instance restarts).
const hits = new Map();
const WINDOW_MS = 60 * 60 * 1000;
export const MAX_CALLS_PER_WINDOW = Number(process.env.LLM_MAX_CALLS_PER_HOUR) || 60;

export function allowCall(req, now = Date.now()) {
  const ip = String(req.headers['x-forwarded-for'] || req.socket?.remoteAddress || 'unknown').split(',')[0].trim();
  const recent = (hits.get(ip) || []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= MAX_CALLS_PER_WINDOW) {
    hits.set(ip, recent);
    return false;
  }
  recent.push(now);
  hits.set(ip, recent);
  if (hits.size > 5000) hits.clear(); // never grow without bound
  return true;
}
