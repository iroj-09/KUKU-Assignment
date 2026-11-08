"""Connect any model in one step: type a model name and an API key, it tests them and saves them.

    python scripts/setup_model.py                         # asks for both
    python scripts/setup_model.py --model gpt-4o-mini     # asks only for the key (hidden input)
    python scripts/setup_model.py --model meta-llama/Llama-3.1-8B-Instruct   # Hugging Face token
    python scripts/setup_model.py --model llama3.1 --provider ollama          # local, no key
    python scripts/setup_model.py --model my-model --base-url https://my-server/v1   # any OpenAI-compatible API

The vendor is detected from the key prefix or the model name (see src/llm.py). The result is saved
to .env as LLM_MODEL / LLM_API_KEY; nothing else in .env is touched. Your key is never printed.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import llm  # noqa: E402

ENV_PATH = ROOT / ".env"
MANAGED = ("LLM_MODEL", "LLM_API_KEY", "LLM_PROVIDER", "LLM_BASE_URL")


def mask(key: str) -> str:
    return "(none)" if not key else (key[:4] + "…" + key[-3:] if len(key) > 10 else "…")


def write_env(values: dict[str, str]) -> None:
    """Update/insert the given variables in .env, drop stale managed ones, keep everything else."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out, seen = [], set()
    for line in lines:
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        name = m.group(1) if m else None
        if name in MANAGED:
            if name in values:
                out.append(f"{name}={values[name]}")
                seen.add(name)
            # a managed variable that is not part of the new setup (e.g. an old LLM_PROVIDER) is removed
            continue
        out.append(line)
    for name, value in values.items():
        if name not in seen:
            out.append(f"{name}={value}")
    ENV_PATH.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="model name, e.g. gemini-3.5-flash-lite, gpt-4o-mini, claude-haiku-4-5, org/model")
    ap.add_argument("--key", help="API key (prefer the hidden prompt: a key typed here lands in shell history)")
    ap.add_argument("--provider", choices=llm.PROVIDERS, help="only if auto-detection guesses wrong")
    ap.add_argument("--base-url", help="custom OpenAI-compatible endpoint")
    ap.add_argument("--no-test", action="store_true", help="save without calling the model")
    args = ap.parse_args()

    current = llm.settings()
    model = args.model or input(f"Model name [{current.model}]: ").strip() or current.model

    key = args.key
    if key is None:
        needs_key = not (args.provider == "ollama" or args.base_url)
        prompt = "API key (hidden, press Enter to keep the one already in .env): " if needs_key else "API key (optional): "
        key = getpass.getpass(prompt).strip()

    # Apply to this process so detection and the test use exactly what will be saved.
    os.environ["LLM_MODEL"] = model
    if key:
        os.environ["LLM_API_KEY"] = key
    for var, val in (("LLM_PROVIDER", args.provider), ("LLM_BASE_URL", args.base_url)):
        if val:
            os.environ[var] = val
        else:
            os.environ.pop(var, None)

    s = llm.settings()
    print(f"\nProvider: {s.provider}   Model: {s.model}   Key: {mask(s.api_key)}"
          + (f"   Endpoint: {s.base_url}" if s.provider not in ('gemini', 'anthropic') else ""))

    if not llm.is_configured():
        print("No API key found. Enter one (or set the vendor's key variable in .env) and run again.")
        return 1

    if not args.no_test:
        print("Testing the connection…")
        try:
            reply = llm.complete_json('Reply with exactly this JSON and nothing else: {"status": "working"}', timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"\nCould not reach the model: {type(exc).__name__}: {str(exc)[:300]}")
            print("Nothing was saved. Check the model name and key (or pass --provider / --base-url).")
            return 1
        print(f"Model replied: {reply.strip()[:120]}")

    values = {"LLM_MODEL": s.model, "LLM_API_KEY": s.api_key}
    if args.provider:
        values["LLM_PROVIDER"] = args.provider
    if args.base_url:
        values["LLM_BASE_URL"] = args.base_url
    if not s.api_key:
        values.pop("LLM_API_KEY")
    write_env(values)
    print(f"\nSaved to {ENV_PATH.name}. Run the pipeline with:  python run_all.py --input data/input")
    return 0


if __name__ == "__main__":
    sys.exit(main())
