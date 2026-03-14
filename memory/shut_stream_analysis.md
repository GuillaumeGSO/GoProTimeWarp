---
name: SHUT stream analysis for GH025116
description: Statistical analysis of the shutter speed telemetry from the Skyrace video
type: project
---

# SHUT Stream Analysis — GH025116

## File: GH025116_1_SHUT.json

| Property | Value |
|----------|-------|
| Device | GoPro HERO9 Black |
| Stream | SHUT — Exposure time (shutter speed) |
| Unit | seconds (s) |
| Total samples | 9,752 |
| Recording start | 2025-08-30 02:30:18.524 UTC |
| Recording end | 2025-08-30 02:48:32.419 UTC |
| Real duration | 1,093.9 s (~18 min 14 sec) |
| CTS range | 0 → 3,253,583 ms |
| CTS duration | 3,253.6 s (~54 min 13 sec) |
| Sampling interval | ~333 ms CTS (~3 Hz) |
| Output framerate | 29.97 fps |

## Speed Ratio

- **Real / CTS = 1094 / 3254 ≈ 0.336** → output video is ~3x longer than real recording time
- This indicates the video is slowed down (slo-mo) or contains predominantly slow TimeWarp

## Shutter Value Statistics

| Stat | Value | Equivalent |
|------|-------|-----------|
| Min | 0.001042 s | 1/960 s |
| Max | 0.033281 s | 1/30 s |
| Mean | 0.005599 s | 1/179 s |

## Most Common Shutter Values

| Shutter (s) | Equiv | Count | Implied capture fps (180°) | Implied speed |
|-------------|-------|-------|---------------------------|---------------|
| 0.0035 | 1/286 | 2443 | 142.9 fps | 4.77x slow |
| 0.0042 | 1/238 | 786 | 119 fps | 3.97x slow ≈ 4x |
| 0.0021 | 1/476 | 588 | 238 fps | ~8x slow |
| 0.0010 | 1/1000 | 543 | 500 fps | ~16x slow |
| 0.0083 | 1/120 | 297 | 60 fps | 2x slow |
| 0.0333 | 1/30 | 209 | 15 fps | 0.5x (2x TimeWarp) |

**Note:** Shutter-based speed inference assumes 180° shutter angle, which may not always hold. The date/CTS ratio method is more reliable.

## Key Observations

1. The CTS sampling interval is very consistent at ~333ms (±2ms), meaning the GPMF payload rate is stable.
2. Multiple distinct shutter clusters exist → the video likely contains multiple speed modes.
3. The 0.0333s (1/30s) shutter value is the max — this caps at the output fps, consistent with TimeWarp 2x or very slow motion.
4. Shutter alone is not sufficient to determine TimeWarp speed reliably; date/CTS ratio is the primary signal.
