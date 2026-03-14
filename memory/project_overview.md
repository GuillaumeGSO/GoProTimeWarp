---
name: GoProTimeWarp project overview
description: Project goals, file structure, video files, and git status
type: project
---

# GoProTimeWarp Project Overview

**Goal:** Build a tool to detect the GoPro TimeWarp speed multiplier (and slo-mo mode) used at any point in a GoPro video, using GPMF telemetry data.

**Why:** GoPro TimeWarp Auto dynamically changes speed. Detecting which speed was active at each moment is needed for correct video processing (speed ramping, motion blur compensation, etc.).

## Directory Structure

```
/Volumes/ORICO/Users/macmini/Documents/Guillaume/Dev/GoProTimeWarp/
├── .gitignore                  # Excludes *.MP4, *.mp4, *.MOV, *.bin, .DS_Store
├── GH025116_1_SHUT.json        # Extracted SHUT (shutter speed) telemetry — 770KB, 9752 samples
├── GH025116_1_SCEN.json        # Extracted SCEN (scene classification) telemetry — 9.7MB, 19504 samples
├── script_bash.txt             # Extraction commands (ffmpeg + gopro2json)
└── Skyrace/
    ├── GH015111.MP4            # 867 MB, Aug 30 2025
    ├── GH015116.MP4            # 4 GB, Aug 30 2025
    ├── GH025116.MP4            # 2.7 GB, Aug 30 2025  ← source of the JSON files
    └── GH025116.bin            # 19.3 MB, extracted GPMF binary metadata
```

## Video File: GH025116.MP4

- **Device:** GoPro HERO9 Black
- **Recording date:** 2025-08-30, starting 02:30:18 UTC (Skyrace event)
- **Real recording duration:** ~18 min 14 sec (1094 seconds)
- **Output video duration (CTS):** ~54 min 13 sec (3253 seconds)
- **Speed ratio (real/output):** ~0.336x → the video plays ~3x longer than real time (slo-mo or TimeWarp Auto)
- **Output framerate:** 29.97 fps

## Filename Convention

`GH025116_1_SHUT.json`:
- `GH` = HERO camera prefix
- `025116` = clip number
- `_1` = segment/chapter 1
- `SHUT` = the extracted GPMF stream name

## Git Status

Repository initialized, no commits yet. Untracked files: `.gitignore`, both JSON files, `script_bash.txt`.
