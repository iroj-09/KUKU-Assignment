"""Parse Kuku, SRT subtitle, and Fountain screenplay files into structured JSON."""

from __future__ import annotations
import json
import re
from pathlib import Path

TIME_RE = re.compile(r"^\s*(\d{2}:\d{2}\.\d{2})\s*$")
EVENT_RE = re.compile(
    r"^Start:\s*\((\d{2}:\d{2}\.\d{2})\)\s*\|\s*End:\s*\((\d{2}:\d{2}\.\d{2})\)\s*$"
)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*$", re.IGNORECASE)
SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)


def to_seconds(value: str) -> float:
    """Convert mm:ss.ff, hh:mm:ss.ff, or hh:mm:ss,fff string into decimal seconds."""
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 2:
        mm, rest = parts
        ss_parts = rest.split(".")
        ss = int(ss_parts[0])
        fraction = int(ss_parts[1]) if len(ss_parts) > 1 else 0
        divisor = 10 ** len(ss_parts[1]) if len(ss_parts) > 1 else 1
        return int(mm) * 60 + ss + fraction / divisor
    elif len(parts) == 3:
        hh, mm, rest = parts
        ss_parts = rest.split(".")
        ss = int(ss_parts[0])
        fraction = int(ss_parts[1]) if len(ss_parts) > 1 else 0
        divisor = 10 ** len(ss_parts[1]) if len(ss_parts) > 1 else 1
        return int(hh) * 3600 + int(mm) * 60 + ss + fraction / divisor
    return float(value)


def parse_kuku_text(text: str, filename: str) -> dict:
    """Parse standard Kuku-style timestamped screenplay format."""
    episode_match = re.search(r"^EPISODE NUMBER:\s*(.+)$", text, re.M)
    logline_match = re.search(r"^EPISODE LOGLINE:\s*(.+)$", text, re.M)
    continuity_match = re.search(r"^CONTINUITY NOTES:\s*(.+)$", text, re.M)
    lines = text.splitlines()
    scenes, current_scene, current_label = [], None, "GENERAL"
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        sm = SCENE_RE.match(line)
        if sm:
            if current_scene:
                scenes.append(current_scene)
            current_scene = {
                "scene_number": int(sm.group(1)),
                "heading": "",
                "start": None,
                "end": None,
                "events": [],
            }
            current_label = "GENERAL"
            i += 1
            continue

        if current_scene is not None:
            if line.startswith("Scene heading:"):
                current_scene["heading"] = line.split(":", 1)[1].strip()
            elif line.startswith("Scene start:"):
                current_scene["start"] = to_seconds(line.split(":", 1)[1].strip())
            elif line.startswith("Scene end:"):
                current_scene["end"] = to_seconds(line.split(":", 1)[1].strip())

        # Section or speaker header
        if line.startswith("**") and line.endswith(":**"):
            current_label = line.strip("*").strip(":").strip()
        elif (
            line.endswith(":")
            and not line.startswith(("Start:", "End:", "Scene "))
            and len(line) < 100
        ):
            current_label = line[:-1].strip()

        em = EVENT_RE.match(line)
        if em:
            start, end = to_seconds(em.group(1)), to_seconds(em.group(2))
            body = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if (
                    EVENT_RE.match(nxt)
                    or SCENE_RE.match(nxt)
                    or nxt.startswith("--- SCRIPT")
                ):
                    break
                if nxt.startswith("**") and nxt.endswith(":**"):
                    break
                if nxt and nxt not in ("Actions and dialogue:",):
                    body.append(nxt)
                j += 1
            content = " ".join(body).strip()
            if current_scene is None:
                current_scene = {
                    "scene_number": 1,
                    "heading": "",
                    "start": None,
                    "end": None,
                    "events": [],
                }
            current_scene["events"].append({
                "type": current_label,
                "start": start,
                "end": end,
                "duration": round(max(0.0, end - start), 2),
                "text": content,
            })
            i = j
            continue
        i += 1

    if current_scene:
        scenes.append(current_scene)

    for s in scenes:
        starts = [e["start"] for e in s["events"]]
        ends = [e["end"] for e in s["events"]]
        if s["start"] is None and starts:
            s["start"] = min(starts)
        if s["end"] is None and ends:
            s["end"] = max(ends)

    all_events = [e for s in scenes for e in s["events"]]
    return {
        "episode_file": filename,
        "episode": (
            episode_match.group(1).strip()
            if episode_match
            else Path(filename).stem
        ),
        "logline": logline_match.group(1).strip() if logline_match else "",
        "continuity_notes": (
            continuity_match.group(1).strip() if continuity_match else ""
        ),
        "scene_count": len(scenes),
        "event_count": len(all_events),
        "scenes": scenes,
    }


def parse_srt_text(text: str, filename: str) -> dict:
    """Parse SubRip (.srt) subtitle format into timestamped scene events."""
    blocks = re.split(r"\n\s*\n", text.strip())
    events = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        # Find line with time arrow
        time_idx = next(
            (idx for idx, ln in enumerate(lines) if "-->" in ln), None
        )
        if time_idx is None:
            continue
        tm = SRT_TIME_RE.match(lines[time_idx])
        if not tm:
            # Fallback split
            parts = lines[time_idx].split("-->")
            start = to_seconds(parts[0].strip())
            end = to_seconds(parts[1].strip())
        else:
            h1, m1, s1, ms1, h2, m2, s2, ms2 = tm.groups()
            start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
            end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000

        sub_text = " ".join(lines[time_idx + 1:]).strip()
        # Clean HTML styling tags if present in SRT
        sub_text = re.sub(r"<[^>]+>", "", sub_text)
        if sub_text and end > start:
            # Extract speaker if prefixed (e.g. "JULIANA: No!")
            speaker = "DIALOGUE"
            spk_match = re.match(r"^([A-Z\s]{2,20}):\s*(.+)$", sub_text)
            if spk_match:
                speaker = spk_match.group(1).strip()
                sub_text = spk_match.group(2).strip()

            events.append({
                "type": speaker,
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "text": sub_text,
            })

    scene = {
        "scene_number": 1,
        "heading": "SUBTITLE TIMELINE",
        "start": events[0]["start"] if events else 0.0,
        "end": events[-1]["end"] if events else 0.0,
        "events": events,
    }
    return {
        "episode_file": filename,
        "episode": Path(filename).stem,
        "logline": "Parsed from SRT subtitles",
        "continuity_notes": "",
        "scene_count": 1 if events else 0,
        "event_count": len(events),
        "scenes": [scene] if events else [],
    }


def parse_fountain_text(text: str, filename: str) -> dict:
    """Parse Fountain screenplay format into scenes and simulated dialogue events."""
    lines = text.splitlines()
    scenes = []
    current_scene = None
    current_time = 0.0
    all_events = []

    scene_heading_re = re.compile(
        r"^(INT\.|EXT\.|INT/EXT\.|EST\.)\s+(.+)$", re.IGNORECASE
    )
    character_re = re.compile(r"^[A-Z0-9\s_'-]{2,30}$")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        sh_match = scene_heading_re.match(line)
        if sh_match:
            if current_scene:
                scenes.append(current_scene)
            current_scene = {
                "scene_number": len(scenes) + 1,
                "heading": line,
                "start": current_time,
                "end": None,
                "events": [],
            }
            i += 1
            continue

        if character_re.match(line) and i + 1 < len(lines):
            speaker = line
            dialogue_lines = []
            j = i + 1
            while j < len(lines) and lines[j].strip():
                dialogue_lines.append(lines[j].strip())
                j += 1
            dial_text = " ".join(dialogue_lines)
            # Estimate speech duration at ~2.5 words per second
            word_count = len(dial_text.split())
            duration = max(1.5, round(word_count / 2.5, 2))
            start_t = current_time
            end_t = round(start_t + duration, 2)
            current_time = end_t + 0.5  # 0.5s pause between lines

            ev = {
                "type": speaker,
                "start": start_t,
                "end": end_t,
                "duration": duration,
                "text": f'{speaker}: "{dial_text}"',
            }
            if current_scene is None:
                current_scene = {
                    "scene_number": 1,
                    "heading": "SCENE 1",
                    "start": 0.0,
                    "end": None,
                    "events": [],
                }
            current_scene["events"].append(ev)
            all_events.append(ev)
            i = j
            continue

        i += 1

    if current_scene:
        current_scene["end"] = current_time
        scenes.append(current_scene)

    return {
        "episode_file": filename,
        "episode": Path(filename).stem,
        "logline": "Parsed from Fountain screenplay",
        "continuity_notes": "",
        "scene_count": len(scenes),
        "event_count": len(all_events),
        "scenes": scenes,
    }


def parse_episode(path: str | Path) -> dict:
    """Auto-detect format and parse screenplay or subtitle file into structured JSON."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")

    suffix = path.suffix.lower()
    if suffix == ".srt" or ("-->" in text and re.search(r"^\d+\s*$", text, re.M)):
        return parse_srt_text(text, path.name)
    elif suffix == ".fountain":
        return parse_fountain_text(text, path.name)
    else:
        return parse_kuku_text(text, path.name)


def parse_directory(input_dir: str | Path, output_dir: str | Path) -> list[dict]:
    """Parse all supported screenplay files in directory (.txt, .srt, .fountain)."""
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    valid_extensions = {".txt", ".srt", ".fountain"}
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in valid_extensions:
            episode = parse_episode(path)
            results.append(episode)
            out = output_dir / (path.stem + ".json")
            out.write_text(
                json.dumps(episode, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return results
