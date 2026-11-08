"""Regression tests for shared pipeline parameters and the fixes made around them."""

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from deduplicate import deduplicate, overlap_ratio  # noqa: E402
from editorial_evaluator import PROMPT, validate_timestamp  # noqa: E402
from nle_export import export_cmx_edl, seconds_to_frames, frames_to_timecode  # noqa: E402
from scoring import heuristic_score  # noqa: E402


# ---------- shared evidence windows ----------

def test_default_windows_are_3_and_5_seconds():
    assert config.HOOK_WINDOW_SECONDS == 3.0
    assert config.CLIFFHANGER_WINDOW_SECONDS == 5.0


def test_validate_timestamp_uses_config_windows():
    # hook window: [start, start + 3]
    assert validate_timestamp(100.0, 100, 150, "hook") == 100.0
    assert validate_timestamp(103.0, 100, 150, "hook") == 103.0
    assert validate_timestamp(103.5, 100, 150, "hook") is None
    # cliffhanger window: [end - 5, end]
    assert validate_timestamp(145.0, 100, 150, "cliffhanger") == 145.0
    assert validate_timestamp(144.9, 100, 150, "cliffhanger") is None
    assert validate_timestamp("not a number", 100, 150, "hook") is None


def test_gemini_prompt_has_no_unreplaced_tokens():
    assert "__HOOK_S__" not in PROMPT and "__CLIFF_S__" not in PROMPT
    assert f"start_seconds + {config.HOOK_WINDOW_SECONDS:g}" in PROMPT
    assert f"end_seconds - {config.CLIFFHANGER_WINDOW_SECONDS:g}" in PROMPT


# ---------- scoring: WPM counts spoken dialogue only ----------

def _candidate(events, duration=30.0):
    transcript = " ".join(e["text"] for e in events)
    return {
        "start": 0.0,
        "end": duration,
        "duration": duration,
        "events": events,
        "transcript": transcript,
    }


def test_wpm_ignores_camera_and_action_lines():
    events = [
        {"type": "CAMERA", "text": "wide shot of the grand hall " * 20, "start": 0, "end": 10},
        {"type": "ALEXANDER", "text": "one two three four five six", "start": 10, "end": 15},
    ]
    result = heuristic_score(_candidate(events, duration=30.0))
    # 6 spoken words over 30s -> 12 WPM, not ~(126 words) 252 WPM
    assert result["wpm"] == 12.0


# ---------- deduplicate ----------

def test_overlap_ratio_is_relative_to_shorter_clip():
    # A short clip fully inside a long one has ratio 1.0 (IoU would be 0.25).
    assert overlap_ratio(0, 20, 0, 80) == 1.0
    assert overlap_ratio(0, 20, 20, 40) == 0.0


def test_deduplicate_respects_duration_bounds_and_overlap():
    df = pd.DataFrame(
        [
            {"episode": "E1", "start": 0, "end": 30, "duration": 30, "baseline_score": 80},
            {"episode": "E1", "start": 5, "end": 35, "duration": 30, "baseline_score": 70},   # overlaps first
            {"episode": "E1", "start": 60, "end": 100, "duration": 40, "baseline_score": 60},
            {"episode": "E1", "start": 120, "end": 125, "duration": 5, "baseline_score": 99},  # too short
        ]
    )
    out = deduplicate(df, max_per_episode=3, overlap_threshold=0.5)
    assert sorted(out["start"].tolist()) == [0, 60]


# ---------- NLE export: frame-accurate EDL ----------

def _tc_to_frames(tc: str, fps: int) -> int:
    h, m, s, f = (int(x) for x in tc.split(":"))
    return ((h * 60 + m) * 60 + s) * fps + f


def test_edl_source_and_record_durations_match_with_fractional_times():
    df = pd.DataFrame(
        [
            {"episode": "E1", "clip_start": 10.3, "clip_end": 40.7, "why_it_works": "line1\nline2"},
            {"episode": "E2", "clip_start": 5.55, "clip_end": 51.15},
            {"episode": "E3", "clip_start": 0.1, "clip_end": 20.3},
        ]
    )
    for fps in (24, 30, 60):
        edl = export_cmx_edl(df, fps=fps)
        events = [ln for ln in edl.splitlines() if ln[:3].isdigit()]
        assert len(events) == 3
        prev_rec_out = 0
        for ln in events:
            src_in, src_out, rec_in, rec_out = ln.split()[-4:]
            assert _tc_to_frames(src_out, fps) - _tc_to_frames(src_in, fps) == \
                _tc_to_frames(rec_out, fps) - _tc_to_frames(rec_in, fps)
            assert _tc_to_frames(rec_in, fps) == prev_rec_out  # events are contiguous
            prev_rec_out = _tc_to_frames(rec_out, fps)
        # multi-line reasons must not break the EDL structure
        assert "line1 line2" in edl


def test_frames_helpers_round_trip():
    assert frames_to_timecode(seconds_to_frames(61.5, 24), 24) == "00:01:01:12"
    assert frames_to_timecode(-5, 24) == "00:00:00:00"
