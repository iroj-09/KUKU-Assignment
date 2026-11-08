"""Transparent baseline heuristic scoring for promo candidates.

Features:
- Time-aware hook extraction (opening window, config.HOOK_WINDOW_SECONDS) instead of character slicing.
- Time-aware cliffhanger extraction (closing window, config.CLIFFHANGER_WINDOW_SECONDS).
- Speaker alternation / dialogue velocity tracking.
- Emotion keyword density and standalone length heuristics.
"""

from __future__ import annotations

import sys
from pathlib import Path as _Path

# Make the project-root config.py importable when running `python src/<script>.py`.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
import config  # noqa: E402

HOOK_TERMS = [
    "what", "why", "no", "stop", "how dare", "you lied", "betray", "betrayal",
    "marry", "marriage", "kill", "secret", "caught", "never", "listen", "who",
    "wait", "look at me", "duke", "bastard", "soldier", "liar", "impossible"
]

CLIFF_TERMS = [
    "but", "unless", "who are you", "what happened", "you will", "not yet",
    "the truth", "secret", "door", "footsteps", "wait", "tomorrow", "or else",
    "kill", "die", "blood", "brand", "burn", "promise", "never", "answer me",
    "silence", "touch", "gun", "knife", "blade"
]

EMOTION_TERMS = [
    "cry", "tears", "shock", "shocked", "furious", "scream", "screaming",
    "betray", "heartbroken", "desperate", "gasp", "slap", "blood", "gun",
    "threat", "revenge", "rage", "hatred", "love", "pain", "shivering",
    "trembling", "plead", "beg", "choking", "murder"
]


def _hits(text: str, terms: list[str]) -> int:
    t = (text or "").lower()
    return sum(1 for term in terms if term in t)


def _extract_time_windows(candidate: dict) -> tuple[str, str, int]:
    """Extract opening and ending text using true event timestamps when available."""
    events = candidate.get("events", [])
    clip_start = float(candidate.get("start", 0.0))
    clip_end = float(candidate.get("end", clip_start + candidate.get("duration", 30.0)))

    if not events:
        text = candidate.get("transcript", "")
        return text[:350], text[-450:], 0

    hook_events = [
        e for e in events
        if float(e.get("start", 0.0)) <= clip_start + config.HOOK_WINDOW_SECONDS
    ]
    if not hook_events and events:
        hook_events = events[:1]

    cliff_events = [
        e for e in events
        if float(e.get("end", clip_end)) >= clip_end - config.CLIFFHANGER_WINDOW_SECONDS
    ]
    if not cliff_events and events:
        cliff_events = events[-1:]

    hook_text = " ".join(e.get("text", "") for e in hook_events)
    cliff_text = " ".join(e.get("text", "") for e in cliff_events)

    # Count dialogue speaker alternations
    dialogue_types = [
        e.get("type", "") for e in events
        if e.get("type", "").upper() not in ("CAMERA", "ACTION", "SOUND FX", "SOUND")
    ]
    turns = sum(1 for i in range(1, len(dialogue_types)) if dialogue_types[i] != dialogue_types[i - 1])

    return hook_text, cliff_text, turns


def heuristic_score(candidate: dict) -> dict:
    """Calculate transparent multi-factor heuristic score for a candidate clip."""
    full_text = candidate.get("transcript", "")
    duration = max(1.0, float(candidate.get("duration", 30.0)))
    words = full_text.split()
    word_count = len(words)
    # WPM must reflect spoken words only; camera/action/sound lines are not spoken.
    events = candidate.get("events", [])
    if events:
        spoken_words = sum(
            len(e.get("text", "").split()) for e in events
            if e.get("type", "").upper() not in ("CAMERA", "ACTION", "SOUND FX", "SOUND")
        )
    else:
        spoken_words = word_count
    wpm = round((spoken_words / duration) * 60, 1)

    hook_text, cliff_text, dialogue_turns = _extract_time_windows(candidate)

    # 1. Hook score: hits in the first 3.5 seconds
    hook_hits = _hits(hook_text, HOOK_TERMS)
    hook = min(10.0, hook_hits * 2.2 + 2.0)

    # 2. Cliffhanger score: hits in the final 5.5 seconds
    cliff_hits = _hits(cliff_text, CLIFF_TERMS)
    cliff = min(10.0, cliff_hits * 2.0 + 1.5)

    # 3. Emotion score: emotional tension across the full clip
    emotion_hits = _hits(full_text, EMOTION_TERMS)
    emotion = min(10.0, emotion_hits * 1.5)

    # 4. Dialogue and pacing score: rewards active dialogue and healthy turnover
    dialogue_events = sum(
        1 for e in candidate.get("events", [])
        if e.get("type", "").upper() not in ("CAMERA", "ACTION", "SOUND FX", "SOUND")
    )
    dialogue = min(10.0, dialogue_events * 0.8 + min(dialogue_turns, 4) * 0.5)

    # 5. Standalone comprehension heuristic
    # Balanced length (neither an empty clip nor an impenetrable wall of text)
    if 25 <= word_count <= 180 and 80 <= wpm <= 210:
        standalone = 5.0
    elif word_count >= 15:
        standalone = 3.5
    else:
        standalone = 2.0

    # Composite weighted total (0 - 100 scale)
    total = (
        0.30 * hook
        + 0.30 * cliff
        + 0.20 * emotion
        + 0.10 * dialogue
        + 0.10 * standalone
    )

    return {
        "hook_score": round(hook, 2),
        "cliffhanger_score": round(cliff, 2),
        "emotion_score": round(emotion, 2),
        "dialogue_score": round(dialogue, 2),
        "standalone_score": round(standalone, 2),
        "baseline_score": round(total * 10, 2),
        "wpm": wpm,
        "dialogue_turns": dialogue_turns,
    }
