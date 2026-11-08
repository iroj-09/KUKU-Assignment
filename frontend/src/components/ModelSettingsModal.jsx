import React, { useState, useEffect } from 'react';
import { X, Sparkles, Key, CheckCircle2, AlertCircle, RefreshCw, Eye, EyeOff, ChevronDown } from 'lucide-react';
import { STORAGE, getServerStatus, completeJson } from '../utils/geminiEvaluator';
import { detectProvider, DEFAULT_MODELS, PROVIDERS, PROVIDER_LABELS } from '../utils/llmClient';

const SUGGESTIONS = [
  'gemini-3.5-flash-lite',
  'gemini-2.5-flash',
  'gpt-4o-mini',
  'claude-haiku-4-5',
  'meta-llama/Llama-3.1-8B-Instruct',
  'Qwen/Qwen2.5-72B-Instruct',
  'llama-3.3-70b-versatile',
];

function readStored() {
  const get = (k) => {
    try {
      return localStorage.getItem(k) || '';
    } catch {
      return '';
    }
  };
  return {
    model: get(STORAGE.model),
    apiKey: get(STORAGE.apiKey),
    baseUrl: get(STORAGE.baseUrl),
    provider: get(STORAGE.provider),
  };
}

function ModelSettingsDialog({ onClose, onSave }) {
  // Mounted fresh every time the dialog opens, so it always starts from what is saved.
  const [stored] = useState(readStored);
  const [model, setModel] = useState(stored.model);
  const [apiKey, setApiKey] = useState(stored.apiKey);
  const [baseUrl, setBaseUrl] = useState(stored.baseUrl);
  const [provider, setProvider] = useState(stored.provider);
  const [showKey, setShowKey] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(Boolean(stored.baseUrl || stored.provider));
  const [testStatus, setTestStatus] = useState(null); // 'testing' | 'success' | 'error'
  const [testMsg, setTestMsg] = useState('');

  // Escape closes the dialog, like any other dialog.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const server = getServerStatus();
  const usingServer = Boolean(server?.configured) && !apiKey && !baseUrl;
  const hasOwnConnection = Boolean(apiKey || baseUrl);

  let detected = null;
  let detectError = '';
  try {
    detected = detectProvider({ provider, model, apiKey, baseUrl });
  } catch (e) {
    detectError = e.message;
  }
  const effectiveModel = model.trim() || (detected ? DEFAULT_MODELS[detected] : '');

  const buildConfig = () => {
    if (hasOwnConnection) {
      return { mode: 'direct', provider: detected, model: effectiveModel, apiKey: apiKey.trim(), baseUrl: baseUrl.trim() };
    }
    if (server?.configured) return { mode: 'proxy', provider: server.provider, model: server.model };
    return null;
  };

  const handleTest = async () => {
    const config = buildConfig();
    if (!config) {
      setTestStatus('error');
      setTestMsg('Enter an API key (and a model name) first.');
      return;
    }
    setTestStatus('testing');
    setTestMsg('');
    const started = Date.now();
    try {
      await completeJson('Reply with exactly this JSON and nothing else: {"status": "working"}', config);
      setTestStatus('success');
      setTestMsg(`Connected to ${config.provider}:${config.model} in ${Date.now() - started} ms.`);
    } catch (err) {
      setTestStatus('error');
      setTestMsg(err.message || 'Connection failed.');
    }
  };

  const handleSave = () => {
    try {
      if (hasOwnConnection) {
        localStorage.setItem(STORAGE.apiKey, apiKey.trim());
        localStorage.setItem(STORAGE.model, effectiveModel);
        localStorage.setItem(STORAGE.baseUrl, baseUrl.trim());
        localStorage.setItem(STORAGE.provider, provider);
      } else {
        [STORAGE.apiKey, STORAGE.model, STORAGE.baseUrl, STORAGE.provider].forEach((k) => localStorage.removeItem(k));
      }
    } catch (e) {
      console.error('Could not save AI settings', e);
    }
    onSave?.(hasOwnConnection ? `${detected}:${effectiveModel}` : server?.configured ? `${server.provider}:${server.model} (from .env)` : '');
    onClose();
  };

  const handleClear = () => {
    setApiKey('');
    setBaseUrl('');
    setProvider('');
    setModel('');
    setTestStatus(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Connect an AI model"
        className="relative w-full max-w-lg max-h-[92vh] overflow-y-auto bg-white border border-slate-200 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-5"
      >
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Connect an AI model</h2>
              <p className="text-xs text-slate-500">
                Type a model name and your API key. Works with Gemini, OpenAI, Claude, Hugging Face, OpenRouter, Groq
                and local Ollama.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Server (.env) connection */}
        {server?.configured && (
          <div
            className={`p-3 rounded-xl border text-xs ${
              usingServer ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-slate-50 border-slate-200 text-slate-600'
            }`}
          >
            <div className="font-bold flex items-center gap-1.5">
              <CheckCircle2 className={`w-3.5 h-3.5 ${usingServer ? 'text-emerald-600' : 'text-slate-400'}`} />
              Connected through the project's .env: {server.provider}:{server.model}
            </div>
            <p className="mt-0.5">
              {usingServer
                ? 'This is the connection in use. Your key stays on the server and never reaches the browser. Enter your own key below only to override it in this browser.'
                : 'Your own key below overrides it in this browser. Clear the fields and save to go back to it.'}
            </p>
          </div>
        )}

        {/* Model name */}
        <div className="space-y-1.5">
          <label htmlFor="model-name" className="text-xs font-semibold text-slate-700">
            Model name
          </label>
          <input
            id="model-name"
            list="model-suggestions"
            type="text"
            placeholder="e.g. gemini-3.5-flash-lite, gpt-4o-mini, meta-llama/Llama-3.1-8B-Instruct"
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              setTestStatus(null);
            }}
            className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:border-amber-500 font-mono transition-colors"
          />
          <datalist id="model-suggestions">
            {SUGGESTIONS.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>

        {/* API key */}
        <div className="space-y-1.5">
          <label htmlFor="api-key" className="text-xs font-semibold text-slate-700 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Key className="w-3.5 h-3.5 text-amber-500" /> API key
            </span>
            {apiKey && (
              <span className="text-[10px] text-emerald-700 font-bold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                Key entered
              </span>
            )}
          </label>
          <div className="relative">
            <input
              id="api-key"
              type={showKey ? 'text' : 'password'}
              autoComplete="off"
              placeholder="Paste your key (AIza…, sk-…, sk-ant-…, hf_…)"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setTestStatus(null);
              }}
              className="w-full pl-3.5 pr-10 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:border-amber-500 font-mono transition-colors"
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              aria-label={showKey ? 'Hide key' : 'Show key'}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-700"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-[10px] text-slate-500">
            Saved only in this browser. Requests go straight from your browser to the model provider.
          </p>
        </div>

        {/* Detected provider */}
        <div className="text-xs flex flex-wrap items-center gap-2">
          <span className="text-slate-500">Detected provider:</span>
          {detected ? (
            <span className="font-bold px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-slate-800">
              {PROVIDER_LABELS[detected]}
            </span>
          ) : (
            <span className="text-rose-600 font-semibold">{detectError}</span>
          )}
          {detected && !model.trim() && <span className="text-slate-400">(default model: {DEFAULT_MODELS[detected]})</span>}
        </div>

        {/* Advanced */}
        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-800"
          >
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
            Advanced (only if the guess above is wrong)
          </button>
          {showAdvanced && (
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-[11px] font-semibold text-slate-600 space-y-1 block">
                Provider
                <select
                  value={provider}
                  onChange={(e) => {
                    setProvider(e.target.value);
                    setTestStatus(null);
                  }}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-amber-500"
                >
                  <option value="">Auto-detect</option>
                  {PROVIDERS.map((p) => (
                    <option key={p} value={p}>
                      {PROVIDER_LABELS[p]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-[11px] font-semibold text-slate-600 space-y-1 block">
                Custom base URL (OpenAI-compatible)
                <input
                  type="text"
                  placeholder="https://my-server/v1"
                  value={baseUrl}
                  onChange={(e) => {
                    setBaseUrl(e.target.value);
                    setTestStatus(null);
                  }}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 font-mono focus:outline-none focus:border-amber-500"
                />
              </label>
            </div>
          )}
        </div>

        {/* Test */}
        <div className="space-y-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={testStatus === 'testing'}
            className="w-full py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200 text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-xs"
          >
            {testStatus === 'testing' ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Testing connection...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                <span>Test connection</span>
              </>
            )}
          </button>

          {testStatus === 'success' && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 font-medium flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>{testMsg}</span>
            </div>
          )}
          {testStatus === 'error' && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 font-medium flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
              <span className="break-words">{testMsg}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 pt-4 border-t border-slate-100">
          <button
            type="button"
            onClick={handleClear}
            disabled={!hasOwnConnection && !model}
            className="text-[11px] font-semibold text-slate-400 hover:text-rose-600 disabled:opacity-40"
          >
            Clear fields
          </button>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-500 hover:text-slate-800"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={Boolean(detectError)}
              className="px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 text-xs font-bold shadow-md shadow-amber-500/20 transition-all hover:scale-[1.01]"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ModelSettingsModal({ isOpen, onClose, onSave }) {
  return isOpen ? <ModelSettingsDialog onClose={onClose} onSave={onSave} /> : null;
}
