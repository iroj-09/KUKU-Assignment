"""Turn a filled-in human_check_sheet.csv into real accuracy numbers.

    python scripts/score_human_check.py                      # outputs/human_check_sheet.csv
    python scripts/score_human_check.py path/to/sheet.csv

Reports, over the rows where a person gave a Y/N verdict:
  - how often the model's hook / cliffhanger / stand-alone call was agreed with
  - precision@10: of the top-ranked promos, how many would the person actually post
  - whether the top-ranked clips are more postable than the lowest-ranked ones (does ranking help?)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def yes(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper().str[:1].map({"Y": True, "N": False})


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "outputs" / "human_check_sheet.csv"
    df = pd.read_csv(path, encoding="utf-8-sig")
    cols = {
        "hook": "human_hook_ok (Y/N)",
        "cliffhanger": "human_cliffhanger_ok (Y/N)",
        "stand-alone": "human_standalone_ok (Y/N)",
        "would post": "human_would_post (Y/N)",
    }
    verdicts = {k: yes(df[v]) for k, v in cols.items()}
    done = pd.concat(verdicts, axis=1).notna().all(axis=1)
    print(f"Rows with a complete verdict: {int(done.sum())} of {len(df)}")
    if not done.any():
        print("Fill the four human_* columns with Y or N first.")
        return

    for name, v in verdicts.items():
        v = v[done]
        print(f"  {name:12s} agreed with the model: {int(v.sum())}/{len(v)} ({100 * v.mean():.0f}%)")

    post = verdicts["would post"]
    top = df[done & (df["why_in_sheet"] == "top ranked")]
    if len(top):
        p = post[top.index].mean()
        print(f"  precision@top-ranked: {int(post[top.index].sum())}/{len(top)} ({100 * p:.0f}%) would actually be posted")
    low = df[done & (df["why_in_sheet"] == "lowest ranked")]
    if len(top) and len(low):
        print(f"  lowest-ranked would be posted: {int(post[low.index].sum())}/{len(low)} "
              f"({100 * post[low.index].mean():.0f}%) -> ranking {'helps' if post[top.index].mean() > post[low.index].mean() else 'does NOT help'}")
    wrong = df[done & (~verdicts['hook'].fillna(True) | ~verdicts['cliffhanger'].fillna(True))]
    if len(wrong):
        print("\nClips where the person disagreed with the hook or cliffhanger:")
        for _, r in wrong.iterrows():
            print(f"  #{int(r['rank'])} {r['episode']} {r['start']}-{r['end']}: {r.get('notes', '')}")


if __name__ == "__main__":
    main()
