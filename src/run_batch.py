
"""
Run screenplay parsing, candidate generation and optional per-clip LLM evaluation (step 1 of run_all.py).

Can be called from:
1. Python:
   run_pipeline(
       input_dir="data/input",
       output_dir="outputs/raw/new_run",
       per_episode=12,
       use_gemini=False
   )

2. Terminal:
   python src/run_batch.py
   python src/run_batch.py --input data/input --output outputs/raw --gemini
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


# ---------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"

load_dotenv(BASE_DIR / ".env", override=False)  # shell/CLI values win over .env

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from parser import parse_directory
from candidate_generator import generate_candidates
from promo_detector import evaluate_candidate
from scoring import heuristic_score


# ---------------------------------------------------------------------
# Main reusable pipeline
# ---------------------------------------------------------------------

def run_pipeline(
    input_dir="data/input",
    output_dir="outputs/raw",
    per_episode=12,
    max_episodes=None,
    use_gemini=False,
):
    """
    Parse screenplay TXT files and generate ranked candidate promos.

    Parameters
    ----------
    input_dir : str
        Directory containing timestamped screenplay TXT files.

    output_dir : str
        Directory where raw results will be saved.

    per_episode : int
        Number of top heuristic candidates retained per episode.

    max_episodes : int or None
        Optional limit on the number of episodes to process.

    use_gemini : bool
        Whether to use Gemini during the initial candidate evaluation.

    Returns
    -------
    tuple[pd.DataFrame, dict]
        Generated candidate DataFrame and run summary.
    """

    if per_episode < 1:
        raise ValueError("per_episode must be at least 1.")

    if max_episodes is not None and max_episodes < 1:
        raise ValueError("max_episodes must be at least 1.")

    input_path = Path(input_dir)

    if not input_path.is_absolute():
        input_path = BASE_DIR / input_path

    output_path = Path(output_dir)

    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path

    processed_path = output_path / "processed"

    if not input_path.exists():
        raise FileNotFoundError(
            f"Screenplay input directory not found: {input_path}"
        )

    supported_files = [
        f for f in input_path.rglob("*")
        if f.is_file() and f.suffix.lower() in {".txt", ".srt", ".fountain"}
    ]
    if not supported_files:
        raise ValueError(
            f"No TXT, SRT, or Fountain files found in: {input_path}"
        )

    output_path.mkdir(parents=True, exist_ok=True)
    processed_path.mkdir(parents=True, exist_ok=True)

    total_start = time.time()

    print("\nLoading screenplay episodes...", flush=True)

    episodes = parse_directory(
        str(input_path),
        str(processed_path),
    )

    if max_episodes is not None:
        episodes = episodes[:max_episodes]

    if not episodes:
        raise ValueError(
            "No episodes could be parsed. Check the screenplay TXT format."
        )

    total_episodes = len(episodes)

    print(f"Found {total_episodes} episodes.", flush=True)

    results = []
    total_candidates = 0
    episode_summaries = []

    # -----------------------------------------------------------------
    # Process each episode
    # -----------------------------------------------------------------

    for episode_index, episode in enumerate(episodes, start=1):

        episode_start = time.time()

        episode_name = episode.get("episode", f"Episode {episode_index}")

        print(
            f"\nProcessing {episode_name} "
            f"({episode_index}/{total_episodes})...",
            flush=True,
        )

        candidates = generate_candidates(episode)

        if not candidates:
            print(
                f"No valid candidates generated for {episode_name}.",
                flush=True,
            )
            continue

        # Rank candidates using the existing baseline heuristic.
        candidates.sort(
            key=lambda candidate: heuristic_score(candidate).get(
                "baseline_score", 0
            ),
            reverse=True,
        )

        selected = candidates[:per_episode]

        print(
            f"Generated {len(candidates)} windows; "
            f"selected {len(selected)} candidates.",
            flush=True,
        )

        episode_successes = 0

        for candidate_index, candidate in enumerate(selected, start=1):

            total_candidates += 1
            candidate_start = time.time()

            print(
                f"  [{candidate_index}/{len(selected)}] "
                f"Evaluating candidate "
                f"{candidate.get('start')}–{candidate.get('end')}s...",
                flush=True,
            )

            try:
                result = evaluate_candidate(
                    candidate,
                    use_gemini=use_gemini,
                )

                if not isinstance(result, dict):
                    raise TypeError(
                        "evaluate_candidate() must return a dictionary."
                    )

                # Retain original candidate fields and evaluation fields.
                combined_result = {
                    **candidate,
                    **result,
                }

                results.append(combined_result)
                episode_successes += 1

                mode = combined_result.get(
                    "evaluation_mode", "unknown"
                )

                print(
                    f"  Completed in "
                    f"{time.time() - candidate_start:.1f}s | "
                    f"Mode: {mode}",
                    flush=True,
                )

                if combined_result.get("model_error"):
                    print(
                        f"  Evaluation warning: "
                        f"{combined_result['model_error']}",
                        flush=True,
                    )

            except Exception as exc:

                print(
                    f"  Candidate failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        episode_summaries.append({
            "episode": episode_name,
            "generated_candidates": len(candidates),
            "selected_candidates": len(selected),
            "successful_candidates": episode_successes,
        })

        print(
            f"{episode_name} completed in "
            f"{time.time() - episode_start:.1f}s.",
            flush=True,
        )

    # -----------------------------------------------------------------
    # Sort results
    # -----------------------------------------------------------------

    results.sort(
        key=lambda item: item.get("baseline_score", 0),
        reverse=True,
    )

    # -----------------------------------------------------------------
    # Save raw JSON
    # -----------------------------------------------------------------

    json_path = output_path / "promo_candidates_raw.json"

    json_path.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # Save CSV
    # -----------------------------------------------------------------

    result_df = pd.DataFrame(results)

    csv_path = output_path / "promo_ranking.csv"

    if not result_df.empty:
        result_df.to_csv(
            csv_path,
            index=False,
            encoding="utf-8-sig",
        )
    else:
        result_df.to_csv(
            csv_path,
            index=False,
            encoding="utf-8-sig",
        )

    # -----------------------------------------------------------------
    # Run summary
    # -----------------------------------------------------------------

    evaluation_modes = {}

    for result in results:
        mode = result.get("evaluation_mode", "unknown")
        evaluation_modes[mode] = evaluation_modes.get(mode, 0) + 1

    total_elapsed = time.time() - total_start

    summary = {
        "episodes_processed": total_episodes,
        "candidates_evaluated": len(results),
        "evaluation_modes": evaluation_modes,
        "per_episode_limit": per_episode,
        "gemini_enabled": use_gemini,
        "duration_seconds": round(total_elapsed, 2),
        "episode_summaries": episode_summaries,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    }

    summary_path = output_path / "run_summary.json"

    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # Final report
    # -----------------------------------------------------------------

    print("\n" + "=" * 55)
    print("PROMO DISCOVERY COMPLETED")
    print("=" * 55)

    print(f"Episodes processed: {total_episodes}")
    print(f"Candidates evaluated: {len(results)}")
    print(f"Evaluation modes: {evaluation_modes}")
    print(f"Total time: {total_elapsed:.1f} seconds")

    print(f"\nJSON output: {json_path}")
    print(f"CSV output: {csv_path}")
    print(f"Summary: {summary_path}")

    return result_df, summary


# ---------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------

def main():

    argument_parser = argparse.ArgumentParser(
        description="Generate screenplay-based promo candidates."
    )

    argument_parser.add_argument(
        "--input",
        default="data/input",
        help="Directory containing screenplay TXT files.",
    )

    argument_parser.add_argument(
        "--output",
        default="outputs/raw",
        help="Directory for generated results.",
    )

    argument_parser.add_argument(
        "--per-episode",
        type=int,
        default=12,
        help="Maximum candidates selected per episode.",
    )

    argument_parser.add_argument(
        "--max-episodes",
        type=int,
        default=None,
        help="Optional limit on episodes for a pilot run.",
    )

    argument_parser.add_argument(
        "--gemini",
        action="store_true",
        help="Enable Gemini evaluation in the initial pipeline.",
    )

    args = argument_parser.parse_args()

    if args.per_episode < 1:
        argument_parser.error("--per-episode must be at least 1.")

    if args.max_episodes is not None and args.max_episodes < 1:
        argument_parser.error("--max-episodes must be at least 1.")

    run_pipeline(
        input_dir=args.input,
        output_dir=args.output,
        per_episode=args.per_episode,
        max_episodes=args.max_episodes,
        use_gemini=args.gemini,
    )


if __name__ == "__main__":
    main()
