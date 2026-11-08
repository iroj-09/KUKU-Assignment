// Provider-agnostic model client. Give it a model name and an API key and it works.
//
// Same idea (and the same detection rules) as src/llm.py in the Python pipeline:
//   key prefix   AIza.. gemini | sk-ant-.. anthropic | sk-or-.. openrouter | hf_.. huggingface | gsk_.. groq | sk-.. openai
//   model name   gemini-* | claude-* | gpt-*, o1/o3/o4* | "org/model" (Hugging Face)
// A custom base URL means "any OpenAI-compatible server" (Ollama, vLLM, ...).
//
// This file has no browser-only code, so the local dev proxy (vite-llm-proxy.js) reuses it in Node.

export const OPENAI_COMPATIBLE = {
  openai: 'https://api.openai.com/v1',
  huggingface: 'https://router.huggingface.co/v1',
  openrouter: 'https://openrouter.ai/api/v1',
  groq: 'https://api.groq.com/openai/v1',
  together: 'https://api.together.xyz/v1',
  ollama: 'http://localhost:11434/v1',
};

export const DEFAULT_MODELS = {
  gemini: 'gemini-3.5-flash-lite',
  anthropic: 'claude-haiku-4-5',
  openai: 'gpt-4o-mini',
  huggingface: 'meta-llama/Llama-3.1-8B-Instruct',
  openrouter: 'openai/gpt-4o-mini',
  groq: 'llama-3.3-70b-versatile',
  together: 'meta-llama/Llama-3.3-70B-Instruct-Turbo',
  ollama: 'llama3.1',
};

export const PROVIDERS = Object.keys(DEFAULT_MODELS);

export const PROVIDER_LABELS = {
  gemini: 'Google Gemini',
  anthropic: 'Anthropic Claude',
  openai: 'OpenAI',
  huggingface: 'Hugging Face',
  openrouter: 'OpenRouter',
  groq: 'Groq',
  together: 'Together AI',
  ollama: 'Ollama (local)',
};

// Environment variables that may hold each vendor's key (used by the server-side proxy).
export const KEY_ENV = {
  gemini: ['GEMINI_API_KEY', 'GOOGLE_API_KEY'],
  anthropic: ['ANTHROPIC_API_KEY'],
  openai: ['OPENAI_API_KEY'],
  huggingface: ['HF_TOKEN', 'HUGGINGFACE_API_KEY', 'HUGGINGFACEHUB_API_TOKEN'],
  openrouter: ['OPENROUTER_API_KEY'],
  groq: ['GROQ_API_KEY'],
  together: ['TOGETHER_API_KEY'],
  ollama: [],
};

const ALIASES = {
  'openai-compatible': 'openai',
  hf: 'huggingface',
  'hugging-face': 'huggingface',
  google: 'gemini',
  claude: 'anthropic',
};

export function providerFromKey(key = '') {
  const k = key.trim();
  if (k.startsWith('AIza')) return 'gemini';
  if (k.startsWith('sk-ant-')) return 'anthropic';
  if (k.startsWith('sk-or-')) return 'openrouter';
  if (k.startsWith('hf_')) return 'huggingface';
  if (k.startsWith('gsk_')) return 'groq';
  if (k.startsWith('sk-')) return 'openai';
  return null;
}

export function providerFromModel(model = '') {
  const m = model.trim().toLowerCase();
  if (m.startsWith('gemini') || m.startsWith('models/gemini')) return 'gemini';
  if (m.startsWith('claude')) return 'anthropic';
  if (/^(gpt-|chatgpt|o1|o3|o4)/.test(m)) return 'openai';
  if (m.includes('/')) return 'huggingface';
  return null;
}

export function detectProvider({ provider = '', model = '', apiKey = '', baseUrl = '' } = {}) {
  const explicit = ALIASES[provider.trim().toLowerCase()] || provider.trim().toLowerCase();
  if (explicit) {
    if (!PROVIDERS.includes(explicit)) throw new Error(`Unknown provider '${provider}'. Use one of: ${PROVIDERS.join(', ')}.`);
    return explicit;
  }
  if (baseUrl) return 'openai';
  return providerFromKey(apiKey) || providerFromModel(model) || 'gemini';
}

/**
 * Server-side settings from environment variables (mirror of settings() in src/llm.py).
 * `env` is a plain object, e.g. the parsed .env merged with process.env.
 */
export function resolveSettings(env = {}) {
  const get = (k) => String(env[k] || '').trim();
  const baseUrlEnv = get('LLM_BASE_URL');
  const modelEnv = get('LLM_MODEL');
  const genericKey = get('LLM_API_KEY');
  const legacyModel = get('GEMINI_MODEL');

  let provider = get('LLM_PROVIDER');
  if (provider) {
    provider = detectProvider({ provider });
  } else if (baseUrlEnv) {
    provider = 'openai';
  } else {
    provider =
      providerFromKey(genericKey) ||
      providerFromModel(modelEnv || legacyModel) ||
      PROVIDERS.find((p) => KEY_ENV[p].some((n) => get(n))) ||
      'gemini';
  }

  const apiKey = genericKey || KEY_ENV[provider].map(get).find(Boolean) || '';
  const model = modelEnv || (provider === 'gemini' ? legacyModel : '') || DEFAULT_MODELS[provider];
  const baseUrl = baseUrlEnv || OPENAI_COMPATIBLE[provider] || '';
  const configured = Boolean(apiKey) || provider === 'ollama' || Boolean(baseUrlEnv);
  return { provider, model, apiKey, baseUrl, configured };
}

export class LLMError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'LLMError';
    this.status = status;
  }
}

async function postJson(url, headers, body, signal) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    let message = `HTTP ${response.status}${response.statusText ? ': ' + response.statusText : ''}`;
    try {
      const json = JSON.parse(text);
      const m = json.error?.message || json.message || (typeof json.error === 'string' ? json.error : '');
      if (m) message = m;
    } catch {
      if (text) message = `${message} ${text.slice(0, 200)}`;
    }
    throw new LLMError(message, response.status);
  }
  return response.json();
}

async function callGemini({ model, apiKey, prompt, signal }) {
  const name = model.replace(/^models\//, '');
  const data = await postJson(
    `https://generativelanguage.googleapis.com/v1beta/models/${name}:generateContent`,
    { 'x-goog-api-key': apiKey },
    {
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { responseMimeType: 'application/json', temperature: 0.2 },
    },
    signal
  );
  return data.candidates?.[0]?.content?.parts?.[0]?.text || '';
}

async function callAnthropic({ model, apiKey, prompt, signal }) {
  const data = await postJson(
    'https://api.anthropic.com/v1/messages',
    {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      // Lets a browser call the API directly with the user's own key.
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    { model, max_tokens: 8000, temperature: 0.2, messages: [{ role: 'user', content: prompt }] },
    signal
  );
  return (data.content || []).map((b) => b.text || '').join('');
}

async function callOpenAICompatible({ provider, model, apiKey, baseUrl, prompt, signal }) {
  const base = (baseUrl || OPENAI_COMPATIBLE[provider] || OPENAI_COMPATIBLE.openai).replace(/\/+$/, '');
  const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  const body = {
    model,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.2,
    response_format: { type: 'json_object' },
  };
  let data;
  try {
    data = await postJson(`${base}/chat/completions`, headers, body, signal);
  } catch (err) {
    // Some hosted open models reject JSON mode; the prompt already demands JSON, so retry plainly.
    if ([400, 422].includes(err.status) && /response_format/.test(err.message)) {
      delete body.response_format;
      data = await postJson(`${base}/chat/completions`, headers, body, signal);
    } else {
      throw err;
    }
  }
  return data.choices?.[0]?.message?.content || '';
}

/** Send `prompt` to the model and return its raw text (expected to be JSON). */
export async function callModel({ provider, model, apiKey = '', baseUrl = '', prompt, signal }) {
  const p = detectProvider({ provider, model, apiKey, baseUrl });
  const name = model || DEFAULT_MODELS[p];
  try {
    if (p === 'gemini') return await callGemini({ model: name, apiKey, prompt, signal });
    if (p === 'anthropic') return await callAnthropic({ model: name, apiKey, prompt, signal });
    return await callOpenAICompatible({ provider: p, model: name, apiKey, baseUrl, prompt, signal });
  } catch (err) {
    if (err instanceof LLMError) err.message = `${PROVIDER_LABELS[p]} error: ${err.message}`;
    throw err;
  }
}

/** Parse JSON that a model may have wrapped in markdown fences or surrounded with prose. */
export function parseJsonLoose(text) {
  let t = String(text || '').trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  const m = t.match(/\{[\s\S]*\}/);
  if (m) t = m[0];
  return JSON.parse(t.replace(/,\s*([\]}])/g, '$1'));
}
