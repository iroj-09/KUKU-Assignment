"""Write the final promo list in the format the brief asks for.

For every promo: the episode, the start/end of EVERY segment in order, the hook, the
cliffhanger, one line on why it works, and its rank with the reason for that rank.

Outputs (in --output-dir):
  promos_submission.json   machine-readable; `segments` is a list so multi-segment promos fit
  promos_submission.csv    one row per promo (segments as "start-end; start-end")
  promos_submission.md     human-readable top of the ranking

With --local-only (used when no LLM is available) the list is ranked by the local
heuristic score alone; hook/cliffhanger/why are left blank rather than invented.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

DIMENSIONS = [
    ("hook_score", "hook"),
    ("cliffhanger_score", "cliffhanger"),
    ("emotional_score", "emotion"),
    ("standalone_score", "standalone"),
    ("progression_score", "progression"),
]


def _clean(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _num(value, nd=1):
    value = _clean(value)
    return None if value is None else round(float(value), nd)


def _risks(value) -> list[str]:
    value = _clean(value)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    text = str(value).strip()
    if text.startswith("["):
        try:
            import ast

            parsed = ast.literal_eval(text)
            return [str(x) for x in parsed]
        except (ValueError, SyntaxError):
            pass
    return [text] if text else []


def rank_reason(row: dict, dims: dict | None) -> str:
    parts = [f"Hybrid {row['hybrid_score']}"]
    if row.get("llm_score") is not None:
        parts[0] += f" = 70% model {row['llm_score']} + 30% local {row['local_score']}"
    if dims:
        parts.append(
            "model scores: " + ", ".join(f"{label} {dims[key]}" for key, label in DIMENSIONS if key in dims)
        )
    compliance = row.get("compliance")
    if compliance == "PASS":
        parts.append("hook and cliffhanger timestamps verified inside the opening/closing windows")
    elif compliance in ("PARTIAL", "FAIL"):
        parts.append(f"timestamp check {compliance}: confirm the hook/cliffhanger by eye")
    risks = row.get("risks") or []
    if risks and not str(risks[0]).lower().startswith("none"):
        parts.append("risk: " + str(risks[0]).rstrip("."))
    return "; ".join(parts) + "."


def build(ranking_path: Path, evaluations_path: Path | None) -> list[dict]:
    df = pd.read_csv(ranking_path, encoding="utf-8-sig")
    dims_by_id: dict[str, dict] = {}
    if evaluations_path and evaluations_path.exists():
        for item in json.loads(evaluations_path.read_text(encoding="utf-8")):
            dims_by_id[item["candidate_id"]] = item

    df = df.sort_values("rank")
    out = []
    for _, r in df.iterrows():
        cid = r["candidate_id"]
        dims = dims_by_id.get(cid)
        row = {
            "rank": int(r["rank"]),
            "promo_id": cid,
            "episode": r["episode"],
            "segments": [{"start": _num(r["clip_start"], 2), "end": _num(r["clip_end"], 2)}],
            "total_duration": _num(r["duration"] if "duration" in r else r["duration_seconds"], 2),
            "hook": _clean(r.get("hook")) or "",
            "hook_timestamp": _num(r.get("hook_timestamp"), 2),
            "cliffhanger": _clean(r.get("cliffhanger")) or "",
            "cliffhanger_timestamp": _num(r.get("cliffhanger_timestamp"), 2),
            "why_it_works": _clean(r.get("why_it_works")) or "",
            "standalone_context": _clean(r.get("standalone_context")) or "",
            "hybrid_score": _num(r.get("ranking_score"), 2),
            "llm_score": _num(r.get("final_score"), 1),
            "local_score": _num(r.get("local_editorial_score"), 1),
            "compliance": _clean(r.get("timestamp_compliance")) or "UNVERIFIED",
            "risks": _risks(r.get("risks")),
            "llm_model": (dims or {}).get("llm_model") or _clean(r.get("llm_model")) or "",
        }
        row["rank_reason"] = rank_reason(row, dims)
        out.append(row)
    return out


def build_local_only(merged_path: Path) -> list[dict]:
    df = pd.read_csv(merged_path, encoding="utf-8-sig").sort_values(
        "local_editorial_score", ascending=False
    )
    out = []
    for i, (_, r) in enumerate(df.iterrows(), start=1):
        score = _num(r.get("local_editorial_score"), 1)
        out.append(
            {
                "rank": i,
                "promo_id": f"{r['episode']}|{r['clip_start']}|{r['clip_end']}",
                "episode": r["episode"],
                "segments": [{"start": _num(r["clip_start"], 2), "end": _num(r["clip_end"], 2)}],
                "total_duration": _num(r["duration"], 2),
                "hook": "",
                "hook_timestamp": None,
                "cliffhanger": "",
                "cliffhanger_timestamp": None,
                "why_it_works": "",
                "standalone_context": "",
                "hybrid_score": score,
                "llm_score": None,
                "local_score": score,
                "compliance": "UNVERIFIED",
                "risks": [],
                "llm_model": "",
                "rank_reason": (
                    f"Local heuristic score {score} only (no LLM was run); "
                    "hook/cliffhanger/why left blank rather than invented. Review by hand."
                ),
            }
        )
    return out


def write_outputs(rows: list[dict], output_dir: Path, top_n: int = 10) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "promos_submission.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    flat = []
    for r in rows:
        f = {k: v for k, v in r.items() if k not in ("segments", "risks")}
        f["segments"] = "; ".join(f"{s['start']}-{s['end']}" for s in r["segments"])
        f["risks"] = " | ".join(r["risks"])
        flat.append(f)
    columns = [
        "rank", "episode", "segments", "total_duration", "hook", "hook_timestamp",
        "cliffhanger", "cliffhanger_timestamp", "why_it_works", "rank_reason",
        "standalone_context", "compliance", "hybrid_score", "llm_score", "local_score",
        "risks", "llm_model", "promo_id",
    ]
    pd.DataFrame(flat)[columns].to_csv(
        output_dir / "promos_submission.csv", index=False, encoding="utf-8-sig"
    )

    lines = [f"# Promo shortlist ({len(rows)} promos, best first)", ""]
    for r in rows[:top_n]:
        segs = ", ".join(f"{s['start']}s-{s['end']}s" for s in r["segments"])
        lines += [
            f"## #{r['rank']} · {r['episode']} · {segs} ({r['total_duration']}s)",
            f"- **Hook:** {r['hook'] or '—'}" + (f" (t={r['hook_timestamp']}s)" if r["hook_timestamp"] is not None else ""),
            f"- **Cliffhanger:** {r['cliffhanger'] or '—'}" + (f" (t={r['cliffhanger_timestamp']}s)" if r["cliffhanger_timestamp"] is not None else ""),
            f"- **Why it works:** {r['why_it_works'] or '—'}",
            f"- **Why ranked here:** {r['rank_reason']}",
            "",
        ]
    if len(rows) > top_n:
        lines.append(f"_…and {len(rows) - top_n} more in promos_submission.csv/json._")
    (output_dir / "promos_submission.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ranking", default="outputs/ranked_promos/final_ranking.csv")
    ap.add_argument("--evaluations", default="outputs/editorial/editorial_evaluations.json")
    ap.add_argument("--merged", default="outputs/editorial/merged_editorial_data.csv",
                    help="used only with --local-only")
    ap.add_argument("--output-dir", default="outputs/ranked_promos")
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--top", type=int, default=10, help="promos shown in the .md file")
    args = ap.parse_args()

    if args.local_only:
        rows = build_local_only(ROOT / args.merged)
    else:
        rows = build(ROOT / args.ranking, ROOT / args.evaluations)
    write_outputs(rows, ROOT / args.output_dir, args.top)
    print(f"Wrote {len(rows)} promos to {ROOT / args.output_dir}/promos_submission.(json|csv|md)")


if __name__ == "__main__":
    main()
