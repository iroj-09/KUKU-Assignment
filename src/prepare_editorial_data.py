"""
Prepare timestamp-grounded editorial evidence for shortlisted promo candidates.

Run from the project root:
    python src/prepare_editorial_data.py
    python src/prepare_editorial_data.py --top 15
    python src/prepare_editorial_data.py --input outputs/ranked_promos/promo_shortlist.csv

Expected screenplay source:
    data/input/**/*.txt

Outputs:
    outputs/editorial/editorial_evidence.json
    outputs/editorial/editorial_evidence.csv

All event timestamps are absolute episode timestamps from the screenplay.
Opening and ending events are selected by interval overlap with the first
3 seconds and final 5 seconds of each candidate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SRC_DIR.parent))
import config  # noqa: E402

try:
    from parser import parse_episode
except ImportError as exc:
    raise ImportError(
        "Could not import src/parser.py. Run this script from the project "
        "that contains src/parser.py."
    ) from exc


def normalize_episode(value: Any) -> str:
    """Normalize 'Episode 32', '32', and similar labels to '32'."""
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        raise ValueError(f"Cannot extract episode number from: {value!r}")
    return str(int(match.group(1)))


SUPPORTED_SUFFIXES = {".txt", ".srt", ".fountain"}


def episode_key(value: Any) -> str:
    """Episode number when the label has one, otherwise a filename-safe version of the label.

    Works for "Episode 32" -> "32" and for labels without digits such as "Pilot".
    """
    try:
        return normalize_episode(value)
    except ValueError:
        return re.sub(r"\s+", "_", str(value or "").strip())


def find_episode_files(input_dir: Path) -> dict[str, Path]:
    """Index screenplay files (.txt / .srt / .fountain) by the episode label they declare."""
    if not input_dir.exists():
        raise FileNotFoundError(f"Screenplay input directory not found: {input_dir}")

    files: dict[str, Path] = {}
    duplicates: dict[str, list[Path]] = {}

    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            parsed = parse_episode(path)
            label = str(parsed.get("episode") or path.stem).strip()
        except Exception as exc:
            print(f"[WARN] Skipping {path.name}: {exc}")
            continue

        if label in files:
            duplicates.setdefault(label, [files[label]]).append(path)
        else:
            files[label] = path

    if duplicates:
        details = "; ".join(
            f"{label}: {[p.name for p in paths]}"
            for label, paths in duplicates.items()
        )
        raise ValueError(f"Duplicate episode labels found: {details}")

    return files


def resolve_episode_file(files: dict[str, Path], episode: Any) -> Path | None:
    """Exact label match first; otherwise a unique match on the episode number."""
    label = str(episode).strip()
    if label in files:
        return files[label]
    key = episode_key(label)
    matches = [path for name, path in files.items() if episode_key(name) == key]
    return matches[0] if len(matches) == 1 else None


def event_overlaps(event: dict, window_start: float, window_end: float) -> bool:
    return (
        float(event.get("end", 0)) > window_start
        and float(event.get("start", 0)) < window_end
    )


def event_payload(event: dict, scene: dict) -> dict:
    start = float(event.get("start", 0))
    end = float(event.get("end", 0))
    return {
        "scene_number": scene.get("scene_number"),
        "scene_heading": scene.get("heading", ""),
        "type": event.get("type", ""),
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(max(0, end - start), 2),
        "text": event.get("text", "").strip(),
    }


def extract_candidate_events(
    episode_data: dict,
    clip_start: float,
    clip_end: float,
) -> tuple[list[dict], list[dict], list[dict]]:
    opening_start = clip_start
    opening_end = min(clip_start + config.HOOK_WINDOW_SECONDS, clip_end)
    ending_start = max(clip_start, clip_end - config.CLIFFHANGER_WINDOW_SECONDS)
    ending_end = clip_end

    full_events: list[dict] = []
    opening_events: list[dict] = []
    ending_events: list[dict] = []

    for scene in episode_data.get("scenes", []):
        for event in scene.get("events", []):
            if not event.get("text", "").strip():
                continue

            # Include only events that intersect the candidate clip.
            if not event_overlaps(event, clip_start, clip_end):
                continue

            item = event_payload(event, scene)
            full_events.append(item)

            if event_overlaps(event, opening_start, opening_end):
                opening_events.append(item)

            if event_overlaps(event, ending_start, ending_end):
                ending_events.append(item)

    full_events.sort(key=lambda e: (e["start"], e["end"], e["type"]))
    opening_events.sort(key=lambda e: (e["start"], e["end"], e["type"]))
    ending_events.sort(key=lambda e: (e["start"], e["end"], e["type"]))

    return full_events, opening_events, ending_events


def build_evidence(row: pd.Series, episode_data: dict, source_file: Path) -> dict:
    clip_start = float(row["start"])
    clip_end = float(row["end"])

    if clip_end <= clip_start:
        raise ValueError(
            f"Invalid clip interval for {row.get('episode')}: "
            f"{clip_start}–{clip_end}"
        )

    events, opening, ending = extract_candidate_events(
        episode_data,
        clip_start,
        clip_end,
    )

    # Use only screenplay events, never the flattened shortlist transcript,
    # as the timestamp-grounded evidence source.
    full_transcript = "\n".join(
        f'[{e["start"]:.2f}-{e["end"]:.2f}] {e["type"]}: {e["text"]}'
        for e in events
    )

    opening_transcript = "\n".join(
        f'[{e["start"]:.2f}-{e["end"]:.2f}] {e["type"]}: {e["text"]}'
        for e in opening
    )

    ending_transcript = "\n".join(
        f'[{e["start"]:.2f}-{e["end"]:.2f}] {e["type"]}: {e["text"]}'
        for e in ending
    )

    duration = clip_end - clip_start
    return {
        "candidate_id": (
            f'{episode_key(row["episode"])}_'
            f'{int(round(clip_start * 100))}_'
            f'{int(round(clip_end * 100))}'
        ),
        "rank": int(row["rank"]) if pd.notna(row.get("rank")) else None,
        "episode": episode_data.get("episode", row.get("episode", "")),
        "episode_file": source_file.name,
        "logline": episode_data.get("logline", ""),
        "continuity_notes": episode_data.get("continuity_notes", ""),
        "clip_start": round(clip_start, 2),
        "clip_end": round(clip_end, 2),
        "duration": round(duration, 2),
        "opening_window": {
            "start": round(clip_start, 2),
            "end": round(min(clip_start + config.HOOK_WINDOW_SECONDS, clip_end), 2),
            "events": opening,
            "transcript": opening_transcript,
        },
        "ending_window": {
            "start": round(max(clip_start, clip_end - config.CLIFFHANGER_WINDOW_SECONDS), 2),
            "end": round(clip_end, 2),
            "events": ending,
            "transcript": ending_transcript,
        },
        "events": events,
        "full_transcript": full_transcript,
        "event_count": len(events),
        "opening_event_count": len(opening),
        "ending_event_count": len(ending),
        "source_timestamp_basis": "Original screenplay event timestamps",
        "timestamp_validation": {
            "duration_within_20_60": 20 <= duration <= 60,
            "opening_window_seconds": min(3.0, duration),
            "ending_window_seconds": min(5.0, duration),
            "has_opening_events": bool(opening),
            "has_ending_events": bool(ending),
        },
        "local_editorial_score": row.get("local_editorial_score", None),
        "heuristic_baseline_score": row.get(
            "heuristic_baseline_score",
            row.get("baseline_score", None),
        ),
        "evaluation_status": "timestamp_evidence_prepared_not_editorially_validated",
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract exact screenplay events for shortlisted promo windows."
    )
    ap.add_argument(
        "--input",
        default="outputs/ranked_promos/promo_shortlist.csv",
        help="Candidate shortlist CSV.",
    )
    ap.add_argument(
        "--screenplays",
        default="data/input",
        help="Directory containing original timestamped screenplay TXT files.",
    )
    ap.add_argument(
        "--output-dir",
        default="outputs/editorial",
        help="Directory for JSON and CSV outputs.",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=0,
        help="Only process top N rows by rank. 0 processes all rows.",
    )
    args = ap.parse_args()

    input_path = BASE_DIR / args.input
    screenplay_dir = BASE_DIR / args.screenplays
    output_dir = BASE_DIR / args.output_dir

    if not input_path.exists():
        raise FileNotFoundError(f"Shortlist CSV not found: {input_path}")

    shortlist = pd.read_csv(input_path)
    required = {"episode", "start", "end"}
    missing = required - set(shortlist.columns)
    if missing:
        raise ValueError(f"Shortlist is missing columns: {sorted(missing)}")

    shortlist["start"] = pd.to_numeric(shortlist["start"], errors="coerce")
    shortlist["end"] = pd.to_numeric(shortlist["end"], errors="coerce")
    shortlist = shortlist.dropna(subset=["episode", "start", "end"])

    if args.top > 0:
        if "rank" in shortlist.columns:
            shortlist = shortlist.sort_values("rank").head(args.top)
        else:
            shortlist = shortlist.head(args.top)

    episode_files = find_episode_files(screenplay_dir)
    print(f"Screenplay files indexed: {len(episode_files)}")
    print(f"Shortlist candidates to process: {len(shortlist)}")

    results = []
    failures = []

    for index, (_, row) in enumerate(shortlist.iterrows(), start=1):
        source_file = resolve_episode_file(episode_files, row["episode"])

        if source_file is None:
            failures.append({
                "episode": row["episode"],
                "start": row["start"],
                "end": row["end"],
                "error": f"No screenplay file found for {row['episode']}",
            })
            print(f"[{index}/{len(shortlist)}] Missing screenplay: {row['episode']}")
            continue

        try:
            episode_data = parse_episode(source_file)
            evidence = build_evidence(row, episode_data, source_file)
            results.append(evidence)
            print(
                f"[{index}/{len(shortlist)}] {episode_data['episode']} "
                f"{row['start']:.2f}-{row['end']:.2f}s | "
                f"events={evidence['event_count']} "
                f"opening={evidence['opening_event_count']} "
                f"ending={evidence['ending_event_count']}",
                flush=True,
            )
        except Exception as exc:
            failures.append({
                "episode": row["episode"],
                "start": row["start"],
                "end": row["end"],
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"[{index}/{len(shortlist)}] ERROR: {exc}", flush=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "editorial_evidence.json"
    csv_path = output_dir / "editorial_evidence.csv"
    failures_path = output_dir / "editorial_evidence_failures.json"

    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    flat_rows = []
    for item in results:
        flat_rows.append({
            "candidate_id": item["candidate_id"],
            "rank": item["rank"],
            "episode": item["episode"],
            "episode_file": item["episode_file"],
            "clip_start": item["clip_start"],
            "clip_end": item["clip_end"],
            "duration": item["duration"],
            "local_editorial_score": item["local_editorial_score"],
            "event_count": item["event_count"],
            "opening_event_count": item["opening_event_count"],
            "ending_event_count": item["ending_event_count"],
            "opening_transcript": item["opening_window"]["transcript"],
            "ending_transcript": item["ending_window"]["transcript"],
            "full_transcript": item["full_transcript"],
            "evaluation_status": item["evaluation_status"],
        })

    pd.DataFrame(flat_rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    failures_path.write_text(
        json.dumps(failures, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nEDITORIAL EVIDENCE PREPARATION COMPLETE")
    print(f"Prepared candidates : {len(results)}")
    print(f"Failed candidates   : {len(failures)}")
    print(f"JSON                : {json_path}")
    print(f"CSV                 : {csv_path}")
    print(f"Failures             : {failures_path}")
    print(
        "\nNote: event timestamps are source-grounded. "
        "A human/editorial model must still decide whether the hook and "
        "cliffhanger are compelling."
    )


if __name__ == "__main__":
    main()
