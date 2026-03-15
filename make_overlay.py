#!/usr/bin/env python3
"""
make_overlay.py — Generate an ASS subtitle file with a real elapsed time overlay
from a GoProTimeWarp speed timeline JSON.

Usage:
  python3 make_overlay.py <_speed_timeline.json> [options]

Options:
  --offset-video HH:MM:SS   Show timer only from this output timestamp (default: 00:00:00)
  --timer-start  HH:MM:SS   Initial timer value at first displayed frame (default: 00:00:00)
  --output       path.ass   Output file path (default: <input>_overlay.ass)
  --refresh      SECONDS    Subtitle refresh interval in seconds (default: 1.0)

Examples:
  # Clip 1 — timer starts at zero
  python3 make_overlay.py GH015116_1_SHUT_speed_timeline.json

  # Clip 2 — timer picks up where clip 1 ended (29:36 real time)
  python3 make_overlay.py GH025116_1_SHUT_speed_timeline.json --timer-start 00:29:36

  # Skip pre-race section in output video
  python3 make_overlay.py GH015116_1_SHUT_speed_timeline.json --offset-video 00:01:30

Burn into video:
  ffmpeg -i input.MP4 -vf "subtitles=overlay.ass" output.MP4
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_hms(s: str) -> float:
    """Parse HH:MM:SS, H:MM:SS, MM:SS, or plain seconds string → float seconds."""
    parts = s.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(parts[0])
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid time format: '{s}' (expected HH:MM:SS or MM:SS)")


def fmt_elapsed(seconds: float) -> str:
    """Format real elapsed seconds as MM:SS or HH:MM:SS."""
    seconds = max(0.0, seconds)
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def to_ass_time(seconds: float) -> str:
    """Convert float seconds to ASS timestamp format H:MM:SS.cc (centiseconds)."""
    seconds = max(0.0, seconds)
    total_cs = int(round(seconds * 100))
    cc = total_cs % 100
    total_s = total_cs // 100
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:d}:{m:02d}:{s:02d}.{cc:02d}"


def parse_iso(dt_str: str) -> datetime:
    """Parse ISO 8601 UTC string (with trailing Z) to timezone-aware datetime."""
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# ASS file generation
# ---------------------------------------------------------------------------

ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Timer,Arial,80,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,3,1,7,40,40,40,1
Style: Label,Arial,40,&H80FFFFFF,&H000000FF,&H00000000,&HA0000000,0,0,0,0,100,100,0,0,1,2,1,7,40,40,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def make_ass(segments: list, timer_start_s: float, offset_s: float, refresh: float = 1.0) -> str:
    """
    Build ASS subtitle content.

    Generates one pair of Dialogue lines per `refresh` seconds of output video (Timer + Label).
    Timer shows real elapsed time; Label shows the speed mode.
    """
    # Precompute real elapsed time at the START of each segment (from t=0, unadjusted)
    real_elapsed = []
    t = 0.0
    for seg in segments:
        real_elapsed.append(t)
        seg_real_duration = (parse_iso(seg["end_date"]) - parse_iso(seg["start_date"])).total_seconds()
        t += seg_real_duration

    # Compute the real elapsed value at offset_s so we can anchor timer_start there.
    # timer_start_s is the value shown AT the first displayed frame (offset_s), not at t=0.
    real_at_offset = 0.0
    for i, seg in enumerate(segments):
        seg_start = seg["start_cts_ms"] / 1000.0
        seg_end = seg["end_cts_ms"] / 1000.0
        if seg_start <= offset_s < seg_end:
            real_at_offset = real_elapsed[i] + (offset_s - seg_start) * seg["avg_speed"]
            break
        elif seg_end <= offset_s:
            real_at_offset = real_elapsed[i] + (parse_iso(seg["end_date"]) - parse_iso(seg["start_date"])).total_seconds()
    adjustment = timer_start_s - real_at_offset

    # Determine video time range
    if not segments:
        return ASS_HEADER

    video_start = offset_s
    video_end = segments[-1]["end_cts_ms"] / 1000.0

    lines = [ASS_HEADER]

    output_t = video_start
    while output_t < video_end:
        # Find which segment contains output_t
        seg_idx = None
        for i, seg in enumerate(segments):
            seg_start = seg["start_cts_ms"] / 1000.0
            seg_end = seg["end_cts_ms"] / 1000.0
            if seg_start <= output_t < seg_end:
                seg_idx = i
                break

        line_end = output_t + refresh
        ass_start = to_ass_time(output_t)
        ass_end = to_ass_time(min(line_end, video_end))

        if seg_idx is not None:
            seg = segments[seg_idx]
            seg_output_start = seg["start_cts_ms"] / 1000.0
            elapsed_in_seg = (output_t - seg_output_start) * seg["avg_speed"]
            current_real = real_elapsed[seg_idx] + elapsed_in_seg + adjustment
            timer_text = fmt_elapsed(current_real)
            label_text = seg["label"]

            lines.append(f"Dialogue: 0,{ass_start},{ass_end},Timer,,0,0,0,,{timer_text}")
            lines.append(f"Dialogue: 0,{ass_start},{ass_end},Label,,0,0,0,,{label_text}")
        else:
            # Gap between segments — find nearest previous segment's closing time
            prev_real = None
            for i in range(len(segments) - 1, -1, -1):
                if segments[i]["end_cts_ms"] / 1000.0 <= output_t:
                    seg = segments[i]
                    seg_real_dur = (parse_iso(seg["end_date"]) - parse_iso(seg["start_date"])).total_seconds()
                    prev_real = real_elapsed[i] + seg_real_dur + adjustment
                    break
            if prev_real is not None:
                lines.append(f"Dialogue: 0,{ass_start},{ass_end},Timer,,0,0,0,,{fmt_elapsed(prev_real)}")
            # No label during gaps

        output_t = line_end

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate ASS subtitle with real elapsed time from a GoProTimeWarp speed timeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("timeline", help="Path to _speed_timeline.json")
    parser.add_argument(
        "--offset-video",
        default="0",
        metavar="HH:MM:SS",
        help="Show timer only from this output timestamp (default: 00:00:00)",
    )
    parser.add_argument(
        "--timer-start",
        default="0",
        metavar="HH:MM:SS",
        help="Initial real elapsed time at first displayed frame (default: 00:00:00)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="path.ass",
        help="Output ASS file path (default: <timeline>_overlay.ass)",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Subtitle event duration in seconds (default: 1.0; use e.g. 0.04 for 25fps)",
    )
    args = parser.parse_args()

    # Validate and parse
    try:
        timer_start_s = parse_hms(args.timer_start)
        offset_s = parse_hms(args.offset_video)
    except argparse.ArgumentTypeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    timeline_path = Path(args.timeline)
    if not timeline_path.exists():
        print(f"Error: file not found: {timeline_path}", file=sys.stderr)
        sys.exit(1)

    with open(timeline_path, encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if not segments:
        print("Error: no segments found in timeline JSON.", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        stem = timeline_path.stem
        if stem.endswith("_speed_timeline"):
            stem = stem[: -len("_speed_timeline")]
        out_path = timeline_path.parent / f"{stem}_overlay.ass"

    # Generate ASS content
    ass_content = make_ass(segments, timer_start_s, offset_s, args.refresh)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    print(f"Device  : {data.get('device', 'unknown')}")
    print(f"Segments: {len(segments)}")
    print(f"Timer   : starts at {fmt_elapsed(timer_start_s)}")
    if offset_s > 0:
        print(f"Offset  : overlay from {fmt_elapsed(offset_s)} output time")
    total_real = sum(
        (parse_iso(seg["end_date"]) - parse_iso(seg["start_date"])).total_seconds()
        for seg in segments
    )
    print(f"Timer   : ends at   {fmt_elapsed(total_real + timer_start_s)}")
    print(f"Written : {out_path}")
    print()
    print("Burn into video:")
    print(f"  ffmpeg -i <video.MP4> -vf \"subtitles={out_path}\" output.MP4")


if __name__ == "__main__":
    main()
