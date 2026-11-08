"""A new show at interview time can arrive in any supported format with any episode naming."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prepare_editorial_data import (  # noqa: E402
    episode_key,
    find_episode_files,
    resolve_episode_file,
)

KUKU_TXT = (
    "EPISODE NUMBER: {label}\n"
    "EPISODE LOGLINE: test\n"
    "SCENE 01\n"
    "Scene heading: INT. ROOM - DAY\n"
    "Scene start: 00:00.00\n"
    "Scene end: 00:30.00\n"
    "**ACTION:**\n"
    "Start: (00:01.00) | End: (00:05.00)\n"
    "She enters.\n"
)


def _srt(n_cues=60):
    cues = []
    for i in range(n_cues):
        s, e = i * 4, i * 4 + 4
        cues.append(
            f"{i + 1}\n00:{s // 60:02d}:{s % 60:02d},000 --> 00:{e // 60:02d}:{e % 60:02d},000\n"
            f"{'MAYA' if i % 2 else 'RAJ'}: line number {i} what why never stop\n"
        )
    return "\n".join(cues)


def test_episode_key_handles_labels_without_numbers():
    assert episode_key("Episode 32") == "32"
    assert episode_key("S01E07") == "1"  # first number wins; exact-label match is tried first anyway
    assert episode_key("The Pilot") == "The_Pilot"


def test_find_episode_files_indexes_all_supported_types_by_label(tmp_path):
    (tmp_path / "a.txt").write_text(KUKU_TXT.format(label="Pilot"), encoding="utf-8")
    (tmp_path / "b.srt").write_text(_srt(5), encoding="utf-8")
    (tmp_path / "notes.md").write_text("ignore me", encoding="utf-8")

    files = find_episode_files(tmp_path)
    assert "Pilot" in files
    assert any(p.suffix == ".srt" for p in files.values())
    assert len(files) == 2

    assert resolve_episode_file(files, "Pilot").name == "a.txt"
    assert resolve_episode_file(files, "does not exist") is None


def test_season_style_labels_do_not_collide(tmp_path):
    (tmp_path / "s1.txt").write_text(KUKU_TXT.format(label="S1E1"), encoding="utf-8")
    (tmp_path / "s2.txt").write_text(KUKU_TXT.format(label="S2E1"), encoding="utf-8")
    files = find_episode_files(tmp_path)
    assert resolve_episode_file(files, "S1E1").name == "s1.txt"
    assert resolve_episode_file(files, "S2E1").name == "s2.txt"


def test_duplicate_labels_fail_loudly(tmp_path):
    (tmp_path / "x.txt").write_text(KUKU_TXT.format(label="Episode 1"), encoding="utf-8")
    (tmp_path / "y.txt").write_text(KUKU_TXT.format(label="Episode 1"), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate episode labels"):
        find_episode_files(tmp_path)


def test_run_all_end_to_end_on_a_new_srt_show_without_an_api_key(tmp_path):
    inp = tmp_path / "new_show"
    inp.mkdir()
    (inp / "ep1.srt").write_text(_srt(60), encoding="utf-8")
    out = tmp_path / "run"

    result = subprocess.run(
        [sys.executable, str(ROOT / "run_all.py"), "--input", str(inp), "--output", str(out), "--no-llm"],
        capture_output=True, text=True, cwd=tmp_path, timeout=300,
    )
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]

    rows = json.loads((out / "ranked_promos" / "promos_submission.json").read_text(encoding="utf-8"))
    assert rows, "expected at least one promo"
    for r in rows:
        seg = r["segments"][0]
        assert 20 <= seg["end"] - seg["start"] <= 60
        assert r["episode"] == "ep1"
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    csv = pd.read_csv(out / "ranked_promos" / "promos_submission.csv", encoding="utf-8-sig")
    assert len(csv) == len(rows)


def test_run_all_explains_when_no_promo_window_can_be_built(tmp_path):
    inp = tmp_path / "too_short"
    inp.mkdir()
    (inp / "short.srt").write_text(_srt(3), encoding="utf-8")  # 12 seconds in total

    result = subprocess.run(
        [sys.executable, str(ROOT / "run_all.py"), "--input", str(inp), "--output", str(tmp_path / "run"), "--no-llm"],
        capture_output=True, text=True, cwd=tmp_path, timeout=300,
    )
    assert result.returncode != 0
    assert "No promo windows could be built" in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
