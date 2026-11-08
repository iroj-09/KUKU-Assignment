import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  detectProvider,
  resolveSettings,
  callModel,
  parseJsonLoose,
  LLMError,
} from './llmClient';

afterEach(() => vi.unstubAllGlobals());

// Same table as tests/test_llm.py: the browser and the Python pipeline must agree.
describe('provider detection (matches src/llm.py)', () => {
  it.each([
    ['gemini-3.5-flash-lite', 'AIzaSyEXAMPLE', 'gemini'],
    ['gpt-4o-mini', 'sk-proj-abc', 'openai'],
    ['claude-haiku-4-5', 'sk-ant-abc', 'anthropic'],
    ['meta-llama/Llama-3.1-8B-Instruct', 'hf_abc', 'huggingface'],
    ['meta-llama/Llama-3.1-8B-Instruct', '', 'huggingface'],
    ['openai/gpt-4o-mini', 'sk-or-abc', 'openrouter'], // key prefix beats the model name
    ['llama-3.3-70b-versatile', 'gsk_abc', 'groq'],
    ['o3-mini', '', 'openai'],
    ['something-unknown', '', 'gemini'],
  ])('%s + %s -> %s', (model, apiKey, expected) => {
    expect(detectProvider({ model, apiKey })).toBe(expected);
  });

  it('a custom base URL means an OpenAI-compatible server; explicit provider wins; aliases work', () => {
    expect(detectProvider({ model: 'my-model', baseUrl: 'http://localhost:9/v1' })).toBe('openai');
    expect(detectProvider({ provider: 'groq', model: 'gpt-4o' })).toBe('groq');
    expect(detectProvider({ provider: 'hf' })).toBe('huggingface');
    expect(() => detectProvider({ provider: 'nope' })).toThrow(/Unknown provider/);
  });
});

describe('resolveSettings (server side, mirrors settings() in src/llm.py)', () => {
  it('the original GEMINI_API_KEY + GEMINI_MODEL setup still works', () => {
    const s = resolveSettings({ GEMINI_API_KEY: 'AIzaOLD', GEMINI_MODEL: 'gemini-old' });
    expect(s).toMatchObject({ provider: 'gemini', model: 'gemini-old', apiKey: 'AIzaOLD', configured: true });
  });

  it('two generic variables are enough for any vendor, and take over from the old ones', () => {
    const hf = resolveSettings({ LLM_MODEL: 'meta-llama/Llama-3.1-8B-Instruct', LLM_API_KEY: 'hf_secret' });
    expect(hf).toMatchObject({ provider: 'huggingface', apiKey: 'hf_secret', baseUrl: 'https://router.huggingface.co/v1' });
    const both = resolveSettings({ GEMINI_API_KEY: 'AIzaOLD', LLM_MODEL: 'gpt-4o-mini', LLM_API_KEY: 'sk-new' });
    expect(both).toMatchObject({ provider: 'openai', model: 'gpt-4o-mini', apiKey: 'sk-new' });
  });

  it('finds vendor-specific key variables and reports "not configured" when there is no key', () => {
    expect(resolveSettings({ LLM_MODEL: 'meta-llama/x', HF_TOKEN: 'hf_t' }).apiKey).toBe('hf_t');
    expect(resolveSettings({ LLM_MODEL: 'gpt-4o-mini' }).configured).toBe(false);
    expect(resolveSettings({ LLM_PROVIDER: 'ollama', LLM_MODEL: 'llama3.1' }).configured).toBe(true);
  });
});

describe('callModel request shapes', () => {
  const capture = (reply) => {
    const calls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init) => {
        calls.push({ url, headers: init.headers, body: JSON.parse(init.body) });
        return { ok: true, json: async () => reply };
      })
    );
    return calls;
  };

  it('Gemini', async () => {
    const calls = capture({ candidates: [{ content: { parts: [{ text: '{"a":1}' }] } }] });
    const text = await callModel({ model: 'gemini-3.5-flash-lite', apiKey: 'AIzaX', prompt: 'hi' });
    expect(text).toBe('{"a":1}');
    expect(calls[0].url).toBe('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent');
    expect(calls[0].headers['x-goog-api-key']).toBe('AIzaX');
    expect(calls[0].body.generationConfig.responseMimeType).toBe('application/json');
  });

  it('Anthropic (browser-direct header included)', async () => {
    const calls = capture({ content: [{ type: 'text', text: 'ok' }] });
    expect(await callModel({ model: 'claude-haiku-4-5', apiKey: 'sk-ant-x', prompt: 'hi' })).toBe('ok');
    expect(calls[0].url).toBe('https://api.anthropic.com/v1/messages');
    expect(calls[0].headers['x-api-key']).toBe('sk-ant-x');
    expect(calls[0].headers['anthropic-dangerous-direct-browser-access']).toBe('true');
    expect(calls[0].body.messages[0].content).toBe('hi');
  });

  it('Hugging Face uses the router with a bearer token', async () => {
    const calls = capture({ choices: [{ message: { content: '{}' } }] });
    await callModel({ model: 'meta-llama/Llama-3.1-8B-Instruct', apiKey: 'hf_abc', prompt: 'hi' });
    expect(calls[0].url).toBe('https://router.huggingface.co/v1/chat/completions');
    expect(calls[0].headers.Authorization).toBe('Bearer hf_abc');
    expect(calls[0].body.model).toBe('meta-llama/Llama-3.1-8B-Instruct');
  });

  it('OpenAI and a custom OpenAI-compatible base URL', async () => {
    let calls = capture({ choices: [{ message: { content: 'x' } }] });
    await callModel({ model: 'gpt-4o-mini', apiKey: 'sk-abc', prompt: 'hi' });
    expect(calls[0].url).toBe('https://api.openai.com/v1/chat/completions');
    calls = capture({ choices: [{ message: { content: 'x' } }] });
    await callModel({ model: 'my-model', baseUrl: 'http://localhost:11434/v1/', prompt: 'hi' });
    expect(calls[0].url).toBe('http://localhost:11434/v1/chat/completions');
    expect(calls[0].headers.Authorization).toBeUndefined(); // no key needed for a local server
  });

  it('drops JSON mode when a model rejects it, then retries once', async () => {
    const bodies = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init) => {
        const body = JSON.parse(init.body);
        bodies.push('response_format' in body);
        if ('response_format' in body) {
          return {
            ok: false, status: 400, statusText: 'Bad Request',
            text: async () => JSON.stringify({ error: { message: 'response_format is not supported' } }),
          };
        }
        return { ok: true, json: async () => ({ choices: [{ message: { content: '{"ok":true}' } }] }) };
      })
    );
    expect(await callModel({ model: 'org/model', apiKey: 'hf_x', prompt: 'hi' })).toBe('{"ok":true}');
    expect(bodies).toEqual([true, false]);
  });

  it('errors carry the HTTP status and a readable message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false, status: 401, statusText: 'Unauthorized',
        text: async () => JSON.stringify({ error: { message: 'Incorrect API key provided' } }),
      }))
    );
    await expect(callModel({ model: 'gpt-4o-mini', apiKey: 'sk-bad', prompt: 'hi' })).rejects.toMatchObject({
      status: 401,
      message: expect.stringContaining('Incorrect API key provided'),
    });
    await expect(callModel({ model: 'gpt-4o-mini', apiKey: 'sk-bad', prompt: 'hi' })).rejects.toBeInstanceOf(LLMError);
  });
});

describe('parseJsonLoose', () => {
  it('handles fences, surrounding prose and trailing commas', () => {
    expect(parseJsonLoose('```json\n{"a": 1}\n```')).toEqual({ a: 1 });
    expect(parseJsonLoose('Sure! Here you go: {"a": 1, "b": [1,2,],} Hope that helps.')).toEqual({ a: 1, b: [1, 2] });
    expect(() => parseJsonLoose('no json here')).toThrow();
  });
});
