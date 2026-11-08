"""Sanity checks on whatever screenplay pack is in data/input.

The pack is confidential and is not in the repository, so these tests skip on a clean checkout and adapt
to any pack size (the supplied pack has 50 episodes; a new show at an interview may have any number).
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from parser import parse_episode  # noqa: E402

PACK = Path(__file__).parents[1] / "data" / "input"
FILES = sorted(PACK.glob("*.txt")) if PACK.exists() else []

pytestmark = pytest.mark.skipif(not FILES, reason="no screenplay pack in data/input (it is not committed)")


def test_pack_is_not_empty():
    assert len(FILES) >= 1


def test_all_parsed_event_timestamps_are_ordered():
    for path in FILES:
        ep = parse_episode(path)
        assert ep["event_count"] > 0, path.name
        for scene in ep["scenes"]:
            for event in scene["events"]:
                assert event["end"] >= event["start"], (path.name, event)
