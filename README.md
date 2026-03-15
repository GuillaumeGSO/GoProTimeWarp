# GoProTimeWarp

When you film with a GoPro in **TimeWarp** or **slow-motion** mode, the output video is compressed or stretched in time — a 30-minute hike becomes a 6-minute clip. This makes it impossible to display accurate real elapsed time on the footage without knowing, frame by frame, what speed the camera was using.

**GoProTimeWarp** solves this by reading the hidden telemetry track embedded in every GoPro MP4, detecting the recording speed at each moment, and producing:

- a **speed timeline** (`_speed_timeline.json`) — which speed mode was active and when
- a **real-time overlay** — an `MM:SS` counter burned into the video (or exported as a transparent layer for video editors), showing the true elapsed time at every frame

**Typical use case:** race or sport footage filmed with TimeWarp, where you want to display the real race clock on the final edit.

## How It Works

Every GoPro MP4 contains a hidden telemetry track (GPMF format) logged several times per second. Each sample records two things simultaneously:

- the **real wall-clock time** when that moment was captured (`date`)
- its **position in the output video** in milliseconds (`cts`)

When TimeWarp is active, real time passes much faster than video time — 5 minutes of real action becomes 1 minute of video. That ratio between the two timestamps directly gives the recording speed.

For example: if 5 seconds of real time map to 1 second of video, the speed is **×5 → TimeWarp 5x**.

The tool reads these timestamps across the whole video, computes the ratio in a sliding window, and snaps each segment to the nearest known GoPro preset:

| Preset | Mode |
|--------|------|
| 0.125× | Slo-mo 8x |
| 0.25× | Slo-mo 4x |
| 0.5× | Slo-mo 2x |
| 1× | Normal |
| 2× / 5× / 10× / 15× / 30× | TimeWarp |

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (includes ffprobe): `brew install ffmpeg`

---

## Scripts

### `process_video.sh` — Full pipeline (recommended)

Runs all steps automatically from a raw GoPro MP4 and produces the speed timeline.

```bash
./process_video.sh path/to/GH015116.MP4          # standard
./process_video.sh path/to/GH015116.MP4 --clean  # delete intermediate .bin after
```

This produces two files next to the MP4:

| File | Description |
|------|-------------|
| `GH015116_1_SHUT.json` | Raw telemetry samples extracted from the video |
| `GH015116_1_SHUT_speed_timeline.json` | Detected speed segments |

The terminal prints a segment table:

```
Device : HERO9 Black
Stream : Exposure time (shutter speed)
Overall: real 29:50 / output 6:47 → speed ×4.394

#     Output start → end          Real start → end    Out dur    Real dur   Avg spd    Mode
---
1     00:00:00.517→00:00:02.385   02:00:39→02:00:47   1.9s       8.4s       ×4.683     timewarp 5x
2     00:00:02.419→00:00:03.052   02:00:48→02:00:49   0.6s       1.9s       ×3.141     timewarp auto
...
```

Internally it chains three steps:

```
MP4 ──ffmpeg──▶ .bin ──gpmf2json.py──▶ _1_SHUT.json ──detect_speed.py──▶ _speed_timeline.json
```

---

### `gpmf2json.py` — Telemetry extraction

Extracts the GPMF telemetry track from the MP4 and converts it to JSON.

```bash
python3 gpmf2json.py GH025116.MP4 GH025116_1_SHUT.json --bin GH025116.bin
```

You normally don't need to run this directly — `process_video.sh` handles it. It replaces the older `gopro2json` tool which fails on modern GoPro firmware.

---

### `detect_speed.py` — Speed detection

Analyses the telemetry JSON and outputs a speed timeline. Run this directly if you already have a `_SHUT.json` file and want to re-tune the detection parameters.

```bash
python3 detect_speed.py GH015116_1_SHUT.json
python3 detect_speed.py GH015116_1_SHUT.json --window 50 --tolerance 0.25 --min-samples 20
```

| Option | Default | Description |
|--------|---------|-------------|
| `--window` | 30 | Sliding window size in samples (~10 s of output at 3 Hz) |
| `--tolerance` | 0.30 | Max fractional deviation to snap to a preset (30%) |
| `--min-samples` | 15 | Merge segments shorter than this into neighbours |

Output JSON format (`_speed_timeline.json`):

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

---

### `make_overlay.py` — Real-time elapsed time overlay

Generates an ASS subtitle file showing the real elapsed time at every frame of the output video. Run this after `process_video.sh`.

```bash
python3 make_overlay.py GH015116_1_SHUT_speed_timeline.json
```

| Option | Default | Description |
|--------|---------|-------------|
| `--offset-video HH:MM:SS` | `00:00:00` | Start the timer only from this output timestamp (skip pre-race section) |
| `--timer-start HH:MM:SS` | `00:00:00` | Timer value at the first displayed frame — use for multi-clip races where clip 2 picks up where clip 1 left off |
| `--refresh SECONDS` | `1.0` | Subtitle refresh rate (use `0.04` for 25fps frame-accurate overlay) |
| `--transparent` | off | Print an ffmpeg command to render the overlay on a transparent background |
| `--fps FPS` | `30` | Frame rate for transparent export (match your source video) |

`--offset-video` and `--timer-start` can be combined: the timer shows `--timer-start` at the `--offset-video` point and counts up from there.

**Option 1 — Burn the overlay directly into the video:**
```bash
ffmpeg -i GH015116.MP4 \
  -vf "subtitles=GH015116_1_SHUT_overlay.ass" \
  -c:v libx264 -crf 18 -preset slow -c:a copy \
  GH015116_overlay.MP4
```
`-crf 18` gives visually lossless quality (lower = better, range 0–51). Works in any player or editor including iMovie.

**Option 2 — Export as a transparent layer (DaVinci Resolve, Premiere, FCP):**
```bash
python3 make_overlay.py GH015116_1_SHUT_speed_timeline.json --transparent --fps 30
# → prints the ffmpeg command; run it to produce a ProRes 4444 .mov with alpha channel
```
Import the `.mov` into your editor and composite it over the video track.
> iMovie does not support alpha-channel compositing — use Option 1 instead.

**Multi-clip race (timer continuity across clips):**
```bash
# Clip 1 — timer starts at 0
python3 make_overlay.py GH015116_1_SHUT_speed_timeline.json

# Clip 2 — timer picks up where clip 1 ended (29:26 real time)
python3 make_overlay.py GH025116_1_SHUT_speed_timeline.json --timer-start 00:29:26
```

**Combined `--offset-video` + `--timer-start` — skip pre-race section while keeping correct time:**

If clip 1 has 1 minute of pre-race footage you want to hide, but you still need the race timer to read correctly from the moment it appears:

```bash
# Overlay starts at 1:00 in the output video, timer shows 00:00 at that point
python3 make_overlay.py GH015116_1_SHUT_speed_timeline.json \
  --offset-video 00:01:00 \
  --timer-start 00:00:00
```

Or if clip 2 also has pre-race footage and the race was already 29:26 in at the start of that clip:

```bash
# Overlay starts at 0:30 in clip 2's output, timer shows 29:56 at that point
python3 make_overlay.py GH025116_1_SHUT_speed_timeline.json \
  --offset-video 00:00:30 \
  --timer-start 00:29:56
```

The timer value shown at `--offset-video` is exactly `--timer-start`, and counts up from there using the segment speed ratios.
