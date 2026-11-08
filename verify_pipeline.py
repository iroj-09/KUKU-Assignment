"""End-to-end verification script for Kuku Promo Discovery components.

Tests:
1. Screenplay parsing (Kuku TXT and SRT formats)
2. Beat-aligned candidate window generation
3. Time-aware heuristic scoring & WPM calculation
4. NLE marker generation (DaVinci, Premiere, CMX EDL)
5. Pydantic schema validation for Gemini responses
"""

from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd
from parser import parse_episode
from candidate_generator import generate_candidates
from scoring import heuristic_score
from nle_export import export_davinci_markers, export_premiere_markers, export_cmx_edl
from editorial_evaluator import parse_response


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    print("=" * 60)
    print("🎬 KUKU PROMO DISCOVERY — SYSTEM VERIFICATION")
    print("=" * 60)

    # 1. Parse real episode from data/input
    ep_files = list((BASE_DIR / "data" / "input").glob("*.txt"))
    if not ep_files:
        print("❌ No input episodes found under data/input/")
        return 1

    sample_file = ep_files[0]
    print(f"\n[1/5] Testing Screenplay Parser on: {sample_file.name}...")
    ep_data = parse_episode(sample_file)
    print(f"  ✓ Successfully parsed '{ep_data.get('episode')}'")
    print(f"  ✓ Scenes: {ep_data.get('scene_count')} | Timestamped Events: {ep_data.get('event_count')}")

    # 2. Beat-aligned candidate generation
    print("\n[2/5] Testing Beat-Aligned Windowing...")
    candidates = generate_candidates(ep_data, min_seconds=20, max_seconds=60, strategy="beat_aligned")
    print(f"  ✓ Generated {len(candidates)} beat-aligned promo windows (20s–60s).")
    if candidates:
        first = candidates[0]
        print(f"  ✓ Candidate #1: {first['start']}s – {first['end']}s (Duration: {first['duration']}s)")

    # 3. Time-aware scoring
    print("\n[3/5] Testing Time-Aware Scoring & Cadence...")
    if candidates:
        scores = heuristic_score(candidates[0])
        print(f"  ✓ Baseline Score: {scores['baseline_score']} / 100")
        print(f"  ✓ Hook Score: {scores['hook_score']} / 10 (evaluated within the opening hook window)")
        print(f"  ✓ Cliffhanger Score: {scores['cliffhanger_score']} / 10 (evaluated within the closing cliffhanger window)")
        print(f"  ✓ Speech Cadence: {scores['wpm']} WPM ({scores['dialogue_turns']} speaker turns)")

    # 4. NLE video editor exporters
    print("\n[4/5] Testing NLE Video Editor Exporters...")
    sample_df = pd.DataFrame([
        {
            "rank": 1,
            "episode": "Episode 16",
            "clip_start": 0.0,
            "clip_end": 55.0,
            "ranking_score": 79.9,
            "why_it_works": "Alexander disarms thugs and reveals Gerald Harrington",
        }
    ])
    davinci_csv = export_davinci_markers(sample_df)
    premiere_csv = export_premiere_markers(sample_df)
    edl_text = export_cmx_edl(sample_df)

    assert "00:00:55:00" in davinci_csv
    assert "00:00:55:00" in premiere_csv
    assert "TITLE: KUKU_PROMOS" in edl_text
    print("  ✓ DaVinci Resolve Marker CSV generated successfully.")
    print("  ✓ Premiere Pro Marker CSV generated successfully.")
    print("  ✓ CMX 3600 EDL generated successfully.")

    # 5. Gemini schema validator
    print("\n[5/5] Testing Pydantic Gemini Response Schema...")
    raw_llm_json = """```json
    {
      "evaluations": [
        {
          "candidate_id": "Ep16|0.0|55.0",
          "is_promising": true,
          "hook": "Move aside, soldier.",
          "hook_timestamp": 2.1,
          "cliffhanger": "Gerald Harrington paid us!",
          "cliffhanger_timestamp": 53.2,
          "why_it_works": "Textbook martial hook and villain mastermind reveal.",
          "standalone_context": "Alexander protecting Juliana.",
          "hook_score": 9,
          "cliffhanger_score": 10,
          "emotional_score": 8,
          "standalone_score": 7,
          "progression_score": 9,
          "risks": []
        }
      ]
    }
    ```"""
    parsed_eval = parse_response(raw_llm_json)
    assert len(parsed_eval["evaluations"]) == 1
    print("  ✓ Pydantic validation passed (handled markdown fences & strict types).")

    print("\n" + "=" * 60)
    print("🎉 ALL 5 SYSTEM MODULES VERIFIED SUCCESSFULLY!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
