"""Generate candidate promo clips from timestamped screenplay events.

Supports both:
1. 'beat_aligned' (recommended): Snaps clip boundaries to natural screenplay
   dialogue and action event start/end timestamps, eliminating mid-sentence cuts.
2. 'sliding': Mathematical sliding window stepped at fixed intervals.
3. 'hybrid': Prioritizes beat-aligned windows with sliding-window fallback.
"""

from __future__ import annotations
from typing import Literal

import sys
from pathlib import Path as _Path

# Make the project-root config.py importable when running `python src/<script>.py`.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402


def flatten_events(episode: dict) -> list[dict]:
    """Extract, normalize, and time-sort all non-empty events across scenes."""
    out = []
    for scene in episode.get("scenes", []):
        scene_num = scene.get("scene_number", 1)
        heading = scene.get("heading", "")
        for event in scene.get("events", []):
            start = event.get("start", 0.0)
            end = event.get("end", 0.0)
            text = (event.get("text") or "").strip()
            if text and end > start:
                out.append({
                    **event,
                    "start": float(start),
                    "end": float(end),
                    "scene_number": scene_num,
                    "scene_heading": heading,
                })
    return sorted(out, key=lambda x: (x["start"], x["end"]))


def _build_candidate(
    episode: dict,
    start: float,
    end: float,
    selected_events: list[dict],
    alignment: str = "beat_aligned",
) -> dict:
    """Helper to assemble a candidate dictionary."""
    transcript = " ".join(e["text"] for e in selected_events).strip()
    return {
        "episode": episode.get("episode"),
        "episode_file": episode.get("episode_file"),
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(end - start, 2),
        "scene_numbers": sorted(set(e["scene_number"] for e in selected_events)),
        "events": [
            {
                "type": e.get("type", "GENERAL"),
                "start": round(e["start"], 2),
                "end": round(e["end"], 2),
                "text": e["text"],
            }
            for e in selected_events
        ],
        "transcript": transcript,
        "alignment": alignment,
    }


def generate_beat_aligned_candidates(
    episode: dict,
    min_seconds: float = config.MIN_PROMO_SECONDS,
    max_seconds: float = config.MAX_PROMO_SECONDS,
) -> list[dict]:
    """Generate candidates aligned directly to event start and end boundaries.

    Ensures that every promo starts on an actor's line or action beat start
    and concludes cleanly on a beat ending, preventing mid-speech clipping.
    """
    events = flatten_events(episode)
    if not events:
        return []

    candidates = []
    seen = set()

    for i, start_ev in enumerate(events):
        clip_start = start_ev["start"]

        for end_ev in events[i:]:
            clip_end = end_ev["end"]
            duration = clip_end - clip_start

            if duration < min_seconds - 0.01:
                continue
            if duration > max_seconds + 0.01:
                break

            key = (round(clip_start, 2), round(clip_end, 2))
            if key in seen:
                continue

            # Selected events wholly or predominantly inside this window
            selected = [
                e for e in events
                if e["end"] > clip_start + 0.01 and e["start"] < clip_end - 0.01
            ]
            if not selected:
                continue

            seen.add(key)
            candidates.append(
                _build_candidate(
                    episode, clip_start, clip_end, selected, alignment="beat_aligned"
                )
            )

    return candidates


def generate_sliding_candidates(
    episode: dict,
    min_seconds: int = config.MIN_PROMO_SECONDS,
    max_seconds: int = config.MAX_PROMO_SECONDS,
    step_seconds: int = 5,
) -> list[dict]:
    """Generate fixed-step mathematical sliding windows."""
    events = flatten_events(episode)
    if not events:
        return []

    episode_end = max(e["end"] for e in events)
    candidates = []
    seen = set()

    start = 0.0
    while start < episode_end:
        for duration in range(min_seconds, max_seconds + 1, step_seconds):
            end = start + duration
            if end > episode_end + 0.01:
                continue

            selected = [
                e for e in events
                if e["end"] > start and e["start"] < end
            ]
            if not selected:
                continue

            key = (round(start, 2), round(end, 2))
            if key in seen:
                continue
            seen.add(key)

            candidates.append(
                _build_candidate(
                    episode, start, end, selected, alignment="sliding"
                )
            )

        start += step_seconds

    return candidates


def generate_candidates(
    episode: dict,
    min_seconds: int = config.MIN_PROMO_SECONDS,
    max_seconds: int = config.MAX_PROMO_SECONDS,
    step_seconds: int = 5,
    strategy: Literal["beat_aligned", "sliding", "hybrid"] = "beat_aligned",
) -> list[dict]:
    """Primary candidate generator function.

    Defaults to beat-aligned generation for clean audio/dialogue boundaries,
    with graceful fallback to sliding windows if few candidates are produced.
    """
    if strategy == "sliding":
        return generate_sliding_candidates(
            episode, min_seconds, max_seconds, step_seconds
        )

    beat_candidates = generate_beat_aligned_candidates(
        episode, min_seconds, max_seconds
    )

    if strategy == "beat_aligned":
        # Fall back to sliding only if episode had sparse events (<5 candidates)
        if len(beat_candidates) >= 5:
            return beat_candidates
        sliding = generate_sliding_candidates(
            episode, min_seconds, max_seconds, step_seconds
        )
        return beat_candidates or sliding

    if strategy == "hybrid":
        seen = {(c["start"], c["end"]) for c in beat_candidates}
        sliding = generate_sliding_candidates(
            episode, min_seconds, max_seconds, step_seconds
        )
        combined = list(beat_candidates)
        for c in sliding:
            key = (c["start"], c["end"])
            if key not in seen:
                seen.add(key)
                combined.append(c)
        return combined

    return beat_candidates
