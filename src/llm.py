"""One place that talks to a language model: give it a model name and an API key, it works.

The pipeline only needs "prompt in, JSON text out". Everything vendor-specific lives here, so the
rest of the code never changes when you switch models.

Quickest setup (two lines in .env, like a Hugging Face token + model id):

    LLM_MODEL=gemini-3.5-flash-lite          # or gpt-4o-mini, claude-haiku-4-5,
    LLM_API_KEY=your_key_here                #     meta-llama/Llama-3.1-8B-Instruct, ...

or run  `python scripts/setup_model.py`  which asks for both, tests them, and saves them.

The provider is detected automatically:
  1. the key's prefix   AIza.. gemini | sk-ant-.. anthropic | sk-or-.. openrouter | hf_.. huggingface
                        | gsk_.. groq | sk-.. openai
  2. else the model name   gemini-* | claude-* | gpt-*, o1/o3/o4* | "org/model" (Hugging Face)
  3. else whichever vendor-specific key is set (GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY,
     HF_TOKEN, OPENROUTER_API_KEY, GROQ_API_KEY, TOGETHER_API_KEY)
  4. else gemini.
Override any of it with LLM_PROVIDER, LLM_BASE_URL (any OpenAI-compatible server, e.g. Ollama/vLLM).

Backward compatible: GEMINI_API_KEY + GEMINI_MODEL alone still work exactly as before.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)  # shell/CLI values win over .env

# OpenAI-compatible endpoints (one request format covers all of them).
OPENAI_COMPATIBLE = {
    "openai": "https://api.openai.com/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
}

# Environment variables that may hold a key for each vendor (after LLM_API_KEY).
KEY_ENV = {
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "huggingface": ["HF_TOKEN", "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "ollama": [],
}

DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash-lite",
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "huggingface": "meta-llama/Llama-3.1-8B-Instruct",
    "openrouter": "openai/gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "ollama": "llama3.1",
}

PROVIDERS = tuple(DEFAULT_MODELS)

ALIASES = {
    "openai-compatible": "openai",
    "hf": "huggingface",
    "hugging-face": "huggingface",
    "google": "gemini",
    "claude": "anthropic",
}


class LLMHTTPError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str
    base_url: str  # only meaningful for OpenAI-compatible providers


def _clean(value: str | None) -> str:
    return (value or "").strip()


def provider_from_key(key: str) -> str | None:
    key = key.strip()
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-or-"):
        return "openrouter"
    if key.startswith("hf_"):
        return "huggingface"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("sk-"):
        return "openai"
    return None


def provider_from_model(model: str) -> str | None:
    m = model.strip().lower()
    if m.startswith("gemini") or m.startswith("models/gemini"):
        return "gemini"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt-", "chatgpt", "o1", "o3", "o4")):
        return "openai"
    if "/" in m:
        return "huggingface"
    return None


def detect_provider(model: str = "", api_key: str = "", base_url: str = "") -> str:
    explicit = _clean(os.getenv("LLM_PROVIDER")).lower()
    if explicit:
        explicit = ALIASES.get(explicit, explicit)
        if explicit not in PROVIDERS:
            raise ValueError(f"Unknown LLM_PROVIDER '{explicit}'. Use one of: {', '.join(PROVIDERS)}.")
        return explicit
    if base_url:
        return "openai"  # a custom OpenAI-compatible server
    return (
        provider_from_key(api_key)
        or provider_from_model(model)
        or next(
            (p for p, names in KEY_ENV.items() if any(_clean(os.getenv(n)) for n in names)),
            None,
        )
        or "gemini"
    )


def settings() -> Settings:
    base_url_env = _clean(os.getenv("LLM_BASE_URL"))
    model_env = _clean(os.getenv("LLM_MODEL"))
    generic_key = _clean(os.getenv("LLM_API_KEY"))

    # GEMINI_MODEL is the legacy way to name the model; only use it to help detection.
    legacy_model = _clean(os.getenv("GEMINI_MODEL"))
    provider = detect_provider(model_env or legacy_model, generic_key, base_url_env)

    api_key = generic_key
    if not api_key:
        api_key = next((_clean(os.getenv(n)) for n in KEY_ENV[provider] if _clean(os.getenv(n))), "")

    model = model_env
    if not model and provider == "gemini":
        model = legacy_model
    model = model or DEFAULT_MODELS[provider]

    return Settings(provider, model, api_key, base_url_env or OPENAI_COMPATIBLE.get(provider, ""))


# ---- small accessors (stable names used across the project and its tests) ----

def provider() -> str:
    return settings().provider


def model() -> str:
    return settings().model


def is_configured() -> bool:
    s = settings()
    if s.api_key:
        return True
    # Local / self-hosted OpenAI-compatible servers (Ollama, vLLM) need no key.
    return s.provider == "ollama" or bool(_clean(os.getenv("LLM_BASE_URL")))


def require_configured() -> None:
    s = settings()
    if not is_configured():
        raise RuntimeError(
            f"No API key for {s.provider}:{s.model}. Put your key in .env as LLM_API_KEY "
            f"(or {KEY_ENV[s.provider][0] if KEY_ENV[s.provider] else 'LLM_API_KEY'}), "
            "or run: python scripts/setup_model.py"
        )


def describe() -> str:
    s = settings()
    return f"{s.provider}:{s.model}"


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _post_json(url: str, headers: dict, body: dict, timeout: int) -> dict:
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError(f"Model endpoint must be an http(s) URL, got: {url[:60]!r}")
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (scheme checked above)
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:400]
        raise LLMHTTPError(err.code, f"HTTP {err.code} from {url}: {detail}") from err


def _gemini(prompt: str, timeout: int, s: Settings) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=s.api_key,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=3,
                initial_delay=2.0,
                max_delay=20.0,
                http_status_codes=[429, 500, 502, 503, 504],
            )
        ),
    )
    response = client.interactions.create(
        model=s.model.removeprefix("models/"),
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json"},
        timeout=timeout,
    )
    return response.output_text or ""


def _openai_compatible(prompt: str, timeout: int, s: Settings) -> str:
    base = s.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {s.api_key}"} if s.api_key else {}
    body = {
        "model": s.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        data = _post_json(f"{base}/chat/completions", headers, body, timeout)
    except LLMHTTPError as err:
        # Some hosted open models reject JSON mode; the prompt already demands JSON, so retry plainly.
        if err.status in (400, 422) and "response_format" in str(err):
            body.pop("response_format")
            data = _post_json(f"{base}/chat/completions", headers, body, timeout)
        else:
            raise
    return data["choices"][0]["message"]["content"] or ""


def _anthropic(prompt: str, timeout: int, s: Settings) -> str:
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": s.api_key, "anthropic-version": "2023-06-01"},
        {
            "model": s.model,
            "max_tokens": 8000,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout,
    )
    return "".join(block.get("text", "") for block in data.get("content", []))


def complete_json(prompt: str, timeout: int = 90) -> str:
    """Send `prompt` to the configured model and return its raw text (expected JSON).

    Callers parse/validate the result; models sometimes wrap JSON in markdown fences, which
    `editorial_evaluator.parse_response` already handles.
    """
    require_configured()
    s = settings()
    if s.provider == "gemini":
        return _gemini(prompt, timeout, s)
    if s.provider == "anthropic":
        return _anthropic(prompt, timeout, s)
    return _openai_compatible(prompt, timeout, s)
