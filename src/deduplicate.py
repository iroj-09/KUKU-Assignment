import argparse
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path as _Path

# Make the project-root config.py importable when running `python src/<script>.py`.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402


def overlap_ratio(a_start, a_end, b_start, b_end):
    intersection = max(
        0,
        min(a_end, b_end) - max(a_start, b_start)
    )

    shorter_duration = min(
        a_end - a_start,
        b_end - b_start
    )

    if shorter_duration <= 0:
        return 0

    return intersection / shorter_duration


def deduplicate(
    df,
    max_per_episode=3,
    overlap_threshold=0.50
):
    required = [
        "episode",
        "start",
        "end",
        "duration",
        "baseline_score"
    ]

    missing = [
        col for col in required
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    df = df.copy()

    for col in ["start", "end", "duration", "baseline_score"]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(subset=required)

    df = df[
        df["duration"].between(
            config.MIN_PROMO_SECONDS,
            config.MAX_PROMO_SECONDS
        )
        & (df["end"] > df["start"])
    ]

    selected = []

    for _episode, group in df.groupby("episode"):
        group = group.sort_values(
            "baseline_score",
            ascending=False,
            kind="stable"
        )

        episode_selected = []

        for _, candidate in group.iterrows():
            overlaps_existing = any(
                overlap_ratio(
                    candidate["start"],
                    candidate["end"],
                    existing["start"],
                    existing["end"]
                ) >= overlap_threshold
                for existing in episode_selected
            )

            if overlaps_existing:
                continue

            episode_selected.append(candidate)

            if len(episode_selected) >= max_per_episode:
                break

        selected.extend(episode_selected)

    result = pd.DataFrame(selected)

    if not result.empty:
        result = result.sort_values(
            ["baseline_score"],
            ascending=False
        ).reset_index(drop=True)

        result.insert(
            0,
            "rank",
            range(1, len(result) + 1)
        )

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        default="outputs/raw/promo_ranking.csv"
    )

    parser.add_argument(
        "--output",
        default="outputs/ranked_promos/promo_shortlist.csv"
    )

    parser.add_argument(
        "--max-per-episode",
        type=int,
        default=3
    )

    parser.add_argument(
        "--overlap-threshold",
        type=float,
        default=0.50
    )

    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    input_path = root / args.input
    output_path = root / args.output

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    df = pd.read_csv(input_path)

    shortlist = deduplicate(
        df,
        max_per_episode=args.max_per_episode,
        overlap_threshold=args.overlap_threshold
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shortlist.to_csv(output_path, index=False)

    print("DEDUPLICATION COMPLETED")
    print("=" * 50)
    print(f"Input candidates: {len(df)}")
    print(f"Shortlisted candidates: {len(shortlist)}")
    print(f"Removed candidates: {len(df) - len(shortlist)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()