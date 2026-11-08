"""Where does the tool pick badly? Build an evidence-based quality report from a finished run.

    python scripts/quality_report.py                       # uses outputs/
    python scripts/quality_report.py --run outputs/runs/run_X

Writes into the run folder:
  quality_report.md          measured failure modes, with the clips that show them
  human_check_sheet.csv      ~20 clips for a person to verify (blank verdict columns)

IMPORTANT: everything in quality_report.md is measured from the model's and the heuristic's
own outputs. That shows where they disagree or look weak, not whether either is RIGHT.
Ground truth comes from a person filling human_check_sheet.csv, then
`python scripts/score_human_check.py`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRIOR_CONTEXT = re.compile(r"prior|earlier|previous|backstory|context of|relies (?:heavily )?on|requires knowledge", re.I)


def episode_no(name: str) -> int:
    m = re.search(r"(\d+)", str(name))
    return int(m.group(1)) if m else 0


def md_table(rows: list[list], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def short(text, n=110) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "/")
    return text if len(text) <= n else text[: n - 1] + "…"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="outputs", help="run folder containing editorial/ and ranked_promos/")
    ap.add_argument("--episodes-total", type=int, default=None,
                    help="how many episodes were in the input (default: distinct episodes in the shortlist)")
    args = ap.parse_args()

    run = (ROOT / args.run).resolve()
    final = pd.read_csv(run / "ranked_promos" / "final_ranking.csv", encoding="utf-8-sig")
    evals = pd.DataFrame(json.loads((run / "editorial" / "editorial_evaluations.json").read_text(encoding="utf-8")))
    dims = ["hook_score", "cliffhanger_score", "emotional_score", "standalone_score", "progression_score"]
    df = final.merge(
        evals[["candidate_id", *dims]].rename(columns={d: "m_" + d for d in dims}),
        on="candidate_id", how="left",
    )
    df["ep_no"] = df["episode"].map(episode_no)
    df["gap"] = df["final_score"] - df["local_editorial_score"]
    n = len(df)
    episodes_total = args.episodes_total or df["episode"].nunique()

    lines = [f"# Quality report — where the tool picks badly ({run.name})", ""]
    lines += [
        "> Measured from the model's and the heuristic's own outputs. This shows where they disagree",
        "> or look weak; it does **not** prove either is right. Ground truth = `human_check_sheet.csv`.",
        "",
        "## 1. Coverage",
    ]
    per_ep = df["episode"].value_counts()
    dist = per_ep.value_counts().sort_index()
    missing = episodes_total - len(per_ep)
    lines += [
        f"- {n} promos from {len(per_ep)} of {episodes_total} episodes"
        + (f" ({missing} episodes have none)." if missing > 0 else "."),
        "- Promos per episode: " + ", ".join(f"{k} promo(s) in {v} episodes" for k, v in dist.items()) + ".",
        "- **Weakness:** the 12-candidate pre-filter plus overlap pruning leaves most episodes with a single "
        "option, so an editor rarely gets alternatives to choose from.",
        "",
        "## 2. Hook / cliffhanger timestamp check (machine-verifiable)",
    ]
    comp = df["timestamp_compliance"].value_counts()
    lines.append("- " + ", ".join(f"{k}: {v}" for k, v in comp.items()))
    bad = df[df["timestamp_compliance"].isin(["PARTIAL", "FAIL"])]
    if len(bad):
        hook_bad = int((bad["hook_timestamp_valid"] == False).sum())  # noqa: E712
        cliff_bad = int((bad["cliffhanger_timestamp_valid"] == False).sum())  # noqa: E712
        lines.append(
            f"- Of {len(bad)} PARTIAL/FAIL clips, the **hook** timestamp is outside the opening window in "
            f"{hook_bad} and the **cliffhanger** timestamp outside the closing window in {cliff_bad}: the model "
            "picked a strong line that is not actually in the first 3s / last 5s (or gave no timestamp)."
        )
        rows = [[f"#{int(r['rank'])}", r["episode"], f"{r['clip_start']}-{r['clip_end']}", r["timestamp_compliance"],
                 short(r["hook"], 60), short(r["cliffhanger"], 60)] for _, r in bad.sort_values("rank").head(8).iterrows()]
        lines += ["", md_table(rows, ["rank", "episode", "span (s)", "check", "hook", "cliffhanger"]), ""]

    lines += ["## 3. Stand-alone problem (does a new viewer follow it?)"]
    low = df[df["m_standalone_score"] <= 6]
    prior = df[df["risks"].fillna("").astype(str).str.contains(PRIOR_CONTEXT)]
    lines.append(
        f"- {len(low)} promos have a model stand-alone score of 6 or less; {len(prior)} list needing earlier-episode "
        "context among their risks."
    )
    if df["ep_no"].nunique() >= 6:
        thirds = pd.qcut(df["ep_no"].rank(method="first"), 3, labels=["early", "middle", "late"])
        by = df.groupby(thirds, observed=True)["m_standalone_score"].mean().round(2)
        lines.append(
            "- Mean stand-alone score by position in the series: "
            + ", ".join(f"{k} {v}" for k, v in by.items())
            + ". A falling trend means the tool picks later-episode moments that need backstory."
        )
    lines.append("")

    lines += ["## 4. Model vs heuristic disagreement"]
    corr = df["final_score"].corr(df["local_editorial_score"])
    lines.append(
        f"- Correlation between the model score and the local heuristic score: **{corr:.2f}**. "
        "A low value means the 30% heuristic share mostly adds noise rather than a second opinion."
    )
    lines.append(f"- Model score: mean {df['final_score'].mean():.1f}, spread (std) {df['final_score'].std():.1f}, "
                 f"{int(df['is_promising'].sum())}/{n} marked promising (little discrimination if nearly all pass).")
    hi_gap = df.sort_values("gap", ascending=False).head(5)
    lo_gap = df.sort_values("gap").head(5)
    rows = [[f"#{int(r['rank'])}", r["episode"], r["final_score"], r["local_editorial_score"], short(r["hook"], 70)]
            for _, r in hi_gap.iterrows()]
    lines += ["", "Model loves it, heuristic does not (check these by eye):", "",
              md_table(rows, ["rank", "episode", "model", "local", "hook"]), ""]
    rows = [[f"#{int(r['rank'])}", r["episode"], r["final_score"], r["local_editorial_score"], short(r["hook"], 70)]
            for _, r in lo_gap.iterrows()]
    lines += ["Heuristic likes it, model does not:", "", md_table(rows, ["rank", "episode", "model", "local", "hook"]), ""]

    lines += ["## 5. Length bias"]
    lines.append(
        f"- Median length {df['duration'].median():.0f}s; {int((df['duration'] >= 55).sum())}/{n} promos are 55s or "
        "longer. Keyword-count scoring rewards longer windows, so very long clips may beat tighter ones."
    )
    corr_len = df["duration"].corr(df["local_editorial_score"])
    lines.append(f"- Correlation of length with local score: {corr_len:.2f}.")
    lines += ["", "## 6. Known blind spots (by design)",
              "- Works from the screenplay only: acting, visuals, music and edit pacing are invisible to it.",
              "- Each promo is one continuous stretch; promos that join moments, or span episodes, are not generated.",
              "- Scores come from a model with no ground truth: it can be confidently wrong, and it grades its own "
              "shortlist. Only the human check sheet gives an accuracy number.",
              ""]

    (run / "quality_report.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- human check sheet: top of the ranking, bottom of the ranking, biggest disagreements ----
    picks = pd.concat([
        df.sort_values("rank").head(10).assign(why_in_sheet="top ranked"),
        df.sort_values("rank").tail(5).assign(why_in_sheet="lowest ranked"),
        hi_gap.head(3).assign(why_in_sheet="model>>heuristic"),
        lo_gap.head(2).assign(why_in_sheet="heuristic>>model"),
    ]).drop_duplicates("candidate_id")
    sheet = pd.DataFrame({
        "rank": picks["rank"].astype(int),
        "why_in_sheet": picks["why_in_sheet"],
        "episode": picks["episode"],
        "start": picks["clip_start"],
        "end": picks["clip_end"],
        "model_hook": picks["hook"],
        "model_cliffhanger": picks["cliffhanger"],
        "model_score": picks["final_score"],
        "opening_3s_transcript": picks["opening_transcript"],
        "closing_5s_transcript": picks["ending_transcript"],
        "human_hook_ok (Y/N)": "",
        "human_cliffhanger_ok (Y/N)": "",
        "human_standalone_ok (Y/N)": "",
        "human_would_post (Y/N)": "",
        "notes": "",
    })
    sheet.to_csv(run / "human_check_sheet.csv", index=False, encoding="utf-8-sig")
    print(f"Wrote {run / 'quality_report.md'} and {run / 'human_check_sheet.csv'} ({len(sheet)} clips to verify)")


if __name__ == "__main__":
    main()
