"""The model is swappable: the evaluator must run unchanged against any supported provider."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

import llm  # noqa: E402


def _evaluations_for(prompt: str) -> dict:
    """Behave like a model: read the CANDIDATES json out of the prompt, answer for each."""
    payload = json.loads(prompt.split("CANDIDATES:\n", 1)[1])
    return {
        "evaluations": [
            {
                "candidate_id": c["candidate_id"],
                "is_promising": True,
                "hook": "opening line",
                "hook_timestamp": c["start_seconds"] + 1,
                "cliffhanger": "closing line",
                "cliffhanger_timestamp": c["end_seconds"] - 1,
                "why_it_works": "fake model says so",
                "standalone_context": "context",
                "hook_score": 8,
                "cliffhanger_score": 9,
                "emotional_score": 7,
                "standalone_score": 6,
                "progression_score": 5,
                "risks": [],
            }
            for c in payload
        ]
    }


class _OpenAICompatible(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _OpenAICompatible.seen.append((self.path, self.headers.get("Authorization"), body))
        content = json.dumps(_evaluations_for(body["messages"][0]["content"]))
        reply = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture
def fake_openai_server():
    _OpenAICompatible.seen = []
    server = HTTPServer(("127.0.0.1", 0), _OpenAICompatible)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_evaluator_runs_end_to_end_on_another_provider(tmp_path, fake_openai_server):
    rows = [
        {
            "episode": "Episode 1", "clip_start": 10.0, "clip_end": 40.0,
            "opening_transcript": "[10.00-12.00] A: \"Stop!\"",
            "full_transcript": "[10.00-12.00] A: \"Stop!\" [38.00-40.00] B: \"No...\"",
            "ending_transcript": "[38.00-40.00] B: \"No...\"",
        },
        {
            "episode": "Episode 2", "clip_start": 0.0, "clip_end": 25.0,
            "opening_transcript": "x", "full_transcript": "x y", "ending_transcript": "y",
        },
    ]
    src = tmp_path / "in.csv"
    pd.DataFrame(rows).to_csv(src, index=False)

    out_dir = tmp_path / "out"
    env = {
        **os.environ,
        "LLM_PROVIDER": "openai",
        "LLM_BASE_URL": fake_openai_server,
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "any-model",
        "GEMINI_API_KEY": "",  # prove Gemini is not needed
    }
    # --input/--output-dir are resolved relative to the project root, so use relative-to-root paths.
    rel = lambda p: os.path.relpath(p, ROOT)  # noqa: E731
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "editorial_evaluator.py"),
         "--input", rel(src), "--output-dir", rel(out_dir), "--batch-size", "2", "--pause", "0"],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    evals = json.loads((out_dir / "editorial_evaluations.json").read_text(encoding="utf-8"))
    assert len(evals) == 2
    for e in evals:
        assert e["evaluation_mode"] == "llm"
        assert e["llm_model"] == "openai:any-model"
        assert e["timestamp_compliance"] == "PASS"
        assert e["final_score"] == 73.0  # 10*(.25*8 + .25*9 + .2*7 + .15*6 + .15*5)

    path, auth, body = _OpenAICompatible.seen[0]
    assert path == "/v1/chat/completions"
    assert auth == "Bearer test-key"
    assert body["model"] == "any-model"


def test_provider_and_model_selection(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "GEMINI_MODEL", "LLM_API_KEY", "GEMINI_API_KEY",
                "ANTHROPIC_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    assert llm.provider() == "gemini"
    assert llm.model() == "gemini-3.5-flash-lite"

    monkeypatch.setenv("GEMINI_MODEL", "gemini-x")
    assert llm.model() == "gemini-x"
    monkeypatch.setenv("LLM_MODEL", "override")
    assert llm.model() == "override"

    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")  # alias
    assert llm.provider() == "openai"
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert llm.provider() == "openrouter"

    monkeypatch.setenv("LLM_PROVIDER", "nonsense")
    with pytest.raises(ValueError):
        llm.provider()


def test_missing_credentials_fail_clearly(monkeypatch):
    for var in ("LLM_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.require_configured()

    # A local OpenAI-compatible server (e.g. Ollama) needs no key.
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    assert llm.is_configured()


def test_anthropic_request_shape(monkeypatch):
    captured = {}

    def fake_post(url, headers, body, timeout):
        captured.update(url=url, headers=headers, body=body)
        return {"content": [{"type": "text", "text": '{"evaluations": []}'}]}

    monkeypatch.setattr(llm, "_post_json", fake_post)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "claude-test")

    assert llm.complete_json("hello") == '{"evaluations": []}'
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "k"
    assert captured["body"]["model"] == "claude-test"
    assert captured["body"]["messages"][0]["content"] == "hello"


# ---------------------------------------------------------------------------
# "Type a model name and an API key and it works" (auto-detection, Hugging Face style)
# ---------------------------------------------------------------------------

ALL_KEY_ENVS = [
    "LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "GEMINI_MODEL",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN",
    "HUGGINGFACE_API_KEY", "HUGGINGFACEHUB_API_TOKEN", "OPENROUTER_API_KEY", "GROQ_API_KEY",
    "TOGETHER_API_KEY",
]


@pytest.fixture
def clean_env(monkeypatch):
    for var in ALL_KEY_ENVS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.mark.parametrize(
    "model, key, expected",
    [
        ("gemini-3.5-flash-lite", "AIzaSyEXAMPLE", "gemini"),
        ("gpt-4o-mini", "sk-proj-abc", "openai"),
        ("claude-haiku-4-5", "sk-ant-abc", "anthropic"),
        ("meta-llama/Llama-3.1-8B-Instruct", "hf_abc", "huggingface"),
        ("meta-llama/Llama-3.1-8B-Instruct", "", "huggingface"),          # "org/model" => Hugging Face
        ("openai/gpt-4o-mini", "sk-or-abc", "openrouter"),                  # key prefix beats the model name
        ("llama-3.3-70b-versatile", "gsk_abc", "groq"),
        ("o3-mini", "", "openai"),
        ("something-unknown", "", "gemini"),                                # default
    ],
)
def test_provider_is_detected_from_key_or_model(clean_env, model, key, expected):
    clean_env.setenv("LLM_MODEL", model)
    if key:
        clean_env.setenv("LLM_API_KEY", key)
    s = llm.settings()
    assert s.provider == expected
    assert s.model == model


def test_two_variables_are_enough_for_any_vendor(clean_env):
    clean_env.setenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    clean_env.setenv("LLM_API_KEY", "hf_secret")
    s = llm.settings()
    assert (s.provider, s.api_key) == ("huggingface", "hf_secret")
    assert s.base_url == "https://router.huggingface.co/v1"
    assert llm.is_configured()


def test_existing_gemini_only_env_still_works(clean_env):
    # The original setup: GEMINI_API_KEY + GEMINI_MODEL and nothing else.
    clean_env.setenv("GEMINI_API_KEY", "AIzaOLD")
    clean_env.setenv("GEMINI_MODEL", "gemini-old-model")
    s = llm.settings()
    assert (s.provider, s.model, s.api_key) == ("gemini", "gemini-old-model", "AIzaOLD")
    # ...and a generic LLM_* pair takes over when present.
    clean_env.setenv("LLM_MODEL", "gpt-4o-mini")
    clean_env.setenv("LLM_API_KEY", "sk-new")
    s = llm.settings()
    assert (s.provider, s.model, s.api_key) == ("openai", "gpt-4o-mini", "sk-new")


def test_vendor_specific_key_variable_is_found(clean_env):
    clean_env.setenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    clean_env.setenv("HF_TOKEN", "hf_from_standard_variable")
    assert llm.settings().api_key == "hf_from_standard_variable"


def test_huggingface_request_goes_to_the_router(clean_env, monkeypatch):
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(llm, "_post_json", fake_post)
    clean_env.setenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    clean_env.setenv("LLM_API_KEY", "hf_abc")
    llm.complete_json("hi")
    assert seen["url"] == "https://router.huggingface.co/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer hf_abc"


def test_json_mode_is_dropped_when_a_model_rejects_it(clean_env, monkeypatch):
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append("response_format" in body)
        if "response_format" in body:
            raise llm.LLMHTTPError(400, "HTTP 400: response_format is not supported by this model")
        return {"choices": [{"message": {"content": '{"evaluations": []}'}}]}

    monkeypatch.setattr(llm, "_post_json", fake_post)
    clean_env.setenv("LLM_MODEL", "some-org/some-model")
    clean_env.setenv("LLM_API_KEY", "hf_abc")
    assert llm.complete_json("hi") == '{"evaluations": []}'
    assert calls == [True, False]


def test_missing_key_message_tells_you_what_to_do(clean_env):
    clean_env.setenv("LLM_MODEL", "gpt-4o-mini")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.require_configured()


def test_setup_script_updates_env_without_touching_other_lines(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import setup_model

    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=keep_me\n# a comment\nLLM_PROVIDER=openai\nLLM_MODEL=old\nOTHER=1\n", encoding="utf-8"
    )
    monkeypatch.setattr(setup_model, "ENV_PATH", env)
    setup_model.write_env({"LLM_MODEL": "gemini-x", "LLM_API_KEY": "AIzaNEW"})
    text = env.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=keep_me" in text and "# a comment" in text and "OTHER=1" in text
    assert "LLM_MODEL=gemini-x" in text and "LLM_API_KEY=AIzaNEW" in text
    assert "LLM_PROVIDER" not in text  # a stale provider override would break detection
    assert text.count("LLM_MODEL=") == 1
