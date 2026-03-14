---
name: GoPro GPMF extraction toolchain
description: How to extract GPMF binary data from MP4 and convert to JSON using ffmpeg and gopro-utils
type: project
---

# GPMF Extraction Toolchain

## Repo: stilldavid/gopro-utils

GitHub: https://github.com/stilldavid/gopro-utils
Purpose: Parse GPMF binary metadata from GoPro Hero 5+ cameras and export to JSON.
Key binary: `gopro2json`

## Step 1 — Install ffmpeg

```bash
brew install ffmpeg
```

## Step 2 — Extract GPMF binary from MP4

```bash
ffmpeg -y -i GH025116.MP4 -map 0:3 -codec copy -f rawvideo GH025116.bin
```

- `-map 0:3` selects track index 3 (the GPMF metadata track in GoPro files)
- Output `.bin` is the raw GPMF binary stream

## Step 3 — Convert binary to JSON

```bash
gopro2json -i GH025116.bin -o GH025116_STREAM.json
```

Or pipe through the individual stream converters in the gopro-utils package.

## Existing Extracted Files

- `Skyrace/GH025116.bin` — raw GPMF binary (19.3 MB), extracted 2025-09-07
- `GH025116_1_SHUT.json` — shutter speed stream (770 KB)
- `GH025116_1_SCEN.json` — scene classification stream (9.7 MB)

## Additional Streams Available in .bin

The binary likely contains: GYRO, ACCL, GPS5, GPSU, GPSF, GPSA, TEMP, TSMP, SHUT, SCEN.
To extract GPS5 (which includes speed): run gopro2json and look for the GPS5 stream.
GPS5 value format: `[latitude, longitude, altitude, speed_2d_m_s, speed_3d_m_s]`

## Notes

- The gopro-utils tool has NO built-in TimeWarp speed detection — that's what this project adds.
- CTS in JSON output = composition timestamp = position in output video (ms from start).
- `frames/second` in JSON = output video framerate (not capture rate).
