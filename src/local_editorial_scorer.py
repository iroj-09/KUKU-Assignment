"""
Local, rule-based editorial pre-screening for promo candidates.

Run from the project root:
    python src/local_editorial_scorer.py
    python src/local_editorial_scorer.py --input outputs/ranked_promos/promo_shortlist.csv
    python src/local_editorial_scorer.py --top 20

Important:
- This is a heuristic pre-screen, NOT an AI/editorial validation.
- The supplied shortlist transcript is a flattened excerpt without reliable
  per-line timestamps. Hook/ending excerpts are extracted from approximate
  transcript positions; do not treat their timestamps as verified.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent

# Weighted rubric: each component is scored from 0 to 10.
WEIGHTS = {
    "hook": 0.25,
    "cliffhanger": 0.25,
    "emotional_intensity": 0.20,
    "standalone_context": 0.15,
    "narrative_progression": 0.15,
}

HOOK_TERMS = {
    "what", "why", "who", "how", "never", "impossible", "secret",
    "truth", "betray", "betrayal", "love", "murder", "kill", "dead",
    "marry", "marriage", "husband", "wife", " duke", "princess",
    "prove", "choose", "promise", "swear", "listen", "stop",
}
CLIFFHANGER_TERMS = {
    "but", "unless", "until", "if", "then", "never", "secret",
    "truth", "reveal", "wait", "stop", "kill", "die", "dead",
    "fire", "gun", "sword", "knife", "blood", "brand", "touch",
    "open", "behind", "return", "found", "pregnant", "marry",
    "divorce", "betray", "prove", "promise",
}
EMOTION_TERMS = {
    "love", "hate", "fear", "terrified", "cry", "tears", "rage",
    "furious", "angry", "scream", "shout", "desperate", "heart",
    "pain", "hurt", "betray", "betrayal", "jealous", "revenge",
    "threat", "threaten", "murder", "kill", "devastated", "shocked",
    "trembling", "weeping", "beg", "begging", "silence",
}
PROGRESSION_TERMS = {
    "then", "but", "suddenly", "however", "until", "because",
    "reveals", "revealed", "realizes", "realized", "discovers",
    "discovered", "enters", "arrives", "raises", "grabs", "attacks",
    "threatens", "confesses", "orders", "refuses", "accepts",
    "interrupts", "turns", "steps", "opens", "falls",
}
ACTION_TERMS = {
    "raises", "grabs", "throws", "slaps", "hits", "attacks", "kisses",
    "kneels", "runs", "falls", "enters", "leaves", "opens", "closes",
    "draws", "points", "screams", "cries", "trembles", "collapses",
    "shoots", "stabs", "threatens", "holds", "pulls", "pushes",
}
CONTEXT_TERMS = {
    "because", "but", "after", "before", "husband", "wife", "family",
    "mother", "father", "daughter", "son", "sister", "brother",
    "married", "marriage", "duke", "duchess", "soldier", "prince",
    "princess", "servant", "guard", "king", "queen", "court",
    "betrayal", "prison", "dungeon", "engagement", "wedding",
}

WORD_RE = re.compile(r"[A-Za-z']+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?])(?=[\"'])")


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(str(text or ""))]


def count_hits(tokens: Iterable[str], vocabulary: set[str]) -> int:
    return sum(1 for token in tokens if token in vocabulary)


def clamp_score(value: float) -> int:
    return max(0, min(10, int(round(value))))


def split_transcript(text: str) -> list[str]:
    parts = [p.strip() for p in SENTENCE_SPLIT_RE.split(str(text or "")) if p.strip()]
    # Fallback for transcripts with no punctuation.
    return parts or ([str(text).strip()] if str(text).strip() else [])


def approximate_excerpt(text: str, fraction: float, side: str) -> str:
    """
    Extract a small transcript slice based on character position.
    This is only an approximate proxy because the CSV has no event timestamps.
    """
    text = str(text or "").strip()
    if not text:
        return ""
    width = max(1, int(len(text) * fraction))
    if side == "start":
        excerpt = text[:width]
    else:
        excerpt = text[-width:]
    # Avoid cutting too aggressively in the middle of a word.
    if side == "start":
        excerpt = excerpt.rsplit(" ", 1)[0] if " " in excerpt else excerpt
    else:
        excerpt = excerpt.split(" ", 1)[-1] if " " in excerpt else excerpt
    return excerpt.strip()


def score_hook(text: str, duration: float) -> tuple[int, str]:
    # The transcript slice approximates the first 3 seconds by character share.
    fraction = min(0.35, max(0.05, 3.0 / max(duration, 1.0)))
    excerpt = approximate_excerpt(text, fraction, "start")
    tokens = words(excerpt)
    if not tokens:
        return 0, excerpt

    hits = count_hits(tokens, HOOK_TERMS)
    punctuation = int("?" in excerpt) + int("!" in excerpt)
    dialogue = int('"' in excerpt or "“" in excerpt)
    action = count_hits(tokens, ACTION_TERMS)

    score = 2.0 + min(hits, 3) * 1.4 + punctuation * 0.8 + dialogue * 0.8 + min(action, 2) * 0.5
    return clamp_score(score), excerpt


def score_cliffhanger(text: str, duration: float) -> tuple[int, str]:
    # The transcript slice approximates the final 5 seconds by character share.
    fraction = min(0.45, max(0.07, 5.0 / max(duration, 1.0)))
    excerpt = approximate_excerpt(text, fraction, "end")
    tokens = words(excerpt)
    if not tokens:
        return 0, excerpt

    hits = count_hits(tokens, CLIFFHANGER_TERMS)
    unresolved = int(any(term in tokens for term in {
        "but", "if", "unless", "until", "then", "wait", "never"
    }))
    punctuation = int("?" in excerpt) + int("!" in excerpt)
    action = count_hits(tokens, ACTION_TERMS)

    score = 1.5 + min(hits, 4) * 1.25 + unresolved * 1.2 + punctuation * 0.7 + min(action, 2) * 0.6
    return clamp_score(score), excerpt


def score_emotion(text: str) -> int:
    tokens = words(text)
    if not tokens:
        return 0
    hits = count_hits(tokens, EMOTION_TERMS)
    density = hits / max(len(tokens), 1)
    score = 2.0 + min(hits, 12) * 0.45 + min(density * 20, 2.0)
    return clamp_score(score)


def score_context(text: str) -> int:
    tokens = words(text)
    if not tokens:
        return 0
    hits = count_hits(tokens, CONTEXT_TERMS)
    # Named characters and explicit relational/context terms help a new viewer.
    quoted_dialogue = int('"' in text or "“" in text)
    distinct_capitalized = len(set(re.findall(r"\b[A-Z][a-z]{2,}\b", text)))
    score = 2.0 + min(hits, 8) * 0.55 + min(distinct_capitalized, 4) * 0.45 + quoted_dialogue * 0.5
    return clamp_score(score)


def score_progression(text: str) -> int:
    tokens = words(text)
    if not tokens:
        return 0
    progression_hits = count_hits(tokens, PROGRESSION_TERMS)
    action_hits = count_hits(tokens, ACTION_TERMS)
    sentences = split_transcript(text)
    sentence_variety = min(len(sentences), 5)
    score = (
        1.5
        + min(progression_hits, 6) * 0.65
        + min(action_hits, 6) * 0.45
        + sentence_variety * 0.35
    )
    return clamp_score(score)


def evaluate_row(row: pd.Series) -> dict:
    transcript = str(row.get("transcript", "") or "")
    try:
        duration = float(row.get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0

    hook_score, hook_excerpt = score_hook(transcript, duration)
    cliff_score, ending_excerpt = score_cliffhanger(transcript, duration)
    emotion_score = score_emotion(transcript)
    context_score = score_context(transcript)
    progression_score = score_progression(transcript)

    components = {
        "hook_score": hook_score,
        "cliffhanger_score": cliff_score,
        "emotional_intensity_score": emotion_score,
        "standalone_context_score": context_score,
        "narrative_progression_score": progression_score,
    }

    total = round(
        hook_score * WEIGHTS["hook"]
        + cliff_score * WEIGHTS["cliffhanger"]
        + emotion_score * WEIGHTS["emotional_intensity"]
        + context_score * WEIGHTS["standalone_context"]
        + progression_score * WEIGHTS["narrative_progression"],
        2,
    ) * 10

    return {
        "episode": row.get("episode", ""),
        "start": row.get("start", ""),
        "end": row.get("end", ""),
        "duration": duration,
        "heuristic_baseline_score": row.get("baseline_score", ""),
        **components,
        "local_editorial_score": round(total, 2),
        "evaluation_mode": "heuristic_editorial",
        "hook_excerpt_approx": hook_excerpt,
        "ending_excerpt_approx": ending_excerpt,
        "timestamp_note": (
            "Excerpt positions are approximate character-based estimates; "
            "the source CSV does not provide event-level timestamps."
        ),
        "review_status": "needs_human_review",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Local editorial pre-screening for promo candidates.")
    parser.add_argument("--input", default="outputs/ranked_promos/promo_shortlist.csv")
    parser.add_argument("--output-dir", default="outputs/editorial")
    parser.add_argument("--top", type=int, default=0, help="Print only the top N rows; 0 prints top 15.")
    args = parser.parse_args()

    input_path = BASE_DIR / args.input
    output_dir = BASE_DIR / args.output_dir
    if not input_path.exists():
        raise FileNotFoundError(
            f"Shortlist not found: {input_path}\n"
            "Run src/deduplicate.py first or pass --input with the correct CSV path."
        )

    source = pd.read_csv(input_path)
    if "transcript" not in source.columns:
        raise ValueError("Input CSV must contain a 'transcript' column.")

    # Keep original values and safely normalize missing transcript cells.
    source["transcript"] = source["transcript"].fillna("").astype(str)

    results = [evaluate_row(row) for _, row in source.iterrows()]
    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values(
        ["local_editorial_score", "episode", "start"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    result_df.insert(0, "local_rank", range(1, len(result_df) + 1))

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "local_editorial_scores.csv"
    json_path = output_dir / "local_editorial_scores.json"

    result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    display_count = args.top if args.top > 0 else 15
    display_columns = [
        "local_rank", "episode", "start", "end", "duration",
        "local_editorial_score", "hook_score", "cliffhanger_score",
        "emotional_intensity_score", "standalone_context_score",
        "narrative_progression_score",
    ]

    print("\nLOCAL EDITORIAL PRE-SCREEN COMPLETE")
    print(f"Candidates processed : {len(result_df)}")
    print("Evaluation mode      : heuristic_editorial (not Gemini)")
    print(f"CSV                  : {csv_path}")
    print(f"JSON                 : {json_path}")
    print("\nTop candidates:")
    print(result_df[display_columns].head(display_count).to_string(index=False))
    print(
        "\nReminder: scores are rule-based prioritization signals. "
        "Manually verify the actual opening, ending, and story context."
    )


if __name__ == "__main__":
    main()
