"""Regenerate frontend/src/data/promos.json from the Python pipeline outputs.

Usage (from the project root):
    python scripts/sync_frontend_data.py
    python scripts/sync_frontend_data.py --ranking outputs/ranked_promos/final_ranking.csv

Reads the final hybrid ranking plus data/processed/*.json (for dialogue-only WPM)
and writes the JSON snapshot the React app loads at startup.
"""

from __future__ import annotations

import argparse
import ast
import glob
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
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
    words = sum(
        len(e["text"].split())
        for e in selected
        if str(e.get("type", "")).upper() not in NON_SPOKEN
    )
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


def windows_generated(ranking_path: Path) -> int | None:
    """Total candidate windows the pipeline generated (from the run's raw/run_summary.json), if available."""
    summary = ranking_path.parent.parent / "raw" / "run_summary.json"
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
        return int(sum(e["generated_candidates"] for e in data["episode_summaries"])) or None
    except (OSError, KeyError, ValueError, TypeError):
        return None


def build(ranking_path: Path, processed_dir: Path, evaluations_path: Path, show_title: str = "") -> list[dict]:
    df = pd.read_csv(ranking_path, encoding="utf-8-sig")
    # final_ranking.csv's *_score columns are the LOCAL heuristic's; the per-dimension
    # scores Gemini gave live in editorial_evaluations.csv. The UI labels these Hook/Cliffhanger/
    # etc. next to the Gemini score, so show Gemini's.
    gem = pd.read_csv(evaluations_path, encoding="utf-8-sig").set_index("candidate_id")
    df = df[df["gemini_evaluated"] == True].sort_values("rank")  # noqa: E712
    events_by_file = load_events(processed_dir)
    total_windows = windows_generated(ranking_path)

    out = []
    for _, r in df.iterrows():
        events = events_by_file.get(r["episode_file"], [])
        out.append(
            {
                "id": r["candidate_id"],
                "show": show_title,
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
                "hookScore": num(gem.at[r["candidate_id"], "hook_score"]),
                "cliffhangerScore": num(gem.at[r["candidate_id"], "cliffhanger_score"]),
                "emotionalScore": num(gem.at[r["candidate_id"], "emotional_score"]),
                "standaloneScore": num(gem.at[r["candidate_id"], "standalone_score"]),
                "progressionScore": num(gem.at[r["candidate_id"], "progression_score"]),
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
    ap.add_argument("--ranking", default="outputs/ranked_promos/final_ranking.csv")
    ap.add_argument("--processed", default="data/processed")
    ap.add_argument("--evaluations", default="outputs/editorial/editorial_evaluations.csv")
    ap.add_argument("--output", default="frontend/src/data/promos.json")
    ap.add_argument("--show-title", default=config.SHOW_TITLE, help="drama name shown on the Home page")
    args = ap.parse_args()

    data = build(ROOT / args.ranking, ROOT / args.processed, ROOT / args.evaluations, args.show_title)
    out = ROOT / args.output
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(data)} promos -> {out}")


if __name__ == "__main__":
    main()
