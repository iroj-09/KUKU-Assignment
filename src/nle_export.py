"""Export ranked promo candidates into standard NLE video editor formats.

Supports:
1. DaVinci Resolve Timeline Marker CSV
2. Adobe Premiere Pro Marker CSV
3. CMX 3600 Edit Decision List (EDL)
"""

from __future__ import annotations
import csv
import io
import pandas as pd


def seconds_to_frames(seconds: float, fps: int = 24) -> int:
    return int(round(max(0.0, float(seconds)) * fps))


def seconds_to_timecode(seconds: float, fps: int = 24) -> str:
    """Convert decimal seconds to SMPTE timecode (HH:MM:SS:FF)."""
    return frames_to_timecode(seconds_to_frames(seconds, fps), fps)


def frames_to_timecode(total_frames: int, fps: int = 24) -> str:
    total_frames = max(0, int(total_frames))
    ff = total_frames % fps
    total_seconds = total_frames // fps
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def export_davinci_markers(df: pd.DataFrame, fps: int = 24) -> str:
    """Generate DaVinci Resolve Timeline Marker CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Description", "In", "Out", "Duration", "Color"])

    for _, row in df.iterrows():
        rank = row.get("rank", "")
        ep = row.get("episode", "Clip")
        start = float(row.get("clip_start", row.get("start", 0.0)))
        end = float(row.get("clip_end", row.get("end", 0.0)))
        dur = end - start
        score = row.get("ranking_score", row.get("final_score", row.get("baseline_score", "")))

        name = f"Rank{rank}_{ep}" if rank != "" else f"Promo_{ep}"
        why = row.get("why_it_works", row.get("hook", ""))
        desc = f"Score: {score} | {why}" if why else f"Score: {score}"

        tc_in = seconds_to_timecode(start, fps)
        tc_out = seconds_to_timecode(end, fps)
        tc_dur = seconds_to_timecode(dur, fps)
        color = "Cyan" if float(score or 0) >= 75 else "Green"

        writer.writerow([name, desc, tc_in, tc_out, tc_dur, color])

    return output.getvalue()


def export_premiere_markers(df: pd.DataFrame, fps: int = 24) -> str:
    """Generate Adobe Premiere Pro Marker CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Marker Name", "Description", "In", "Out", "Duration", "Marker Type"])

    for _, row in df.iterrows():
        rank = row.get("rank", "")
        ep = row.get("episode", "Clip")
        start = float(row.get("clip_start", row.get("start", 0.0)))
        end = float(row.get("clip_end", row.get("end", 0.0)))
        dur = end - start
        score = row.get("ranking_score", row.get("final_score", row.get("baseline_score", "")))

        name = f"Rank{rank}_{ep}" if rank != "" else f"Promo_{ep}"
        why = row.get("why_it_works", row.get("hook", ""))
        desc = f"Score: {score} | {why}" if why else f"Score: {score}"

        tc_in = seconds_to_timecode(start, fps)
        tc_out = seconds_to_timecode(end, fps)
        tc_dur = seconds_to_timecode(dur, fps)

        writer.writerow([name, desc, tc_in, tc_out, tc_dur, "Comment"])

    return output.getvalue()


def export_cmx_edl(df: pd.DataFrame, title: str = "KUKU_PROMOS", fps: int = 24) -> str:
    """Generate industry standard CMX 3600 Edit Decision List (EDL)."""
    lines = [
        f"TITLE: {title}",
        "FCM: NON-DROP FRAME",
        "",
    ]

    # Work in whole frames so source and record durations always match (EDL requirement).
    record_frames = 0

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        ep = row.get("episode", f"Clip_{i}")
        start = float(row.get("clip_start", row.get("start", 0.0)))
        end = float(row.get("clip_end", row.get("end", 0.0)))
        src_in_f = seconds_to_frames(start, fps)
        src_out_f = seconds_to_frames(end, fps)

        src_in = frames_to_timecode(src_in_f, fps)
        src_out = frames_to_timecode(src_out_f, fps)
        rec_in = frames_to_timecode(record_frames, fps)
        record_frames += src_out_f - src_in_f
        rec_out = frames_to_timecode(record_frames, fps)

        why = str(row.get("why_it_works", "") or "").replace("\r", " ").replace("\n", " ").strip()
        rank = row.get("rank", i)

        lines.append(f"{i:03d}  AX       V     C        {src_in} {src_out} {rec_in} {rec_out}")
        lines.append(f"* FROM CLIP NAME: {ep}")
        if why:
            lines.append(f"* COMMENT: Rank {rank} - {why}")
        lines.append("")

    return "\n".join(lines)
