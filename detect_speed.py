#!/usr/bin/env python3
"""
detect_speed.py — Detect GoPro TimeWarp / slo-mo speed from GPMF telemetry.

Usage:
    python3 detect_speed.py <SHUT.json> [--window N] [--tolerance T]

Method:
    Speed multiplier = Δreal_time / Δoutput_time
    where real_time comes from the `date` field (wall-clock UTC)
    and output_time from the `cts` field (composition timestamp in ms).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# GoPro speed presets
# ---------------------------------------------------------------------------

PRESETS = [0.125, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0]

LABELS = {
    0.125: "slo-mo 8x",
    0.25:  "slo-mo 4x",
    0.5:   "slo-mo 2x",
    1.0:   "normal",
    2.0:   "timewarp 2x",
    5.0:   "timewarp 5x",
    10.0:  "timewarp 10x",
    15.0:  "timewarp 15x",
    30.0:  "timewarp 30x",
}


def snap_to_preset(raw_speed, tolerance=0.30):
    """Return the nearest GoPro preset within tolerance, or None if no match."""
    best = min(PRESETS, key=lambda p: abs(raw_speed - p) / p)
    if abs(raw_speed - best) / best <= tolerance:
        return best
    return None


CTS_TO_SEC = 10000.0  # cts units are 0.1 ms (100 µs); divide by 10000 to get seconds


def cts_to_sec(cts):
    """Convert raw cts units to seconds."""
    return cts / CTS_TO_SEC


def cts_to_ms(cts):
    """Convert raw cts units to milliseconds."""
    return cts / 10.0


def ms_to_hms(ms):
    """Convert milliseconds to HH:MM:SS.mmm string."""
    total_s = ms / 1000
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def parse_date(date_str):
    """Parse ISO 8601 UTC date string to datetime."""
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def load_samples(path):
    with open(path) as f:
        data = json.load(f)

    fps = data.get("frames/second")

    # Find the first numeric segment key
    segment_key = next(k for k in data if k not in ("frames/second",))
    streams = data[segment_key]["streams"]
    device = data[segment_key].get("device name", "unknown")

    # Use the first available stream (usually SHUT, but works with any)
    stream_name = next(iter(streams))
    stream = streams[stream_name]
    samples = stream["samples"]

    return samples, fps, device, stream_name, stream.get("name", "")


def compute_speeds(samples, window):
    """
    Sliding window speed estimation.
    Returns list of (center_index, raw_speed) pairs.
    Skips windows where real Δtime is too small to be reliable.
    """
    half = window // 2
    results = []

    for i in range(half, len(samples) - half):
        lo = samples[i - half]
        hi = samples[i + half]

        delta_cts = cts_to_sec(hi["cts"] - lo["cts"])  # seconds
        if delta_cts <= 0:
            continue

        delta_real = (parse_date(hi["date"]) - parse_date(lo["date"])).total_seconds()
        if delta_real < 0.05:  # skip windows with insufficient date precision
            continue

        raw_speed = delta_real / delta_cts
        results.append((i, raw_speed))

    return results


def build_segments(samples, speed_estimates, tolerance, min_samples=15):
    """
    Group consecutive speed estimates into segments with the same label,
    then merge short segments (< min_samples) into their dominant neighbor.
    Returns list of segment dicts.
    """
    if not speed_estimates:
        return []

    # --- Pass 1: raw segmentation ---
    raw_segs = []  # list of (label, preset, [(idx, raw_speed), ...])
    current_label = None
    current_preset = None
    current_items = []

    for idx, raw_speed in speed_estimates:
        preset = snap_to_preset(raw_speed, tolerance)
        label = LABELS.get(preset, "timewarp auto") if preset else "timewarp auto"

        if label != current_label:
            if current_label is not None:
                raw_segs.append((current_label, current_preset, current_items))
            current_label = label
            current_preset = preset
            current_items = [(idx, raw_speed)]
        else:
            current_items.append((idx, raw_speed))

    if current_label is not None:
        raw_segs.append((current_label, current_preset, current_items))

    # --- Pass 2: merge short segments into longer neighbours ---
    def dominant_neighbor_label(segs, pos):
        """Return the label of the longer adjacent segment."""
        left = len(segs[pos - 1][2]) if pos > 0 else 0
        right = len(segs[pos + 1][2]) if pos < len(segs) - 1 else 0
        if left == 0 and right == 0:
            return segs[pos][0], segs[pos][1]
        if left >= right:
            return segs[pos - 1][0], segs[pos - 1][1]
        return segs[pos + 1][0], segs[pos + 1][1]

    changed = True
    while changed:
        changed = False
        merged = []
        i = 0
        while i < len(raw_segs):
            label, preset, items = raw_segs[i]
            if len(items) < min_samples and len(raw_segs) > 1:
                new_label, new_preset = dominant_neighbor_label(raw_segs, i)
                raw_segs[i] = (new_label, new_preset, items)
                changed = True
            merged.append(raw_segs[i])
            i += 1
        # Collapse consecutive same-label segments
        collapsed = []
        for seg in merged:
            if collapsed and collapsed[-1][0] == seg[0]:
                collapsed[-1][2].extend(seg[2])
            else:
                collapsed.append([seg[0], seg[1], list(seg[2])])
        raw_segs = collapsed

    # --- Pass 3: build final segment dicts ---
    segments = []
    for label, preset, items in raw_segs:
        idxs = [it[0] for it in items]
        speeds = [it[1] for it in items]
        segments.append(_make_segment(samples, idxs[0], idxs[-1], label, preset, speeds))

    return segments


def _make_segment(samples, start_idx, end_idx, label, preset, raw_speeds):
    s_start = samples[start_idx]
    s_end = samples[end_idx]
    avg_speed = sum(raw_speeds) / len(raw_speeds)

    return {
        "label": label,
        "preset": preset,
        "avg_speed": round(avg_speed, 3),
        "start_cts_ms": round(cts_to_ms(s_start["cts"]), 1),
        "end_cts_ms": round(cts_to_ms(s_end["cts"]), 1),
        "start_time_output": ms_to_hms(cts_to_ms(s_start["cts"])),
        "end_time_output": ms_to_hms(cts_to_ms(s_end["cts"])),
        "start_date": s_start["date"],
        "end_date": s_end["date"],
        "sample_count": end_idx - start_idx + 1,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def seg_real_duration(seg):
    """Return real-world duration of a segment in seconds."""
    return (parse_date(seg["end_date"]) - parse_date(seg["start_date"])).total_seconds()


def seg_output_duration(seg):
    """Return output-video duration of a segment in seconds."""
    return (seg["end_cts_ms"] - seg["start_cts_ms"]) / 1000.0  # start/end_cts_ms are now actual ms


def print_summary(segments, device, stream_name, total_real_s, total_cts_s):
    overall = total_real_s / total_cts_s if total_cts_s else 0

    print(f"\nDevice : {device}")
    print(f"Stream : {stream_name}")
    print(f"Overall: real {total_real_s:.1f}s ({ms_to_hms(total_real_s*1000)}) / "
          f"output {total_cts_s:.1f}s ({ms_to_hms(total_cts_s*1000)}) → "
          f"speed ×{overall:.3f}\n")

    col = "{:<4}  {:<26}  {:<18}  {:<9}  {:<9}  {:<9}  {:<9}  {}"
    print(col.format("#", "Output start → end", "Real start → end", "Out dur", "Real dur", "Avg spd", "Samples", "Mode"))
    print("-" * 108)

    for i, seg in enumerate(segments, 1):
        out_dur = seg_output_duration(seg)
        real_dur = seg_real_duration(seg)
        # Format real start time as HH:MM:SS (UTC) — strip date prefix
        real_start = parse_date(seg["start_date"]).strftime("%H:%M:%S")
        real_end   = parse_date(seg["end_date"]).strftime("%H:%M:%S")
        print(col.format(
            i,
            f"{seg['start_time_output']}→{seg['end_time_output']}",
            f"{real_start}→{real_end}",
            f"{out_dur:.1f}s",
            f"{real_dur:.1f}s",
            f"×{seg['avg_speed']:.3f}",
            seg["sample_count"],
            seg["label"],
        ))

    print(f"\n{len(segments)} segment(s) detected.")


def write_json(segments, output_path, device, stream_name):
    out = {
        "device": device,
        "stream": stream_name,
        "segments": segments,
    }
    with open(output_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nJSON written → {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Detect GoPro TimeWarp speed from GPMF JSON.")
    parser.add_argument("input", help="Path to SHUT JSON file (e.g. GH025116_1_SHUT.json)")
    parser.add_argument("--window", type=int, default=30,
                        help="Sliding window size in samples (default: 30 ≈ 10s)")
    parser.add_argument("--tolerance", type=float, default=0.30,
                        help="Fractional tolerance for snapping to preset (default: 0.30 = 30%%)")
    parser.add_argument("--min-samples", type=int, default=15,
                        help="Minimum samples per segment; shorter ones are merged (default: 15)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {input_path.name} …")
    samples, fps, device, stream_name, stream_full_name = load_samples(input_path)
    print(f"  {len(samples)} samples  |  output fps: {fps:.3f}")

    print(f"Computing speeds (window={args.window}) …")
    speed_estimates = compute_speeds(samples, args.window)
    print(f"  {len(speed_estimates)} valid windows")

    segments = build_segments(samples, speed_estimates, args.tolerance, args.min_samples)

    # Overall stats
    total_real_s = (parse_date(samples[-1]["date"]) - parse_date(samples[0]["date"])).total_seconds()
    total_cts_s = cts_to_sec(samples[-1]["cts"] - samples[0]["cts"])

    print_summary(segments, device, stream_full_name, total_real_s, total_cts_s)

    output_path = input_path.with_name(input_path.stem + "_speed_timeline.json")
    write_json(segments, output_path, device, stream_full_name)


if __name__ == "__main__":
    main()
