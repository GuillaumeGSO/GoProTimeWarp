---
name: GPMF telemetry data format
description: Structure of GPMF JSON output from gopro-utils, available streams and their meaning
type: project
---

# GPMF Telemetry Data Format

## What is GPMF?

GPMF (GoPro Metadata Format) is GoPro's binary telemetry format embedded in MP4 files as a dedicated track (track 3 typically). It contains sensor data recorded in sync with video capture.

## JSON Output Format (gopro-utils / gopro2json)

```json
{
  "1": {
    "device name": "HERO9 Black",
    "streams": {
      "STREAM_NAME": {
        "name": "Human-readable description",
        "units": "unit_string",
        "samples": [
          {
            "value": <number or array>,
            "cts": <milliseconds from start>,
            "date": "<ISO 8601 UTC timestamp>"
          }
        ]
      }
    }
  },
  "frames/second": 29.970029970029973
}
```

Top-level keys are segment indices (`"1"`, `"2"`, ...) plus `"frames/second"` for the output video framerate.

## Key Fields Per Sample

| Field | Description |
|-------|-------------|
| `value` | The sensor reading (float, or array of floats for multi-axis) |
| `cts` | **Composition timestamp** in milliseconds — position in the **output video** |
| `date` | **Wall-clock UTC time** of actual capture — real-world time when the frame was recorded |

**Critical distinction:** `cts` is output video time, `date` is real capture time. Their ratio reveals the speed multiplier.

## Available GPMF Streams (HERO9 Black)

| Stream | Name | Rate | Value |
|--------|------|------|-------|
| GYRO | Gyroscope | ~400 Hz | 3-axis angular velocity |
| ACCL | Accelerometer | ~200 Hz | 3-axis acceleration |
| GPS5 | GPS Position | ~18 Hz | lat, lon, alt, speed2D, speed3D |
| GPSU | GPS UTC time | 1 Hz | UTC timestamp |
| GPSA | GPS accuracy | 1 Hz | positional accuracy in cm |
| GPSF | GPS fix | 1 Hz | 2D/3D fix status |
| TEMP | Temperature | 1 Hz | camera temperature °C |
| **SHUT** | **Shutter speed** | ~3 Hz | exposure time in seconds |
| **SCEN** | **Scene classification** | ~6 Hz | 6 probabilities: snow, urban, indoor, water, vegetation, beach |
| TSMP | Total sample counter | varies | sample count per stream |

## SCEN Stream Details

- Value is an array of 6 floats (probabilities 0.0–1.0)
- Order: `[snow, urban, indoor, water, vegetation, beach]`
- Units: `["prob"]`
- Sampled at ~6 Hz in output video time (one sample every ~5 output frames at 30fps)

## SHUT Stream Details

- Value is a single float: shutter duration in seconds
- Sampled at ~3 Hz in output video time (one sample every ~333ms CTS = ~10 output frames at 30fps)
- Reflects the actual exposure time chosen by auto-exposure for each captured frame
