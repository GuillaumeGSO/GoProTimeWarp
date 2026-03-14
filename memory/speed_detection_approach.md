---
name: TimeWarp speed detection approach
description: How to detect GoPro TimeWarp/slo-mo speed from GPMF telemetry using date vs CTS ratio
type: project
---

# TimeWarp Speed Detection Approach

## Core Principle

Each GPMF sample has two time references:
- `date` → real wall-clock UTC time when the frame was captured
- `cts` → composition timestamp in ms (position in the output video)

**Speed multiplier = Δreal_time / Δoutput_time**

```
speed = (date[i+W] - date[i]).total_seconds()
        ----------------------------------------
              (cts[i+W] - cts[i]) / 1000
```

| Mode | Speed | Real/Output ratio |
|------|-------|-------------------|
| TimeWarp 30x | 30x faster | ratio = 30 |
| TimeWarp 15x | 15x faster | ratio = 15 |
| TimeWarp 10x | 10x faster | ratio = 10 |
| TimeWarp 5x | 5x faster | ratio = 5 |
| TimeWarp 2x | 2x faster | ratio = 2 |
| Normal | 1x | ratio = 1 |
| Slo-mo 2x | 2x slower | ratio = 0.5 |
| Slo-mo 4x | 4x slower | ratio = 0.25 |
| Slo-mo 8x | 8x slower | ratio = 0.125 |

## Why This Method Is Better Than Shutter-Based Detection

- Shutter speed reflects auto-exposure decisions, not capture rate directly
- Shutter angle varies (not always 180°), so shutter → fps conversion is unreliable
- Date/CTS ratio is a direct geometric measurement: it tells exactly how much real time maps to output video time
- Requires only the SHUT (or any other) GPMF stream — no need for GPS or additional data

## Sliding Window Smoothing

The `date` field has limited precision (milliseconds), causing jitter on small windows. Solution: use a window of W samples:
- W = 30 samples ≈ 10 seconds of output video (at 3 Hz SHUT sampling)
- Larger W = smoother but slower to detect transitions
- Recommended range: W = 20–50

## Known GoPro Speed Presets

Snap raw ratio to nearest preset with tolerance ±20%:

```python
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
```

If raw speed doesn't match any preset within tolerance → label as `"timewarp auto"` (variable speed).

## Segmentation

Group consecutive samples with the same snapped label into segments:

```json
[
  {
    "segment": 1,
    "start_cts_ms": 0,
    "end_cts_ms": 45000,
    "start_time_output": "00:00:00",
    "end_time_output": "00:00:45",
    "start_date": "2025-08-30T02:30:18Z",
    "end_date": "2025-08-30T02:30:33Z",
    "speed": 0.336,
    "label": "timewarp auto",
    "sample_count": 135
  }
]
```

## Limitations

1. Date precision: GoPro timestamps have ~55ms resolution; very short segments (<2s) may be inaccurate
2. Transition zones: The sliding window blurs speed changes; actual transition may be ±W/2 samples
3. TimeWarp Auto: Speed changes continuously — segments will appear as short bursts at different snapped values
4. Some date values are repeated (GoPro batches them) — skip windows where Δreal < 0.1s

## Planned Tool: detect_speed.py

```
python3 detect_speed.py GH025116_1_SHUT.json
python3 detect_speed.py GH025116_1_SHUT.json --window 50
```

Output:
- `GH025116_1_SHUT_speed_timeline.json` — machine-readable segment list
- Terminal summary table — human-readable

**Why:** How to apply: use this method whenever building or extending the speed detection tool.
