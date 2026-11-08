// Browser-side editorial evaluator. Works with ANY model: Gemini, OpenAI, Claude, Hugging Face,
// OpenRouter, Groq, Ollama, ... (see llmClient.js). The file keeps its old name for compatibility.
import { HOOK_WINDOW_SECONDS, CLIFFHANGER_WINDOW_SECONDS } from './clientParser';
import { callModel, detectProvider, parseJsonLoose, DEFAULT_MODELS } from './llmClient';

// ---------------------------------------------------------------------------
// Which model is used?
//   1. a key the user typed into the "AI Model" dialog (kept in this browser's localStorage), else
//   2. the model configured in the project's .env, reached through the local dev proxy
//      (the key itself never reaches the browser; see vite-llm-proxy.js).
// Never read a key from a VITE_* variable: Vite inlines those into the public bundle.
// The localStorage names keep their old "gemini" prefix so earlier saved settings still work.
// ---------------------------------------------------------------------------
export const STORAGE = {
  apiKey: 'kuku_gemini_api_key',
  model: 'kuku_gemini_model',
  baseUrl: 'kuku_llm_base_url',
  provider: 'kuku_llm_provider',
};

function read(name) {
  try {
    return localStorage.getItem(name) || '';
  } catch {
    return '';
  }
}

let serverStatus = null; // { configured, provider, model } from /api/llm/status, or null

export async function loadServerStatus() {
  try {
    const res = await fetch('/api/llm/status', { cache: 'no-store' });
    serverStatus = res.ok ? await res.json() : null;
  } catch {
    serverStatus = null; // static deployment: no proxy
  }
  return serverStatus;
}

export function getServerStatus() {
  return serverStatus;
}

export function getActiveApiKey() {
  return read(STORAGE.apiKey);
}

export function getActiveModel() {
  return read(STORAGE.model) || serverStatus?.model || import.meta.env.VITE_GEMINI_MODEL || DEFAULT_MODELS.gemini;
}

/** The connection to use right now: { mode: 'direct' | 'proxy', provider, model, ... } or null. */
export function getLlmConfig() {
  const apiKey = read(STORAGE.apiKey);
  const baseUrl = read(STORAGE.baseUrl);
  if (apiKey || baseUrl) {
    const model = read(STORAGE.model) || DEFAULT_MODELS[detectProvider({ provider: read(STORAGE.provider), apiKey, baseUrl })];
    return {
      mode: 'direct',
      provider: detectProvider({ provider: read(STORAGE.provider), model, apiKey, baseUrl }),
      model,
      apiKey,
      baseUrl,
    };
  }
  if (serverStatus?.configured) {
    return { mode: 'proxy', provider: serverStatus.provider, model: serverStatus.model };
  }
  return null;
}

export function isModelConfigured() {
  return getLlmConfig() !== null;
}

export function describeModel(config = getLlmConfig()) {
  return config ? `${config.provider}:${config.model}` : '';
}

/** Accepts a ready config object, a bare API key string (+ optional model), or nothing. */
function normalizeConfig(arg, model) {
  if (arg && typeof arg === 'object') return arg;
  if (typeof arg === 'string' && arg) {
    const name = model || getActiveModel();
    return { mode: 'direct', provider: detectProvider({ model: name, apiKey: arg }), model: name, apiKey: arg, baseUrl: '' };
  }
  return getLlmConfig();
}

/** Send a prompt through whichever connection is active and return the model's raw text. */
export async function completeJson(prompt, config = getLlmConfig(), signal) {
  if (!config) {
    throw new Error(
      'No AI model is connected. Click "AI Model" in the top bar and enter a model name and your API key.'
    );
  }
  if (config.mode === 'proxy') {
    const res = await fetch('/api/llm/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
      signal,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(`AI error: ${body.error || `HTTP ${res.status}`}`);
      err.status = body.status || res.status;
      throw err;
    }
    return body.text || '';
  }
  return callModel({ ...config, prompt, signal });
}

export async function evaluateCandidateWithGemini(candidate, apiKeyOrConfig, model) {
  const config = normalizeConfig(apiKeyOrConfig, model);

  const prompt = `You are a professional short-form vertical-drama promo editor.
Evaluate this microdrama screenplay clip using ONLY its transcript and timestamps.
Do not invent dialogue, actions, motives, or relationships.

EPISODE: ${candidate.episode}
CLIP BOUNDS: ${candidate.clipStart}s to ${candidate.clipEnd}s (Duration: ${candidate.duration}s)

FULL TRANSCRIPT:
${candidate.fullTranscript}

CRITICAL EVIDENCE RULES:
1. The hook must occur strictly within the opening ${HOOK_WINDOW_SECONDS} seconds (${candidate.clipStart}s to ${Math.min(candidate.clipStart + HOOK_WINDOW_SECONDS, candidate.clipEnd)}s).
2. The cliffhanger must occur strictly within the final ${CLIFFHANGER_WINDOW_SECONDS} seconds (${Math.max(candidate.clipStart, candidate.clipEnd - CLIFFHANGER_WINDOW_SECONDS)}s to ${candidate.clipEnd}s).
3. The ending must remain unresolved without giving away the story outcome.
4. If there is no real hook or cliffhanger, score that dimension low.

Return ONLY a valid JSON object in this exact schema:
{
  "is_promising": true,
  "hook": "exact opening dialogue or concise action description in first ${HOOK_WINDOW_SECONDS}s",
  "hook_timestamp": ${candidate.clipStart},
  "cliffhanger": "exact closing dialogue or action in final ${CLIFFHANGER_WINDOW_SECONDS}s",
  "cliffhanger_timestamp": ${candidate.clipEnd},
  "why_it_works": "concise sentence explaining why this hooks short-form mobile viewers",
  "standalone_context": "minimum context a new viewer needs to follow this conflict",
  "hook_score": 8,
  "cliffhanger_score": 9,
  "emotional_score": 8,
  "standalone_score": 7,
  "progression_score": 8,
  "risks": []
}`;

  const rawText = await completeJson(prompt, config);

  let data;
  try {
    data = parseJsonLoose(rawText || '{}');
  } catch {
    throw new Error(`Failed to parse the model's response as JSON: ${String(rawText).slice(0, 100)}...`);
  }

  // Validate and clamp dimension scores (1 to 10)
  const hookScore = Math.max(1, Math.min(10, Math.round(Number(data.hook_score) || 5)));
  const cliffScore = Math.max(1, Math.min(10, Math.round(Number(data.cliffhanger_score) || 5)));
  const emoScore = Math.max(1, Math.min(10, Math.round(Number(data.emotional_score) || 5)));
  const standaloneScore = Math.max(1, Math.min(10, Math.round(Number(data.standalone_score) || 5)));
  const progScore = Math.max(1, Math.min(10, Math.round(Number(data.progression_score) || 5)));

  // Model's weighted final score (0 - 100 scale)
  const geminiScore = Number((
    (0.25 * hookScore + 0.25 * cliffScore + 0.20 * emoScore + 0.15 * standaloneScore + 0.15 * progScore) * 10
  ).toFixed(1));

  // Compute Hybrid Score: 70% model editorial + 30% local heuristic
  const localScore = Number(candidate.localScore || geminiScore);
  const hybridScore = Number((0.70 * geminiScore + 0.30 * localScore).toFixed(2));

  // Check timestamp compliance
  const hTs = typeof data.hook_timestamp === 'number' ? data.hook_timestamp : candidate.clipStart;
  const cTs = typeof data.cliffhanger_timestamp === 'number' ? data.cliffhanger_timestamp : candidate.clipEnd;

  // Same strict windows as the Python pipeline (root config.py).
  const hookValid =
    hTs >= candidate.clipStart &&
    hTs <= Math.min(candidate.clipStart + HOOK_WINDOW_SECONDS, candidate.clipEnd);
  const cliffValid =
    cTs >= Math.max(candidate.clipStart, candidate.clipEnd - CLIFFHANGER_WINDOW_SECONDS) &&
    cTs <= candidate.clipEnd;

  let compliance = 'FAIL';
  if (hookValid && cliffValid) compliance = 'PASS';
  else if (hookValid || cliffValid) compliance = 'PARTIAL';

  return {
    ...candidate,
    geminiScore,
    hybridScore,
    compliance,
    isPromising: Boolean(data.is_promising),
    hook: data.hook || candidate.hook,
    hookTimestamp: hTs,
    cliffhanger: data.cliffhanger || candidate.cliffhanger,
    cliffhangerTimestamp: cTs,
    whyItWorks: data.why_it_works || candidate.whyItWorks,
    standaloneContext: data.standalone_context || candidate.standaloneContext,
    risks: Array.isArray(data.risks) && data.risks.length > 0 ? data.risks : candidate.risks || [],
    hookScore,
    cliffhangerScore: cliffScore,
    emotionalScore: emoScore,
    standaloneScore,
    progressionScore: progScore,
    geminiEvaluated: true,
    llmModel: describeModel(config),
  };
}

export async function evaluateBatchWithGemini(
  candidates,
  apiKeyOrConfig,
  model,
  onProgress = null,
  signal = null
) {
  const config = normalizeConfig(apiKeyOrConfig, model);
  const evaluated = [];
  let failed = 0;
  let abortReason = null;
  let cancelled = false;
  // These statuses mean every remaining call would fail too (bad key, bad model, quota).
  const FATAL_STATUSES = [400, 401, 403, 404, 429];
  for (let i = 0; i < candidates.length; i++) {
    const cand = candidates[i];
    if (signal?.aborted) {
      cancelled = true;
      // Keep everything not yet evaluated unchanged.
      evaluated.push(...candidates.slice(i));
      break;
    }
    if (onProgress) {
      onProgress(i + 1, candidates.length, cand);
    }
    try {
      const updated = await evaluateCandidateWithGemini(cand, config);
      evaluated.push(updated);
    } catch (err) {
      console.warn(`AI evaluation failed for ${cand.id}:`, err);
      failed += 1;
      evaluated.push(cand);
      if (FATAL_STATUSES.includes(err.status) || !config) {
        abortReason = err.message;
        // Keep the remaining candidates unchanged and stop calling the API.
        evaluated.push(...candidates.slice(i + 1));
        break;
      }
    }
    // Rate limit delay (1.2s between calls)
    if (i + 1 < candidates.length) {
      await new Promise((r) => setTimeout(r, 1200));
    }
  }

  // Re-sort and re-rank
  evaluated.sort((a, b) => b.hybridScore - a.hybridScore);
  return {
    candidates: evaluated.map((c, idx) => ({ ...c, rank: idx + 1 })),
    evaluatedCount: evaluated.filter((c) => c.geminiEvaluated).length,
    failed,
    abortReason,
    cancelled,
  };
}
