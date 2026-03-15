# GoProTimeWarp

Detect which recording speed (TimeWarp / slo-mo / normal) a GoPro HERO camera was using at each moment in a video, using the GPMF telemetry data embedded in the MP4 file.

## How It Works

GoPro embeds telemetry (GPMF format) in every MP4. Each telemetry sample has two timestamps:

- `date` — real wall-clock UTC time when the frame was captured
- `cts` — composition timestamp (position in the **output** video, in 0.1 ms units)

**Speed multiplier = Δreal_time / Δoutput_time**

| Value | Meaning |
|-------|---------|
| > 1 | TimeWarp (sped up — real time > output time) |
| = 1 | Normal recording |
| < 1 | Slo-mo (slowed down — output time > real time) |

The tool slides a window over the SHUT (shutter speed) telemetry stream, computes the ratio, and snaps to the nearest known GoPro preset.

**Known presets:** `0.125` (slo-mo 8x) · `0.25` (slo-mo 4x) · `0.5` (slo-mo 2x) · `1.0` (normal) · `2x / 5x / 10x / 15x / 30x` (TimeWarp)

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (includes ffprobe): `brew install ffmpeg`

## Quick Start

```bash
# Process a GoPro MP4 end-to-end
./process_video.sh path/to/GH015116.MP4

# Keep the intermediate .bin file (faster re-runs)
./process_video.sh path/to/GH015116.MP4

# Delete the .bin after processing (saves ~20 MB)
./process_video.sh path/to/GH015116.MP4 --clean
```

This produces two files next to the MP4:

| File | Description |
|------|-------------|
| `GH015116_1_SHUT.json` | Raw telemetry samples (cts + date + shutter value) |
| `GH015116_1_SHUT_speed_timeline.json` | Detected speed segments |

The terminal prints a table like:

```
Device : HERO9 Black
Stream : Exposure time (shutter speed)
Overall: real 29:50 / output 6:47 → speed ×4.394

#     Output start → end          Real start → end    Out dur    Real dur   Avg spd    Samples    Mode
---
1     00:00:00.517→00:00:02.385   02:00:39→02:00:47   1.9s       8.4s       ×4.683     57         timewarp 5x
2     00:00:02.419→00:00:03.052   02:00:48→02:00:49   0.6s       1.9s       ×3.141     20         timewarp auto
...
```

## Running Just the Speed Detector

If you already have a `_SHUT.json` telemetry file:

```bash
python3 detect_speed.py GH015116_1_SHUT.json
python3 detect_speed.py GH015116_1_SHUT.json --window 50 --tolerance 0.25 --min-samples 20
```

| Option | Default | Description |
|--------|---------|-------------|
| `--window` | 30 | Sliding window size in samples (~10 s of output at 3 Hz) |
| `--tolerance` | 0.30 | Max fractional deviation to snap to a preset (30%) |
| `--min-samples` | 15 | Merge segments shorter than this into neighbours |

## Output JSON Format

```json
{
  "device": "HERO9 Black",
  "stream": "Exposure time (shutter speed)",
  "segments": [
    {
      "label": "timewarp 5x",
      "preset": 5.0,
      "avg_speed": 4.683,
      "start_cts_ms": 517.0,
      "end_cts_ms": 2385.0,
      "start_time_output": "00:00:00.517",
      "end_time_output": "00:00:02.385",
      "start_date": "2025-08-30T02:00:39.004Z",
      "end_date": "2025-08-30T02:00:47.389Z",
      "sample_count": 57
    }
  ]
}
```

`start_cts_ms` / `end_cts_ms` are the actual millisecond positions in the output video.

## Pipeline Details

`process_video.sh` runs three steps:

```
MP4 ──ffmpeg──▶ .bin ──gpmf2json.py──▶ _1_SHUT.json ──detect_speed.py──▶ _speed_timeline.json
```

1. **ffmpeg** extracts the GPMF metadata track (auto-detected, typically track 3) as a raw binary
2. **gpmf2json.py** parses the binary and queries the MP4 for per-packet timestamps via ffprobe, producing the telemetry JSON (replaces the older `gopro2json` tool which doesn't support modern GoPro firmware)
3. **detect_speed.py** analyses the telemetry and produces the speed timeline

## Real-time Overlay

After running `process_video.sh`, you can generate a real elapsed time overlay from the speed timeline:

```bash
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json
```

This produces `GH015116_1_SHUT_overlay.ass` — an ASS subtitle file showing the real elapsed time at each frame, accounting for TimeWarp / slo-mo speed changes.

| Option | Default | Description |
|--------|---------|-------------|
| `--offset-video HH:MM:SS` | `00:00:00` | Start the timer only from this output timestamp (skip pre-race section) |
| `--timer-start HH:MM:SS` | `00:00:00` | Timer value at the first displayed frame (use for multi-clip races) |
| `--refresh SECONDS` | `1.0` | Subtitle refresh rate (use `0.04` for 25fps frame-accurate overlay) |
| `--transparent` | off | Print an ffmpeg command to render on a transparent background (ProRes 4444) |
| `--fps FPS` | `30` | Frame rate for transparent export |

`--offset-video` and `--timer-start` can be combined freely.

**Burn into video (high quality):**
```bash
ffmpeg -i GH015116.MP4 -vf "subtitles=GH015116_1_SHUT_overlay.ass" \
  -c:v libx264 -crf 18 -preset slow -c:a copy GH015116_overlay.MP4
```

**Export as transparent layer for video editors (DaVinci Resolve, Premiere, FCP):**
```bash
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json --transparent --fps 30
# Prints the ffmpeg command → run it to get a ProRes 4444 .mov with alpha channel
```

> **iMovie:** does not support alpha-channel compositing. Use the burn-in command above instead.

**Multi-clip race example (timer continuity between clips):**
```bash
# Clip 1 — timer starts at 0, ends at 29:26 real time
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json

# Clip 2 — timer picks up from 29:26
python3 make_overlay.py Skyrace/GH025116_1_SHUT_speed_timeline.json --timer-start 00:29:26
```

## Files

```
GoProTimeWarp/
├── process_video.sh       ← full pipeline (ffmpeg → gpmf2json → detect_speed)
├── gpmf2json.py           ← GPMF binary → JSON (replaces gopro2json)
├── detect_speed.py        ← speed segment detection from telemetry JSON
├── make_overlay.py        ← real-time elapsed time overlay generator
├── README.md
└── CLAUDE.md              ← developer/AI assistant notes
```
