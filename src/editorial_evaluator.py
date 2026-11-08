"""Editorially evaluate shortlisted promo clips with Gemini in small batches.

Run from the project root:
    python src/editorial_evaluator.py --batch-size 5 --limit 10

Successful evaluations are saved after every batch. Failed candidates are logged
separately and can be retried. Existing successful evaluations are preserved.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

import sys
from pathlib import Path as _Path

# Make the project-root config.py importable when running `python src/<script>.py`.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import llm  # noqa: E402

# Evaluation modes that mean "scored by an LLM". "gemini" is the legacy label used by
# earlier outputs; new runs write "llm" together with the provider:model used.
LLM_EVAL_MODES = ("gemini", "llm")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)  # shell/CLI values win over .env

PROMPT = r"""You are a professional short-form vertical-drama promo editor.
Evaluate each supplied screenplay clip using ONLY its transcript and timestamps.
Do not invent dialogue, actions, motives, relationships, or outcomes.

CRITICAL EVIDENCE-WINDOW RULES:
- Use ONLY opening_3_seconds to identify and assess the hook.
- The hook must occur from start_seconds through min(start_seconds + __HOOK_S__, end_seconds).
- Use ONLY ending_5_seconds to identify and assess the cliffhanger.
- The cliffhanger must occur from max(start_seconds, end_seconds - __CLIFF_S__) through end_seconds.
- Use full_transcript for emotional stakes, standalone context, and narrative progression.
- Never select a hook or cliffhanger from outside its respective evidence window.
- If the supplied opening or ending evidence does not support a genuine hook or
  unresolved cliffhanger, return an empty string and null timestamp, and score
  that dimension low. Do not invent missing evidence.
- A dramatic sentence is not automatically a cliffhanger: the ending should leave
  a meaningful question, threat, reveal, interruption, or unresolved consequence.
- Timestamps must be absolute screenplay seconds, not seconds relative to the clip.

For EACH candidate return one JSON object with these exact fields:
{
  "candidate_id": "copy the supplied ID exactly",
  "is_promising": true,
  "hook": "exact dialogue or concise description from opening_3_seconds",
  "hook_timestamp": 123,
  "cliffhanger": "exact dialogue or concise description from ending_5_seconds",
  "cliffhanger_timestamp": 150,
  "why_it_works": "one concise sentence",
  "standalone_context": "minimum context a new viewer needs",
  "hook_score": 1,
  "cliffhanger_score": 1,
  "emotional_score": 1,
  "standalone_score": 1,
  "progression_score": 1,
  "risks": []
}

Return ONLY valid JSON in this shape: {"evaluations": [ ... ]}.
JSON RULES: use double quotes for every key and string; do not use trailing
commas, comments, Markdown fences, or explanatory text outside the JSON object.
Return exactly one complete JSON object and close every array/object.
Scoring: all five scores are integers from 1 (very weak) to 10 (excellent).
- hook_score: strength of the hook, subject to the strict first-3-seconds rule.
- cliffhanger_score: strength of the unresolved ending, subject to the strict final-5-seconds rule.
- emotional_score: strength and clarity of emotional stakes.
- standalone_score: whether a new viewer can follow the moment without prior episodes.
- progression_score: whether the clip develops rather than feeling like disconnected dialogue.
Be strict: a clip can be promising overall while still having weaknesses.
"""


from pydantic import BaseModel, Field, ValidationError

class CandidateEval(BaseModel):
    candidate_id: str
    is_promising: bool = False
    hook: str = ""
    hook_timestamp: float | None = None
    cliffhanger: str = ""
    cliffhanger_timestamp: float | None = None
    why_it_works: str = ""
    standalone_context: str = ""
    hook_score: int = Field(default=1, ge=1, le=10)
    cliffhanger_score: int = Field(default=1, ge=1, le=10)
    emotional_score: int = Field(default=1, ge=1, le=10)
    standalone_score: int = Field(default=1, ge=1, le=10)
    progression_score: int = Field(default=1, ge=1, le=10)
    risks: list[str] = Field(default_factory=list)

class BatchEvaluationResponse(BaseModel):
    evaluations: list[CandidateEval]


def parse_response(response_text: str) -> dict:
    """Robustly parse and schema-validate Gemini JSON responses."""
    text = (response_text or "").strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text, flags=re.I).strip()

    # If surrounded by extra prose, extract the outermost JSON object
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        text = match.group(1)

    # Clean trailing commas before closing braces/brackets
    text = re.sub(r",\s*([\]\}])", r"\1", text)

    try:
        raw_data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ValueError(f"Malformed JSON from the model: {err}\nSnippet: {text[:200]}") from err

    if not isinstance(raw_data, dict) or "evaluations" not in raw_data:
        raise ValueError("Model response is missing the top-level 'evaluations' array")

    try:
        validated = BatchEvaluationResponse.model_validate(raw_data)
        return validated.model_dump()
    except ValidationError as val_err:
        raise ValueError(f"Schema validation error in the model response: {val_err}") from val_err



def candidate_id(row: dict) -> str:
    return f"{row.get('episode')}|{row.get('clip_start')}|{row.get('clip_end')}"


# The evidence windows come from config.py so the prompt and validators can't drift apart.
PROMPT = PROMPT.replace("__HOOK_S__", f"{config.HOOK_WINDOW_SECONDS:g}").replace(
    "__CLIFF_S__", f"{config.CLIFFHANGER_WINDOW_SECONDS:g}"
)

def prepare_candidate(row: dict) -> dict:
    start = float(row["clip_start"])
    end = float(row["clip_end"])
    return {
        "candidate_id": candidate_id(row),
        "episode": row.get("episode"),
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": end - start,
        "opening_3_seconds": str(row.get("opening_transcript", "")),
        "full_transcript": str(row.get("full_transcript", "")),
        "ending_5_seconds": str(row.get("ending_transcript", "")),
    }


def clamp_score(value) -> int:
    try:
        return max(1, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return 1


def validate_timestamp(timestamp, start: float, end: float, window: str):
    try:
        timestamp = float(timestamp)
    except (TypeError, ValueError):
        return None

    if window == "hook":
        valid = start <= timestamp <= min(start + config.HOOK_WINDOW_SECONDS, end)
    elif window == "cliffhanger":
        valid = max(start, end - config.CLIFFHANGER_WINDOW_SECONDS) <= timestamp <= end
    else:
        raise ValueError(f"Unknown timestamp window: {window}")

    return timestamp if valid else None


def validate_evaluation(
    item: dict, expected_id: str, start_seconds: float, end_seconds: float
) -> dict:
    if item.get("candidate_id") != expected_id:
        raise ValueError(
            f"Candidate ID mismatch: expected {expected_id}, "
            f"got {item.get('candidate_id')}"
        )

    item = dict(item)
    score_fields = (
        "hook_score", "cliffhanger_score", "emotional_score",
        "standalone_score", "progression_score",
    )
    for field in score_fields:
        item[field] = clamp_score(item.get(field, 1))

    risks = item.get("risks", [])
    if not isinstance(risks, list):
        risks = [str(risks)]

    item["hook_timestamp"] = validate_timestamp(
        item.get("hook_timestamp"), start_seconds, end_seconds, "hook"
    )
    item["cliffhanger_timestamp"] = validate_timestamp(
        item.get("cliffhanger_timestamp"), start_seconds, end_seconds, "cliffhanger"
    )

    hook_valid = item["hook_timestamp"] is not None
    cliffhanger_valid = item["cliffhanger_timestamp"] is not None

    if not hook_valid:
        item["hook_score"] = min(item["hook_score"], 3)
        risks.append(
            f"Missing or invalid hook timestamp: outside first {config.HOOK_WINDOW_SECONDS:g} seconds"
        )
    if not cliffhanger_valid:
        item["cliffhanger_score"] = min(item["cliffhanger_score"], 3)
        risks.append(
            f"Missing or invalid cliffhanger timestamp: outside final {config.CLIFFHANGER_WINDOW_SECONDS:g} seconds"
        )

    if hook_valid and cliffhanger_valid:
        compliance = "PASS"
    elif hook_valid or cliffhanger_valid:
        compliance = "PARTIAL"
    else:
        compliance = "FAIL"

    item["hook_timestamp_valid"] = hook_valid
    item["cliffhanger_timestamp_valid"] = cliffhanger_valid
    item["timestamp_compliance"] = compliance
    item["risks"] = list(dict.fromkeys(risks))

    item["final_score"] = round((
        0.25 * item["hook_score"]
        + 0.25 * item["cliffhanger_score"]
        + 0.20 * item["emotional_score"]
        + 0.15 * item["standalone_score"]
        + 0.15 * item["progression_score"]
    ) * 10, 2)
    item["evaluation_mode"] = "llm"
    item["llm_model"] = llm.describe()
    return item


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate shortlisted promo candidates with Gemini."
    )
    parser.add_argument("--input", default="outputs/editorial/merged_editorial_data.csv")
    parser.add_argument("--output-dir", default="outputs/editorial")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Evaluate only the first N pending candidates."
    )
    parser.add_argument("--pause", type=float, default=1.5)
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    input_path = BASE_DIR / args.input
    output_dir = BASE_DIR / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "editorial_evaluations.json"
    csv_path = output_dir / "editorial_evaluations.csv"
    failures_path = output_dir / "editorial_failures.json"
    raw_response_dir = output_dir / "raw_responses"
    raw_response_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Shortlist not found: {input_path}")
    llm.require_configured()

    source = pd.read_csv(input_path)
    source = source.astype(object).where(pd.notna(source), "")
    required = {
        "episode", "clip_start", "clip_end", "full_transcript",
        "opening_transcript", "ending_transcript",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Input is missing required columns: {sorted(missing)}")

    rows = source.to_dict(orient="records")
    for row in rows:
        row["candidate_id"] = candidate_id(row)

    saved = {}
    if json_path.exists():
        try:
            previous = json.loads(json_path.read_text(encoding="utf-8"))
            saved = {
                x["candidate_id"]: x for x in previous
                if x.get("evaluation_mode") in LLM_EVAL_MODES
            }
        except (json.JSONDecodeError, KeyError, TypeError) as err:
            raise RuntimeError(
                f"Could not safely read existing results at {json_path}; "
                "back up the file before replacing it."
            ) from err

    pending = [row for row in rows if row["candidate_id"] not in saved]
    if args.limit is not None:
        pending = pending[:args.limit]
    if not pending:
        print("No pending candidates. All candidates already have successful evaluations.")
        return

    model = llm.describe()
    failures = []
    batches = [
        pending[i:i + args.batch_size]
        for i in range(0, len(pending), args.batch_size)
    ]

    print(
        f"Shortlist rows: {len(rows)} | Already evaluated: {len(saved)} "
        f"| Pending: {len(pending)}"
    )
    print(
        f"Model: {model} | Batch size: {args.batch_size} "
        f"| API requests planned: {len(batches)}"
    )

    for batch_no, batch in enumerate(batches, start=1):
        payload = [prepare_candidate(row) for row in batch]
        expected = {item["candidate_id"] for item in payload}
        print(
            f"\nBatch {batch_no}/{len(batches)}: evaluating {len(batch)} candidates...",
            flush=True,
        )
        response_text = None
        try:
            response_text = llm.complete_json(
                PROMPT + "\nCANDIDATES:\n" + json.dumps(
                    payload, ensure_ascii=False
                ),
                timeout=90,
            )
            parsed = parse_response(response_text)
            returned = {}
            for result in parsed["evaluations"]:
                cid = result.get("candidate_id")
                if cid in returned:
                    raise ValueError(f"Gemini returned duplicate candidate ID: {cid}")
                returned[cid] = result

            missing_ids = expected - set(returned)
            if missing_ids:
                raise ValueError(
                    f"Gemini omitted candidate(s): {sorted(missing_ids)}"
                )

            # Validate the whole batch before committing any new results.
            validated_batch = {}
            payload_by_id = {x["candidate_id"]: x for x in payload}
            for cid in expected:
                candidate = payload_by_id[cid]
                validated_batch[cid] = validate_evaluation(
                    returned[cid], cid,
                    candidate["start_seconds"], candidate["end_seconds"]
                )
            saved.update(validated_batch)
            print(f"Batch successful. Total successful: {len(saved)}", flush=True)

        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            print(f"Batch failed: {message}", flush=True)

            # Preserve malformed model output for debugging. Do not overwrite
            # successful evaluations or attempt risky automatic JSON repair.
            if response_text:
                raw_path = raw_response_dir / f"batch_{batch_no:03d}_response.txt"
                raw_path.write_text(response_text, encoding="utf-8")
                print(f"Raw Gemini response saved: {raw_path}", flush=True)

            for cid in sorted(expected):
                failures.append({
                    "candidate_id": cid,
                    "evaluation_mode": "error",
                    "model_error": message,
                })

        # Persist successes after every batch.
        json_path.write_text(
            json.dumps(list(saved.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if args.pause and batch_no < len(batches):
            time.sleep(args.pause)

    if saved:
        result_df = pd.DataFrame(list(saved.values())).sort_values(
            "final_score", ascending=False
        )
        result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    failures_path.write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\nEDITORIAL EVALUATION FINISHED")
    print(f"Successful evaluations: {len(saved)}")
    print(f"Failed candidate entries in this run: {len(failures)}")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"Failures: {failures_path}")


if __name__ == "__main__":
    main()
