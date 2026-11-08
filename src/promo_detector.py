"""Optional Gemini evaluation with strict evidence and graceful fallback."""

import json
import re
import time

from pathlib import Path
from dotenv import load_dotenv
from scoring import heuristic_score
import llm

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)  # shell/CLI values win over .env

PROMPT = """You are a promo editor evaluating a 20–60 second excerpt
from a vertical microdrama screenplay.

Use ONLY the supplied transcript and timestamps.
Do not invent actions, dialogue, motives, or outcomes.

Return one JSON object with exactly these keys:
{
  "is_promising": true,
  "hook": "Exact moment/line that makes a viewer stop scrolling",
  "hook_timestamp": "timestamp or null",
  "cliffhanger": "Unresolved question or reveal at the cut",
  "cliffhanger_timestamp": "timestamp or null",
  "why_it_works": "One concise sentence",
  "standalone_context": "What a new viewer needs to understand",
  "hook_score": 1,
  "cliffhanger_score": 1,
  "standalone_score": 1,
  "risks": []
}

Scoring: integers 1–10.

A hook must occur within the FIRST 3 seconds of the clip.
A cliffhanger must occur in the FINAL 5 seconds and remain
unresolved in the supplied excerpt.

A clip that depends on unexplained character relationships
or prior episodes should receive a low standalone_score.

If no genuine hook or unresolved ending is present, say so
and score it low.

Do not treat dramatic wording alone as proof of a cliffhanger.
"""


def _clean_json(text):
    text = (text or "").strip()
    text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        text,
        flags=re.I
    )
    return json.loads(text)


def evaluate_candidate(candidate, use_gemini=True):

    base = heuristic_score(candidate)

    if not use_gemini:
        return {
            **candidate,
            **base,
            "evaluation_mode": "heuristic_only",
            "hook": "",
            "cliffhanger": "",
            "why_it_works": "Baseline lexical score only; human review required."
        }

    if not llm.is_configured():
        return {
            **candidate,
            **base,
            "evaluation_mode": "heuristic_fallback",
            "model_error": "LLM credentials are not configured (see src/llm.py).",
            "hook": "",
            "cliffhanger": "",
            "why_it_works": "Gemini was not run; baseline score requires human review."
        }

    try:
        model = llm.describe()

        payload = {
            "episode": candidate.get("episode"),
            "start_seconds": candidate.get("start"),
            "end_seconds": candidate.get("end"),
            "duration_seconds": candidate.get("duration"),
            "events": candidate.get("events", []),
            "transcript": candidate.get("transcript", ""),
        }


        print(f"[GEMINI] Sending request to {model}...", flush=True)

        start_time = time.time()

        raw_text = llm.complete_json(
            PROMPT
            + "\nSCREENPLAY EXCERPT:\n"
            + json.dumps(payload, ensure_ascii=False),
            timeout=45,
        )

        print(
            f"[GEMINI] Response received in "
            f"{time.time() - start_time:.2f} seconds",
            flush=True
        )

        data = _clean_json(raw_text)

        for key in (
            "hook_score",
            "cliffhanger_score",
            "standalone_score"
        ):
            value = data.get(key, 1)
            data[key] = max(1, min(10, int(value)))

        ai_score = round(
            (
                0.40 * data["hook_score"]
                + 0.35 * data["cliffhanger_score"]
                + 0.25 * data["standalone_score"]
            ) * 10,
            2
        )

        return {
            **candidate,
            **base,
            **data,
            "baseline_score": ai_score,
            "heuristic_score": base["baseline_score"],
            "evaluation_mode": "gemini",
            "model": model
        }

    except Exception as exc:
        return {
            **candidate,
            **base,
            "evaluation_mode": "heuristic_fallback",
            "model_error": f"{type(exc).__name__}: {exc}",
            "hook": "",
            "cliffhanger": "",
            "why_it_works": "Gemini evaluation failed; baseline score requires human review."
        }
