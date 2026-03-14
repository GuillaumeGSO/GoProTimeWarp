# GoProTimeWarp

## Project Goal

Detect which recording speed (TimeWarp / slo-mo / normal) a GoPro HERO camera was using at each moment in a video, using the GPMF telemetry data embedded in the MP4 file.

## How It Works

GoPro embeds telemetry (GPMF format) as a hidden track in every MP4. Each telemetry sample carries two timestamps:

- `date` — real wall-clock UTC time when the frame was captured
- `cts` — composition timestamp in **0.1 ms units** (position in the **output** video; divide by 10 for ms, by 10000 for seconds)

Speed multiplier = `Δreal_time / Δoutput_time`

| Result | Meaning |
|--------|---------|
| > 1 | TimeWarp (sped up — real time > output time) |
| = 1 | Normal recording |
| < 1 | Slo-mo (slowed down — output time > real time) |

Known GoPro presets: `0.125` (slo-mo 8x), `0.25` (slo-mo 4x), `0.5` (slo-mo 2x), `1.0` (normal), `2x / 5x / 10x / 15x / 30x` (TimeWarp).

## File Structure

```
GoProTimeWarp/
├── CLAUDE.md                               ← this file
├── README.md                               ← user-facing documentation
├── process_video.sh                        ← full pipeline (ffmpeg → gpmf2json → detect_speed)
├── gpmf2json.py                            ← GPMF binary → JSON (replaces gopro2json)
├── detect_speed.py                         ← speed segment detection
├── GH025116_1_SHUT.json                    ← extracted SHUT telemetry (input example)
├── GH025116_1_SHUT_speed_timeline.json     ← detected speed segments (output example)
├── GH025116_1_SCEN.json                    ← scene classification telemetry (unused so far)
├── script_bash.txt                         ← original manual extraction notes (superseded)
├── memory/                                 ← project research notes
│   ├── MEMORY.md
│   ├── project_overview.md
│   ├── gpmf_data_format.md
│   ├── shut_stream_analysis.md
│   ├── speed_detection_approach.md
│   └── toolchain.md
└── Skyrace/                                ← raw video files (git-ignored)
    ├── GH015116.MP4                        ← race start clip (6:47 output / 29:50 real)
    ├── GH015116_1_SHUT.json
    ├── GH015116_1_SHUT_speed_timeline.json
    ├── GH025116.MP4                        ← race continuation (5:25 output / 18:14 real)
    └── GH025116.bin                        ← kept for reference
```

## Toolchain

### All-in-one (recommended)
```bash
./process_video.sh Skyrace/GH015116.MP4          # keep .bin
./process_video.sh Skyrace/GH015116.MP4 --clean  # delete .bin after
```

### Manual steps

**Step 1 — Extract GPMF binary**
```bash
ffmpeg -y -i GH025116.MP4 -map 0:3 -codec copy -f rawvideo GH025116.bin
```
Track index 3 is the GPMF metadata track (`gpmd`). `process_video.sh` auto-detects it via ffprobe.

**Step 2 — Convert binary to JSON**
```bash
python3 gpmf2json.py GH025116.MP4 GH025116_1_SHUT.json --bin GH025116.bin
```
`gpmf2json.py` replaces the old `gopro2json` (stilldavid/gopro-utils) which fails on modern GoPro firmware due to unknown GPMF labels (e.g. `STMP`). It gets CTS values from ffprobe packet timestamps.

**Step 3 — Detect speed**
```bash
python3 detect_speed.py GH025116_1_SHUT.json
```

## detect_speed.py

```
python3 detect_speed.py <SHUT.json> [--window N] [--tolerance T] [--min-samples M]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--window` | 30 | Sliding window size in samples (~10s of output video at 3 Hz) |
| `--tolerance` | 0.30 | Max fractional deviation to snap to a preset (30%) |
| `--min-samples` | 15 | Segments shorter than this are merged into neighbours |

**Output:**
- Terminal table: segment # / output time range / avg speed / mode
- `<input>_speed_timeline.json` — machine-readable segment list

### JSON output format
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

`start_cts_ms` / `end_cts_ms` are actual milliseconds in the output video.

## Sample Data — GH025116 (Skyrace, 2025-08-30)

- Device: GoPro HERO9 Black
- Real recording time: ~18 min (1094s)
- Output video duration: ~5:25 (325s)
- Overall speed ratio: ×3.36 (predominantly TimeWarp 5x)
- 43 segments detected

## Sample Data — GH015116 (Skyrace start, 2025-08-30)

- Real recording time: ~29:50 (1790s)
- Output video duration: ~6:47 (407s)
- Overall speed ratio: ×4.39 (predominantly TimeWarp 5x)
- 84 segments detected

## Known Limitations

- Only SHUT stream is used; GPS5 speed or GYRO could cross-validate detections.
- No support yet for multi-chapter videos (segments `"2"`, `"3"`, …).

## TODO — Future Features

### CSV export in detect_speed.py
- Add `--csv` flag to `detect_speed.py` to export the speed timeline as a CSV file
- Two possible outputs:
  - **Segment-level** (one row per segment): `output_start_ms, output_end_ms, real_start, real_end, avg_speed, label`
  - **Sample-level** (one row per telemetry sample): `cts_ms, date, value, speed_estimate` — useful for plotting

### Real-time overlay with ffmpeg
- Use `_speed_timeline.json` to burn a **real elapsed time counter** onto the video via an ASS subtitle file
- The overlay shows real elapsed race time at each output frame, derived from segment speed ratios
- New script: `make_overlay.py <_speed_timeline.json> [options]`

**Options:**
| Option | Example | Description |
|--------|---------|-------------|
| `--offset-video` | `--offset-video 00:01:30` | Start the timer only from this output video timestamp (e.g. skip a pre-race section) |
| `--timer-start` | `--timer-start 00:29:50` | Initial value of the timer at the first displayed frame — essential for multi-clip races where clip 2 picks up where clip 1 left off |
| `--output` | `--output overlay.ass` | Output ASS file path |

**Example for a two-clip race:**
```bash
# Clip 1 — timer starts at 0
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json --timer-start 0

# Clip 2 — timer starts where clip 1 ended (29:50 real time)
python3 make_overlay.py GH025116_1_SHUT_speed_timeline.json --timer-start 00:29:50
```

**Burn into video:**
```bash
ffmpeg -i GH025116.MP4 -vf "subtitles=overlay.ass" GH025116_overlay.MP4
```

- Overlay lines: `MM:SS` real elapsed time (large) + `TimeWarp 5x` speed mode (small, dimmed)
- ASS format chosen for precise per-frame timing and styling flexibility
