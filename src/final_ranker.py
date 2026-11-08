"""Combine local heuristic and Gemini editorial scores for promo review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path as _Path

# Make the project-root config.py importable when running `python src/<script>.py`.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Share of the final score that comes from the cheap local heuristic. Default 30%.
# Tune with LOCAL_WEIGHT (0-1) once the human check sheet shows how useful the heuristic is.
LOCAL_WEIGHT = min(1.0, max(0.0, config.LOCAL_WEIGHT))
GEMINI_WEIGHT = 1.0 - LOCAL_WEIGHT
TOP_N = 10


def make_candidate_id(episode, start, end) -> str:
    return f"{episode}|{float(start)}|{float(end)}"


def load_evaluations(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Evaluation file not found: {path}"
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError(
            "Editorial evaluations JSON must contain a list."
        )

    if not data:
        return pd.DataFrame()

    eval_df = pd.DataFrame(data)

    if "candidate_id" not in eval_df.columns:
        raise ValueError(
            "Editorial evaluations are missing candidate_id."
        )

    eval_df = eval_df.drop_duplicates(
        "candidate_id",
        keep="last"
    )

    return eval_df


def rank_candidates(
    input_path: Path,
    evaluations_path: Path,
    output_dir: Path,
) -> pd.DataFrame:

    input_path = Path(input_path)
    evaluations_path = Path(evaluations_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input file not found: {input_path}"
        )

    df = pd.read_csv(input_path)

    required = [
        "episode",
        "clip_start",
        "clip_end",
        "local_editorial_score"
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns in merged editorial data: {missing}"
        )

    df = df.copy()

    for col in [
        "clip_start",
        "clip_end",
        "local_editorial_score"
    ]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=[
            "episode",
            "clip_start",
            "clip_end",
            "local_editorial_score"
        ]
    )

    df["duration_seconds"] = (
        df["clip_end"] - df["clip_start"]
    )

    df["duration_valid"] = (
        df["duration_seconds"].between(20, 60)
    )

    df["candidate_id"] = df.apply(
        lambda row: make_candidate_id(
            row["episode"],
            row["clip_start"],
            row["clip_end"]
        ),
        axis=1
    )

    if df["candidate_id"].duplicated().any():
        raise ValueError(
            "Duplicate candidate IDs found in merged input."
        )

    # Load Gemini evaluations.
    eval_df = load_evaluations(evaluations_path)

    if eval_df.empty:
        raise ValueError(
            "No Gemini evaluations found. "
            "Cannot generate a final hybrid ranking."
        )

    if "evaluation_mode" in eval_df.columns:
        eval_df = eval_df[
            eval_df["evaluation_mode"].isin(["gemini", "llm"])
        ].copy()

    if eval_df["candidate_id"].duplicated().any():
        raise ValueError(
            "Duplicate Gemini candidate IDs found."
        )

    keep = [
        "candidate_id",
        "final_score",
        "timestamp_compliance",
        "hook_timestamp_valid",
        "cliffhanger_timestamp_valid",
        "hook",
        "hook_timestamp",
        "cliffhanger",
        "cliffhanger_timestamp",
        "why_it_works",
        "standalone_context",
        "risks",
        "is_promising",
        "evaluation_mode",
        "llm_model",
    ]

    eval_df = eval_df[
        [col for col in keep if col in eval_df.columns]
    ]

    # The merged input already carries the local scorer's evaluation_mode;
    # rename it so it does not collide with Gemini's (avoids _x/_y suffixes).
    if "evaluation_mode" in df.columns:
        df = df.rename(
            columns={"evaluation_mode": "local_evaluation_mode"}
        )

    df = df.merge(
        eval_df,
        on="candidate_id",
        how="left",
        validate="one_to_one"
    )

    if "final_score" not in df.columns:
        df["final_score"] = pd.NA

    df["final_score"] = pd.to_numeric(
        df["final_score"],
        errors="coerce"
    )

    df["gemini_evaluated"] = (
        df["final_score"].notna()
    )

    # Require actual Gemini evaluation for final ranking.
    if int(df["gemini_evaluated"].sum()) == 0:
        raise ValueError(
            "No candidates matched the Gemini evaluations. "
            "Check candidate IDs."
        )

    # Recalculate timestamp compliance independently.
    if "hook_timestamp" not in df.columns:
        df["hook_timestamp"] = pd.NA

    if "cliffhanger_timestamp" not in df.columns:
        df["cliffhanger_timestamp"] = pd.NA

    df["hook_timestamp"] = pd.to_numeric(
        df["hook_timestamp"],
        errors="coerce"
    )

    df["cliffhanger_timestamp"] = pd.to_numeric(
        df["cliffhanger_timestamp"],
        errors="coerce"
    )

    hook_valid = (
        df["hook_timestamp"].notna()
        & (df["hook_timestamp"] >= df["clip_start"])
        & (
            df["hook_timestamp"]
            <= (df["clip_start"] + config.HOOK_WINDOW_SECONDS).clip(
                upper=df["clip_end"]
            )
        )
    )

    cliffhanger_valid = (
        df["cliffhanger_timestamp"].notna()
        & (
            df["cliffhanger_timestamp"]
            >= (df["clip_end"] - config.CLIFFHANGER_WINDOW_SECONDS).clip(
                lower=df["clip_start"]
            )
        )
        & (
            df["cliffhanger_timestamp"]
            <= df["clip_end"]
        )
    )

    df["hook_timestamp_valid"] = hook_valid.where(
        df["gemini_evaluated"],
        pd.NA
    )

    df["cliffhanger_timestamp_valid"] = (
        cliffhanger_valid.where(
            df["gemini_evaluated"],
            pd.NA
        )
    )

    df["timestamp_compliance"] = "UNVERIFIED"

    df.loc[
        df["gemini_evaluated"]
        & hook_valid
        & cliffhanger_valid,
        "timestamp_compliance"
    ] = "PASS"

    df.loc[
        df["gemini_evaluated"]
        & (hook_valid ^ cliffhanger_valid),
        "timestamp_compliance"
    ] = "PARTIAL"

    df.loc[
        df["gemini_evaluated"]
        & ~hook_valid
        & ~cliffhanger_valid,
        "timestamp_compliance"
    ] = "FAIL"

    # Hybrid ranking.
    df["ranking_score"] = pd.NA

    df["ranking_basis"] = (
        "Local heuristic only — provisional"
    )

    evaluated = df["gemini_evaluated"]

    df.loc[evaluated, "ranking_score"] = (
        GEMINI_WEIGHT * df.loc[
            evaluated, "final_score"
        ]
        + LOCAL_WEIGHT * df.loc[
            evaluated, "local_editorial_score"
        ]
    )

    df.loc[evaluated, "ranking_basis"] = (
        f"{GEMINI_WEIGHT:.0%} model editorial + {LOCAL_WEIGHT:.0%} local heuristic"
    )

    df.loc[~evaluated, "ranking_score"] = (
        df.loc[~evaluated, "local_editorial_score"]
    )

    df["review_status"] = "Pending human review"

    df["ranking_method"] = (
        "Hybrid where Gemini evaluation exists"
    )

    df["evaluation_group"] = (
        df["gemini_evaluated"].map({
            True: "Gemini evaluated",
            False: "Provisional — local only"
        })
    )

    # Evaluated candidates are ranked first.
    df = df.sort_values(
        [
            "gemini_evaluated",
            "duration_valid",
            "ranking_score"
        ],
        ascending=[False, False, False],
        na_position="last"
    ).reset_index(drop=True)

    df["rank"] = range(1, len(df) + 1)

    # Save outputs.
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    full_path = output_dir / "final_ranking.csv"

    df.to_csv(
        full_path,
        index=False,
        encoding="utf-8-sig"
    )

    # Only valid-duration candidates enter the review shortlist.
    valid = df[
        df["duration_valid"]
    ].copy()

    evaluated_valid = valid[
        valid["gemini_evaluated"]
    ]

    pending_valid = valid[
        ~valid["gemini_evaluated"]
    ]

    shortlist = pd.concat(
        [
            evaluated_valid,
            pending_valid
        ],
        ignore_index=True
    ).head(TOP_N)

    shortlist_path = (
        output_dir / "top_10_for_review.csv"
    )

    shortlist.to_csv(
        shortlist_path,
        index=False,
        encoding="utf-8-sig"
    )

    # Validation summary.
    print("\n========== FINAL RANKING ==========")

    print("Total candidates:", len(df))
    print(
        "Valid duration:",
        int(df["duration_valid"].sum())
    )
    print(
        "Gemini evaluated:",
        int(df["gemini_evaluated"].sum())
    )
    print(
        "Provisional local-only:",
        int((~df["gemini_evaluated"]).sum())
    )
    print(
        "Candidates for review:",
        len(shortlist)
    )

    print("\nTimestamp compliance:")
    print(
        df["timestamp_compliance"].value_counts().to_string()
    )

    print("\nTop candidates:")

    display_cols = [
        "rank",
        "episode",
        "clip_start",
        "clip_end",
        "duration_seconds",
        "final_score",
        "local_editorial_score",
        "ranking_score",
        "timestamp_compliance",
        "evaluation_group"
    ]

    print(
        shortlist[
            [
                col for col in display_cols
                if col in shortlist.columns
            ]
        ].to_string(index=False)
    )

    print("\nSaved:")
    print(full_path)
    print(shortlist_path)

    return df


def main():

    parser = argparse.ArgumentParser(
        description="Generate final hybrid promo ranking."
    )

    parser.add_argument(
        "--input",
        default="outputs/editorial/merged_editorial_data.csv"
    )

    parser.add_argument(
        "--evaluations",
        default="outputs/editorial/editorial_evaluations.json"
    )

    parser.add_argument(
        "--output-dir",
        default="outputs/ranked_promos"
    )

    args = parser.parse_args()

    rank_candidates(
        ROOT / args.input,
        ROOT / args.evaluations,
        ROOT / args.output_dir
    )


if __name__ == "__main__":
    main()