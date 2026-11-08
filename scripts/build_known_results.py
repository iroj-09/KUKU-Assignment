"""Let the app show the saved pipeline results when the same screenplay files are uploaded again.

    python scripts/build_known_results.py
    python scripts/build_known_results.py --input data/input --run submission/raw_outputs

For every file in the input folder it fingerprints the file (SHA-256 of its bytes) and stores the promos the
Python pipeline found in it (the run's final ranking + the model's per-clip evaluation). Uploading the same
file in the app then shows exactly those promos instead of re-deriving them in the browser; any other file is
processed in the browser as before.

Writes frontend/src/data/known_results.json. That file contains screenplay text, so it is git-ignored: a copy
of the app built from a clean clone (e.g. on Vercel) simply has no saved results. Do not publish a build made
on this machine.
"""

from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NON_SPOKEN = {"CAMERA", "ACTION", "SOUND FX", "SOUND"}


def load_events(processed_dir: Path) -> dict[str, list[dict]]:
    episodes = {}
    for f in glob.glob(str(processed_dir / "*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        events = []
        for scene in d.get("scenes", []):
            for e in scene.get("events", []):
                if (e.get("text") or "").strip() and e["end"] > e["start"]:
                    events.append(e)
        episodes[d["episode_file"]] = events
    return episodes


def spoken_wpm(events: list[dict], start: float, end: float, duration: float) -> float:
    selected = [e for e in events if e["end"] > start + 0.01 and e["start"] < end - 0.01]
    words = sum(len(e["text"].split()) for e in selected if str(e.get("type", "")).upper() not in NON_SPOKEN)
    return round(words / max(1.0, duration) * 60, 1)


def parse_risks(value) -> list[str]:
    if isinstance(value, list):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    try:
        parsed = ast.literal_eval(str(value))
        return [str(x) for x in parsed] if isinstance(parsed, (list, tuple)) else [str(parsed)]
    except (ValueError, SyntaxError):
        return [str(value)] if str(value).strip() else []


def num(value, default=0.0):
    return float(value) if pd.notna(value) else default


def opt(value):
    """Keep missing values as null (the UI distinguishes 'absent' from 0)."""
    return None if pd.isna(value) else value


def windows_generated(run_dir: Path) -> int | None:
    try:
        data = json.loads((run_dir / "raw" / "run_summary.json").read_text(encoding="utf-8"))
        return int(sum(e["generated_candidates"] for e in data["episode_summaries"])) or None
    except (OSError, KeyError, ValueError, TypeError):
        return None


def build_candidates(run_dir: Path, processed_dir: Path) -> list[dict]:
    df = pd.read_csv(run_dir / "ranked_promos" / "final_ranking.csv", encoding="utf-8-sig")
    # final_ranking.csv's *_score columns are the local heuristic's; the per-dimension scores the model gave
    # live in editorial_evaluations.csv, and those are the ones shown next to the model score.
    gem = pd.read_csv(run_dir / "editorial" / "editorial_evaluations.csv", encoding="utf-8-sig").set_index("candidate_id")
    df = df[df["gemini_evaluated"] == True].sort_values("rank")  # noqa: E712
    events_by_file = load_events(processed_dir)
    total_windows = windows_generated(run_dir)

    out = []
    for _, r in df.iterrows():
        events = events_by_file.get(r["episode_file"], [])
        cid = r["candidate_id"]
        out.append(
            {
                "id": cid,
                "show": "",
                "showWindows": total_windows,
                "rank": int(r["rank"]),
                "episode": r["episode"],
                "episodeFile": r["episode_file"],
                "clipStart": num(r["clip_start"]),
                "clipEnd": num(r["clip_end"]),
                "duration": num(r["duration"]),
                "hybridScore": round(num(r["ranking_score"]), 2),
                "geminiScore": num(r["final_score"]),
                "localScore": num(r["local_editorial_score"]),
                "compliance": r["timestamp_compliance"],
                "isPromising": bool(r["is_promising"]),
                "hook": opt(r["hook"]),
                "hookTimestamp": opt(r["hook_timestamp"]),
                "cliffhanger": opt(r["cliffhanger"]),
                "cliffhangerTimestamp": opt(r["cliffhanger_timestamp"]),
                "whyItWorks": r["why_it_works"],
                "standaloneContext": r["standalone_context"],
                "risks": parse_risks(r["risks"]),
                "hookScore": num(gem.at[cid, "hook_score"]),
                "cliffhangerScore": num(gem.at[cid, "cliffhanger_score"]),
                "emotionalScore": num(gem.at[cid, "emotional_score"]),
                "standaloneScore": num(gem.at[cid, "standalone_score"]),
                "progressionScore": num(gem.at[cid, "progression_score"]),
                "openingTranscript": r["opening_transcript"],
                "endingTranscript": r["ending_transcript"],
                "fullTranscript": r["full_transcript"],
                "wpm": spoken_wpm(events, num(r["clip_start"]), num(r["clip_end"]), num(r["duration"])),
                "wordCount": len(str(r["full_transcript"]).split()),
                "reviewStatus": r["review_status"],
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="data/input", help="folder with the screenplay files the run was made from")
    ap.add_argument("--run", default="submission/raw_outputs", help="pipeline output folder (ranked_promos/, editorial/, raw/)")
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--output", default="frontend/src/data/known_results.json")
    args = ap.parse_args()

    candidates = build_candidates(ROOT / args.run, ROOT / args.processed)
    by_file: dict[str, list[dict]] = {}
    for c in candidates:
        by_file.setdefault(c["episodeFile"], []).append(c)

    known: dict[str, dict] = {}
    for f in sorted((ROOT / args.input).glob("*.txt")):
        promos = by_file.get(f.stem, []) or by_file.get(f.name, [])
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        if promos:
            known[digest] = {"file": f.name, "candidates": promos}

    matched = sum(len(v["candidates"]) for v in known.values())
    if matched != len(candidates):
        print(f"WARNING: {len(candidates) - matched} promos belong to files not found in {args.input}", file=sys.stderr)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(known, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote saved results for {len(known)} files ({matched} promos) -> {out}")


if __name__ == "__main__":
    main()
