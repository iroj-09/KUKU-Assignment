"""Run the whole promo-discovery pipeline on a folder of screenplays with one command.

    python run_all.py --input data/input
    python run_all.py --input path/to/new_show --output outputs/runs/new_show
    python run_all.py --input path/to/new_show --no-llm            # free, no API key needed
    python run_all.py --input path/to/new_show --limit 10          # only ask the model about 10 clips

Steps (each is also runnable on its own from src/):
  1. candidate windows   src/run_batch.py              parse screenplays, build 20-60s beat-aligned windows
  2. de-duplicate        src/deduplicate.py            drop overlapping windows, cap per episode
  3. local scores        src/local_editorial_scorer.py cheap rule-based score
  4. evidence            src/prepare_editorial_data.py opening-3s / closing-5s evidence per window
  5. merge               src/merge_editorial_data.py
  6. LLM evaluation      src/editorial_evaluator.py    hook / cliffhanger / stakes / standalone (swappable model)
  7. final ranking       src/final_ranker.py           70% model + 30% local, timestamp compliance check
  8. submission export   src/export_submission.py       promos_submission.json / .csv / .md

The model is chosen with environment variables (see src/llm.py), e.g.
    LLM_PROVIDER=openai LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... python run_all.py --input ...
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
sys.path.insert(0, str(ROOT))
import config  # noqa: E402


def step(label: str, args: list[str], total: int, index: int) -> None:
    print(f"\n[{index}/{total}] {label}", flush=True)
    started = time.time()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([PY, *args], cwd=ROOT, env=env)
    if result.returncode != 0:
        sys.exit(f"\nStep failed: {label} (exit code {result.returncode}). See the output above.")
    print(f"    done in {time.time() - started:.1f}s", flush=True)


def csv_rows(path: Path) -> int:
    """Data rows in a CSV (0 when the file is missing or empty)."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except (FileNotFoundError, UnicodeDecodeError):
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="folder with screenplay files (.txt / .srt / .fountain)")
    ap.add_argument("--output", default=None, help="run folder (default: outputs/runs/run_<timestamp>)")
    ap.add_argument("--per-episode", type=int, default=12, help="candidates kept per episode before de-duplication")
    ap.add_argument("--max-per-episode", type=int, default=3, help="promos kept per episode after de-duplication")
    ap.add_argument("--max-episodes", type=int, default=None, help="process only the first N episodes (quick test)")
    ap.add_argument("--model", default=None, help="model name for this run (overrides .env), e.g. gpt-4o-mini")
    ap.add_argument("--provider", default=None, help="only if auto-detection from key/model guesses wrong")
    ap.add_argument("--no-llm", action="store_true", help="skip the model: rank by the local heuristic only (free)")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N shortlisted clips with the model")
    ap.add_argument("--batch-size", type=int, default=5, help="clips per model request")
    args = ap.parse_args()

    # Shell/CLI values beat .env, so these also reach every pipeline step (they inherit this environment).
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider

    input_dir = Path(args.input).resolve()
    if not input_dir.is_dir() or not any(input_dir.iterdir()):
        sys.exit(f"Input folder not found or empty: {input_dir}")

    run_dir = Path(args.output).resolve() if args.output else (
        ROOT / "outputs" / "runs" / f"run_{datetime.now():%Y%m%d_%H%M%S}"
    )
    raw, editorial, ranked = run_dir / "raw", run_dir / "editorial", run_dir / "ranked_promos"
    for d in (raw, editorial, ranked):
        d.mkdir(parents=True, exist_ok=True)

    if not args.no_llm:
        sys.path.insert(0, str(ROOT / "src"))
        import llm

        try:
            llm.require_configured()
        except RuntimeError as err:
            sys.exit(f"{err}\nSet the credentials, or run with --no-llm for a free local-only ranking.")
        print(f"Model: {llm.describe()}")

    total = 6 if args.no_llm else 8
    started = time.time()

    batch = ["src/run_batch.py", "--input", str(input_dir), "--output", str(raw),
             "--per-episode", str(args.per_episode)]
    if args.max_episodes:
        batch += ["--max-episodes", str(args.max_episodes)]
    step("Candidate windows", batch, total, 1)

    if csv_rows(raw / "promo_ranking.csv") == 0:
        sys.exit(
            "\nNo promo windows could be built from this input.\n"
            f"A promo needs {config.MIN_PROMO_SECONDS}-{config.MAX_PROMO_SECONDS} s of continuous, timestamped screenplay, "
            "so each episode must contain at least that much and its timestamps must be readable.\n"
            "Check that the files use a supported format (Kuku screenplay .txt, .srt or .fountain) with "
            "timestamps in mm:ss or hh:mm:ss, and that the episodes are not shorter than the minimum clip length "
            "(MIN_PROMO_SECONDS in .env)."
        )

    shortlist = raw / "promo_shortlist.csv"
    step("De-duplicate", ["src/deduplicate.py", "--input", str(raw / "promo_ranking.csv"),
                          "--output", str(shortlist), "--max-per-episode", str(args.max_per_episode),
                          "--overlap-threshold", "0.50"], total, 2)
    if csv_rows(shortlist) == 0:
        sys.exit("\nAfter removing overlaps there are no promo candidates left. Try a larger --per-episode.")

    step("Local scores", ["src/local_editorial_scorer.py", "--input", str(shortlist),
                          "--output-dir", str(editorial), "--top", "0"], total, 3)
    step("Evidence extraction", ["src/prepare_editorial_data.py", "--input", str(shortlist),
                                 "--screenplays", str(input_dir), "--output-dir", str(editorial),
                                 "--top", "0"], total, 4)
    merged = editorial / "merged_editorial_data.csv"
    step("Merge", ["src/merge_editorial_data.py", "--evidence", str(editorial / "editorial_evidence.csv"),
                   "--scores", str(editorial / "local_editorial_scores.csv"), "--output", str(merged)],
         total, 5)

    if args.no_llm:
        step("Submission export (local only)",
             ["src/export_submission.py", "--local-only", "--merged", str(merged),
              "--output-dir", str(ranked)], total, 6)
    else:
        evaluator = ["src/editorial_evaluator.py", "--input", str(merged), "--output-dir", str(editorial),
                     "--batch-size", str(args.batch_size), "--pause", "2"]
        if args.limit:
            evaluator += ["--limit", str(args.limit)]
        step("LLM evaluation", evaluator, total, 6)
        evaluations = editorial / "editorial_evaluations.json"
        step("Final ranking", ["src/final_ranker.py", "--input", str(merged), "--evaluations", str(evaluations),
                               "--output-dir", str(ranked)], total, 7)
        step("Submission export", ["src/export_submission.py", "--ranking", str(ranked / "final_ranking.csv"),
                                   "--evaluations", str(evaluations), "--output-dir", str(ranked)], total, 8)

    print(f"\nFinished in {time.time() - started:.0f}s. Results: {ranked}")
    print(f"  Readable list: {ranked / 'promos_submission.md'}")
    print(f"  Full data:     {ranked / 'promos_submission.csv'}  (and .json)")


if __name__ == "__main__":
    main()
