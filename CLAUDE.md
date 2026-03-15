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
├── make_overlay.py                         ← generate ASS subtitle / transparent overlay from speed timeline
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
    └── GH025116.MP4                        ← race continuation (5:25 output / 18:14 real)
    
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
- Real recording time: ~18:12 (1092s)
- Output video duration: ~5:24 (325s)
- Overall speed ratio: ×3.36 (predominantly TimeWarp 5x)
- 43 segments detected

## Sample Data — GH015116 (Skyrace start, 2025-08-30)

- Real recording time: ~29:36 (1776s)
- Output video duration: ~6:46 (407s)
- Overall speed ratio: ×4.37 (predominantly TimeWarp 5x)
- 84 segments detected

## Known Limitations

- Only SHUT stream is used; GPS5 speed or GYRO could cross-validate detections.
- No support yet for multi-chapter videos (segments `"2"`, `"3"`, …).

## make_overlay.py

Generates an ASS subtitle file with a real elapsed time counter from a `_speed_timeline.json`.

```
python3 make_overlay.py <_speed_timeline.json> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--offset-video` | `00:00:00` | Show timer only from this output video timestamp (skip pre-race section) |
| `--timer-start` | `00:00:00` | Timer value at the first displayed frame — use for multi-clip races |
| `--output` | auto | Output ASS file path |
| `--refresh` | `1.0` | Subtitle event duration in seconds (use e.g. `0.04` for 25fps) |
| `--transparent` | flag | Print ffmpeg command to render on transparent background (ProRes 4444) |
| `--fps` | `30` | Frame rate for transparent export (match your source video) |

`--offset-video` and `--timer-start` can be combined: timer shows `--timer-start` at the `--offset-video` point and counts up from there.

**Examples:**
```bash
# Clip 1 — timer starts at 0
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json

# Clip 2 — timer picks up where clip 1 ended (29:26 real time)
python3 make_overlay.py Skyrace/GH025116_1_SHUT_speed_timeline.json --timer-start 00:29:26

# Skip first 40s of output, timer shows 4:00 at that point
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json --offset-video 00:00:40 --timer-start 4:00
```

**Burn into video (high quality):**
```bash
ffmpeg -i GH025116.MP4 -vf "subtitles=overlay.ass" -c:v libx264 -crf 18 -preset slow -c:a copy GH025116_overlay.MP4
```
- `-crf 18` — visually lossless; lower = better quality (range 0–51)
- `-c:a copy` — audio copied without re-encoding

**Export as transparent overlay (for NLE compositing — DaVinci / Premiere / FCP):**
```bash
python3 make_overlay.py Skyrace/GH015116_1_SHUT_speed_timeline.json --transparent --fps 30
# Prints the ffmpeg command → run it to produce a ProRes 4444 .mov with alpha channel
```
- iMovie does **not** support alpha compositing — use the burn-in command for iMovie

Overlay shows: `MM:SS` real elapsed time (large, white) + speed mode label (small, dimmed)

