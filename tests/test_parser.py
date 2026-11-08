from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from parser import to_seconds, parse_episode
from candidate_generator import generate_beat_aligned_candidates
from scoring import heuristic_score


def test_to_seconds():
    assert to_seconds("01:02.50") == 62.5
    assert to_seconds("00:01:02.50") == 62.5
    assert to_seconds("00:01:02,500") == 62.5


def test_parse_episode_metadata(tmp_path):
    p = tmp_path / "ep.txt"
    p.write_text(
        "EPISODE NUMBER: Episode 1\n"
        "EPISODE LOGLINE: Test\n"
        "SCENE 01\n"
        "Scene heading: INT. ROOM – DAY\n"
        "Scene start: 00:00.00\n"
        "Scene end: 00:30.00\n"
        "**ACTION:**\n"
        "Start: (00:01.00) | End: (00:05.00)\n"
        "She enters.\n",
        encoding="utf-8",
    )
    result = parse_episode(p)
    assert result["episode"] == "Episode 1"
    assert result["event_count"] == 1
    assert result["scenes"][0]["events"][0]["text"] == "She enters."


def test_parse_srt_format(tmp_path):
    p = tmp_path / "subs.srt"
    p.write_text(
        "1\n"
        "00:00:01,000 --> 00:00:04,500\n"
        "JULIANA: You lied to me!\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,200\n"
        "ALEXANDER: I had to protect you.\n",
        encoding="utf-8",
    )
    result = parse_episode(p)
    assert result["event_count"] == 2
    assert result["scenes"][0]["events"][0]["start"] == 1.0
    assert result["scenes"][0]["events"][0]["end"] == 4.5
    assert "You lied to me!" in result["scenes"][0]["events"][0]["text"]


def test_beat_aligned_windowing():
    ep = {
        "episode": "Test Ep",
        "scenes": [
            {
                "scene_number": 1,
                "events": [
                    {"type": "DIALOGUE", "start": 0.0, "end": 10.0, "text": "Opening hook line."},
                    {"type": "ACTION", "start": 10.0, "end": 22.0, "text": "Intense struggle occurs."},
                    {"type": "DIALOGUE", "start": 22.0, "end": 28.0, "text": "Final cliffhanger!"},
                ],
            }
        ],
    }
    cands = generate_beat_aligned_candidates(ep, min_seconds=20, max_seconds=30)
    assert len(cands) >= 1
    # Candidate must strictly span from an event start to an event end
    cand = cands[0]
    assert cand["start"] == 0.0
    assert cand["end"] in (22.0, 28.0)
    assert 20 <= cand["duration"] <= 30


def test_time_aware_scoring():
    cand = {
        "start": 0.0,
        "end": 25.0,
        "duration": 25.0,
        "transcript": "Why did you marry me? You lied! I hate you! The truth will kill you.",
        "events": [
            {"type": "JULIANA", "start": 0.0, "end": 3.0, "text": "Why did you marry me? You lied!"},
            {"type": "ALEXANDER", "start": 3.0, "end": 20.0, "text": "I hate you!"},
            {"type": "JULIANA", "start": 20.0, "end": 25.0, "text": "The truth will kill you."},
        ],
    }
    scores = heuristic_score(cand)
    assert scores["baseline_score"] > 0
    assert "wpm" in scores
    assert "dialogue_turns" in scores
    assert scores["hook_score"] > 2.0
    assert scores["cliffhanger_score"] > 2.0


def test_nle_export():
    from nle_export import seconds_to_timecode, export_davinci_markers, export_cmx_edl
    import pandas as pd

    assert seconds_to_timecode(0.0) == "00:00:00:00"
    assert seconds_to_timecode(65.5, fps=24) == "00:01:05:12"

    df = pd.DataFrame([
        {
            "rank": 1,
            "episode": "Episode 16",
            "clip_start": 0.0,
            "clip_end": 55.0,
            "ranking_score": 79.9,
            "why_it_works": "Alexander protects Juliana",
        }
    ])
    davinci_csv = export_davinci_markers(df)
    assert "Episode 16" in davinci_csv
    assert "00:00:55:00" in davinci_csv

    edl = export_cmx_edl(df)
    assert "TITLE: KUKU_PROMOS" in edl
    assert "001  AX" in edl


def test_gemini_response_schema_validation():
    from editorial_evaluator import parse_response

    sample_json = """```json
    {
      "evaluations": [
        {
          "candidate_id": "Ep1|0|30",
          "is_promising": true,
          "hook": "Stop right there!",
          "hook_timestamp": 1.5,
          "cliffhanger": "You will pay for this.",
          "cliffhanger_timestamp": 29.0,
          "why_it_works": "High energy hook.",
          "standalone_context": "Dungeon scene.",
          "hook_score": 9,
          "cliffhanger_score": 8,
          "emotional_score": 7,
          "standalone_score": 6,
          "progression_score": 7,
          "risks": ["Fast dialogue"]
        }
      ]
    }
    ```"""
    parsed = parse_response(sample_json)
    assert len(parsed["evaluations"]) == 1
    eval_item = parsed["evaluations"][0]
    assert eval_item["candidate_id"] == "Ep1|0|30"
    assert eval_item["hook_score"] == 9


