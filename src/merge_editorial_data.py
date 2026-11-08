import argparse
from pathlib import Path

import pandas as pd


def merge_editorial_data(
    evidence_path,
    scores_path,
    output_path
):
    evidence_path = Path(evidence_path)
    scores_path = Path(scores_path)
    output_path = Path(output_path)

    if not evidence_path.exists():
        raise FileNotFoundError(evidence_path)

    if not scores_path.exists():
        raise FileNotFoundError(scores_path)

    evidence = pd.read_csv(evidence_path)
    scores = pd.read_csv(scores_path)

    evidence_required = [
        "episode", "clip_start", "clip_end"
    ]

    scores_required = [
        "episode", "start", "end",
        "local_editorial_score"
    ]

    for col in evidence_required:
        if col not in evidence.columns:
            raise ValueError(
                f"Evidence file missing column: {col}"
            )

    for col in scores_required:
        if col not in scores.columns:
            raise ValueError(
                f"Score file missing column: {col}"
            )

    evidence = evidence.copy()
    scores = scores.copy()

    evidence["episode"] = evidence["episode"].astype(str).str.strip()
    scores["episode"] = scores["episode"].astype(str).str.strip()

    evidence["clip_start"] = pd.to_numeric(
        evidence["clip_start"], errors="coerce"
    )
    evidence["clip_end"] = pd.to_numeric(
        evidence["clip_end"], errors="coerce"
    )

    scores["start"] = pd.to_numeric(
        scores["start"], errors="coerce"
    )
    scores["end"] = pd.to_numeric(
        scores["end"], errors="coerce"
    )

    evidence = evidence.dropna(
        subset=["episode", "clip_start", "clip_end"]
    )

    scores = scores.dropna(
        subset=["episode", "start", "end"]
    )

    if scores.duplicated(
        ["episode", "start", "end"]
    ).any():
        raise ValueError(
            "Duplicate candidate keys found in score file."
        )

    if evidence.duplicated(
        ["episode", "clip_start", "clip_end"]
    ).any():
        raise ValueError(
            "Duplicate candidate keys found in evidence file."
        )

    # Remove the score copied into evidence during preparation.
    # The authoritative score comes from local_editorial_scores.csv.
    evidence = evidence.drop(
        columns=["local_editorial_score"],
        errors="ignore"
    )

    # Columns present in both files (e.g. `duration`) would be suffixed _x/_y by the merge
    # and break everything downstream that expects the plain name. The evidence file's
    # copy is kept; `episode` is a merge key and handled by the merge itself.
    shared = [c for c in scores.columns if c in evidence.columns and c != "episode"]
    if shared:
        scores = scores.drop(columns=shared)

    merged = evidence.merge(
        scores,
        left_on=["episode", "clip_start", "clip_end"],
        right_on=["episode", "start", "end"],
        how="left",
        validate="one_to_one"
    )

    missing = merged["local_editorial_score"].isna().sum()

    print("\n========== MERGE VALIDATION ==========")
    print(f"Evidence candidates: {len(evidence)}")
    print(f"Score candidates: {len(scores)}")
    print(f"Merged candidates: {len(merged)}")
    print(f"Missing editorial scores: {missing}")

    if missing:
        unmatched = merged[
            merged["local_editorial_score"].isna()
        ][["episode", "clip_start", "clip_end"]]

        print("\nUnmatched candidates:")
        print(unmatched.to_string(index=False))

        raise ValueError(
            "Some evidence candidates have no matching local score."
        )

    merged = merged.drop(columns=["start", "end"])

    merged = merged.sort_values(
        "local_editorial_score",
        ascending=False
    ).reset_index(drop=True)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    merged.to_csv(output_path, index=False)

    print("\nTop 10 candidates:")
    print(
        merged[
            [
                "episode",
                "clip_start",
                "clip_end",
                "local_editorial_score"
            ]
        ].head(10).to_string(index=False)
    )

    print(f"\nSaved successfully: {output_path}")

    return merged


def main():
    root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Merge timestamped evidence and local editorial scores."
    )

    parser.add_argument(
        "--evidence",
        default="outputs/editorial/editorial_evidence.csv"
    )

    parser.add_argument(
        "--scores",
        default="outputs/editorial/local_editorial_scores.csv"
    )

    parser.add_argument(
        "--output",
        default="outputs/editorial/merged_editorial_data.csv"
    )

    args = parser.parse_args()

    merge_editorial_data(
        root / args.evidence,
        root / args.scores,
        root / args.output
    )


if __name__ == "__main__":
    main()