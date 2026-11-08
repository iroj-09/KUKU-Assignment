# Dataset Audit — Kuku Promo Discovery

> **Historical snapshot.** This audit describes the earlier run that used fixed 5-second sliding windows
> (7,749 windows, 74 shortlisted candidates). Those outputs are archived in
> `outputs/archive/sliding_windows_20261107/`. The current outputs in `outputs/` come from the beat-aligned
> run (53,182 windows, 60 shortlisted candidates, all 50 episodes covered); see section 4 of
> `SYSTEM_ARCHITECTURE.md` for its numbers.

**Project:** Screenplay-Based Promo Discovery for *I Married a Broken Soldier. He was a Duke.*  
**Audit scope:** Supplied timestamped screenplay files, candidate-generation outputs, editorial evidence, Gemini evaluations, and final hybrid ranking included in this project snapshot.

## 1. Source dataset

| Item | Result |
|---|---:|
| Supplied screenplay files | 50 TXT files |
| Episodes parsed | 50 |
| Parsed scenes | 100 |
| Timestamped screenplay events | 3,727 |
| Processed episode JSON files | 50 |

The input consists of timestamped English screenplay text. Events contain screenplay descriptions such as dialogue, action, camera directions, and sound cues, with event-level start and end times. The source material is retained under `data/input/`; parsed records are under `data/processed/`.

## 2. Candidate generation and reduction

| Stage | Count | Explanation |
|---|---:|---|
| Generated duration-compliant windows | 7,749 | Candidate windows generated from parsed events, within the assignment's 20–60 second duration range |
| Per-episode baseline shortlist | 600 | Up to 12 candidates retained per episode using the baseline heuristic |
| Deduplicated shortlist | 74 | Overlapping/redundant candidates reduced using the configured overlap rule and per-episode cap |
| Episodes represented in final shortlist | 50 | Final candidates span all 50 supplied episodes |

The deduplication step uses an overlap ratio based on the intersection duration divided by the shorter candidate duration, with a threshold of 0.5, and limits the shortlist to at most three candidates per episode. The final shortlist contains 74 candidates.

## 3. Editorial evidence preparation

Editorial evidence was prepared for all 74 shortlisted candidates:

- 74 candidate records in `outputs/editorial/editorial_evidence.csv` and `.json`.
- 74 records have `evaluation_status` set to `timestamp_evidence_prepared_not_editorially_validated` in the evidence-preparation output. This status describes the evidence-preparation stage; it is not the final Gemini evaluation status.
- 0 evidence-preparation failures are recorded in `outputs/editorial/editorial_evidence_failures.json`.
- Evidence includes the candidate's episode and clip bounds, duration, event counts, opening excerpt, ending excerpt, and full screenplay transcript.

**Boundary limitation:** screenplay events can begin before a candidate window or continue after it. The earlier boundary audit found 217 such event crossings across 72 candidate records. These crossings are not word-level clipping measurements; the source provides event-level timestamps, not word-level timestamps. They should be inspected during editorial review rather than silently treated as fully contained events.

## 4. Gemini editorial evaluation

All 74 shortlisted candidates have a Gemini evaluation in the supplied final project outputs.

| Metric | Result |
|---|---:|
| Candidates evaluated by Gemini | 74 / 74 |
| Evaluation failures in final evaluation set | 0 |
| Average Gemini final score | 70.57 / 100 |
| Minimum Gemini final score | 33.00 / 100 |
| Maximum Gemini final score | 94.00 / 100 |
| Marked `is_promising = true` | 64 / 74 (86.5%) |
| Marked `is_promising = false` | 10 / 74 (13.5%) |

The Gemini rubric records scores for hook, cliffhanger, emotional intensity, standalone context, and narrative progression, along with hook/cliffhanger descriptions, timestamps where supplied, explanatory text, and risks. The evaluator output is stored in:

- `outputs/editorial/editorial_evaluations.json`
- `outputs/editorial/editorial_evaluations.csv`

The JSON/CSV `final_score` is the Gemini editorial score. The `is_promising` flag is a model judgment and is not a substitute for structural validation or human approval.

## 5. Local heuristic score and hybrid ranking

A separate local heuristic/editorial score is retained for each of the 74 candidates.

| Metric | Result |
|---|---:|
| Average local editorial score | 40.74 / 100 |
| Minimum local editorial score | 26.50 / 100 |
| Maximum local editorial score | 62.00 / 100 |
| Average hybrid ranking score | 61.62 / 100 |

For candidates with Gemini evaluations, the final ranking uses:

`Hybrid score = 0.70 × Gemini editorial score + 0.30 × local editorial score`

All 74 rows in the supplied `final_ranking.csv` are marked as Gemini-evaluated and use the hybrid ranking basis `70% Gemini editorial + 30% local heuristic`.

### Top 10 candidates in the supplied final ranking

| Rank | Episode | Clip | Gemini score | Local score | Hybrid score | Hook/cliff compliance |
|---:|---|---:|---:|---:|---:|---|
| 1 | Episode 16 | 0–55s | 94.0 | 47.0 | 79.90 | PASS |
| 2 | Episode 32 | 105–150s | 83.0 | 62.0 | 76.70 | PASS* |
| 3 | Episode 42 | 25–75s | 86.0 | 50.5 | 75.35 | PASS |
| 4 | Episode 29 | 50–110s | 86.0 | 50.0 | 75.20 | PASS |
| 5 | Episode 46 | 35–95s | 84.5 | 50.5 | 74.30 | PASS |
| 6 | Episode 2 | 0–45s | 86.0 | 41.0 | 72.50 | PASS |
| 7 | Episode 45 | 55–90s | 81.0 | 50.0 | 71.70 | PASS |
| 8 | Episode 38 | 40–85s | 84.5 | 40.5 | 71.30 | PASS |
| 9 | Episode 1 | 35–85s | 81.0 | 48.5 | 71.25 | PASS |
| 10 | Episode 43 | 55–110s | 83.5 | 41.5 | 70.90 | PASS |

`PASS` in this table refers only to the stored hook/cliffhanger timestamp compliance fields. It does not certify that all screenplay events are wholly contained within the clip, nor that the promo is visually effective. `*` Episode 32 (105–150s) has a previously identified event crossing the 150-second clip boundary and should receive manual inspection.

## 6. Timestamp and duration validation

| Validation | Candidates |
|---|---:|
| Duration-valid (20–60 seconds) | 74 / 74 |
| Timestamp compliance PASS | 43 |
| Timestamp compliance PARTIAL | 28 |
| Timestamp compliance FAIL | 3 |

The timestamp compliance field checks whether the selected hook timestamp falls within the first three seconds of the candidate and whether the selected cliffhanger timestamp falls within the final five seconds. A missing or out-of-window timestamp prevents a full PASS. The status is independent of Gemini's `is_promising` flag.

The dashboard should display duration validity, timestamp compliance, Gemini score, local score, and human review status as separate fields.

## 7. Automated tests and reproducibility

The project includes:

- `tests/test_parser.py`: timestamp conversion and parser metadata/event extraction tests.
- `tests/test_dataset.py`: verifies that the supplied input pack contains 50 TXT files and that parsed event end times are not earlier than their start times.

The project review run reported **4 tests passed**. The dataset test checks the supplied local input directory; it will require the screenplay TXT files to be present. The final Gemini evaluations and ranking are already saved as output artifacts, so opening the dashboard does not require rerunning the Gemini batch evaluation.

## 8. Output artifacts

| File | Purpose |
|---|---|
| `outputs/ranked_promos/promo_shortlist.csv` | Deduplicated candidate shortlist |
| `outputs/editorial/editorial_evidence.csv` / `.json` | Transcript evidence and candidate boundary excerpts |
| `outputs/editorial/editorial_evaluations.csv` / `.json` | Gemini editorial evaluations |
| `outputs/editorial/local_editorial_scores.csv` / `.json` | Local heuristic/editorial scores |
| `outputs/ranked_promos/final_ranking.csv` | Final hybrid ranking and validation fields |
| `outputs/ranked_promos/top_10_for_review.csv` | Top candidates for human editorial review |

These outputs contain screenplay-derived excerpts and should be treated as confidential assignment material. Do not publish them or the source screenplays without authorization.

## 9. Limitations and interpretation

1. **Screenplay-only analysis:** The system analyzes timestamped screenplay text. It does not process episode video or audio.
2. **No visual/audio verification:** It cannot confirm actor performance, facial expressions, shot composition as actually filmed, editing pace, music impact, sound mix, or final audience retention.
3. **Event-level timing:** Source timestamps are attached to screenplay events. Word-level timing is unavailable, and events may cross candidate boundaries.
4. **Model judgments are provisional:** Gemini's hook, cliffhanger, and `is_promising` assessments can be incorrect or overconfident. The local score is a heuristic, not an independent human judgment.
5. **Timestamp PASS is narrow:** It validates the location of selected hook/cliffhanger timestamps against the configured windows. It does not establish creative quality or guarantee that every event fits neatly inside the clip.
6. **Human review remains necessary:** Editors should review the opening, ending, full transcript, boundary-crossing events, and narrative context before selecting a promo.

## 10. Audit conclusion

The current project snapshot contains 50 parsed screenplay episodes, 7,749 generated duration-compliant windows, a 74-candidate deduplicated shortlist, 74 completed Gemini evaluations, local heuristic scores, and a final hybrid ranking. All 74 final candidates meet the 20–60 second duration constraint. Hook/cliffhanger timestamp compliance is PASS for 43, PARTIAL for 28, and FAIL for 3 candidates.

The project should therefore be described as an **AI-assisted, screenplay-based promo discovery and editorial prioritization prototype**. It narrows a large screenplay dataset into a ranked review queue; it does not automatically produce or certify finished video promos.
