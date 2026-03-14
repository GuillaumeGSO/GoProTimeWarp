#!/usr/bin/env python3
"""
gpmf2json.py — Extract GPMF telemetry from a GoPro file and output JSON.

Replaces gopro2json for modern GoPro firmware (handles unknown labels like STMP).
Reads the .bin extracted by ffmpeg alongside the original .MP4 for timestamps.

Usage:
    python3 gpmf2json.py <video.MP4> <output.json> [--bin path.bin] [--track N] [--stream KEY]

    --bin      Path to GPMF binary (default: <video>.bin next to the MP4)
    --track    GPMF track index in MP4 (default: auto-detected)
    --stream   GPMF stream key to extract (default: SHUT)

Output format is compatible with detect_speed.py.
"""

import argparse
import json
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# GPMF binary parser
# ---------------------------------------------------------------------------

def _next_klv(data: bytes, offset: int):
    """Return (key, type_char, elem_size, repeat, payload, next_offset) or None."""
    if offset + 8 > len(data):
        return None
    key = data[offset:offset+4]
    type_char = data[offset+4:offset+5]
    elem_size = data[offset+5]
    repeat = struct.unpack_from('>H', data, offset+6)[0]
    data_len = elem_size * repeat
    padded = (data_len + 3) & ~3
    payload = data[offset+8: offset+8+data_len]
    return key, type_char, elem_size, repeat, payload, offset + 8 + padded


def parse_payload(type_char: bytes, elem_size: int, repeat: int, payload: bytes):
    """Decode GPMF payload. Returns Python value(s) or None for unknown types."""
    tc = type_char.decode('latin-1')
    if tc == 'c':
        return payload.decode('utf-8', errors='replace').rstrip('\x00')
    if tc == 'U':
        return payload.decode('ascii', errors='replace')
    if tc == 'f':
        return list(struct.unpack_from(f'>{repeat}f', payload))
    if tc in ('s', 'S', 'l', 'L', 'J', 'j'):
        fmt = {'s': 'h', 'S': 'H', 'l': 'i', 'L': 'I', 'J': 'Q', 'j': 'q'}[tc]
        return list(struct.unpack_from(f'>{repeat}{fmt}', payload))
    return None  # skip unknown types


def parse_gpsu(s: str) -> str | None:
    """Parse GoPro GPS UTC 'YYMMDDHHMMSS.SSS' → ISO 8601 UTC string."""
    s = s.rstrip('\x00').strip()
    if len(s) < 14:
        return None
    try:
        yy, mo, dd = int(s[0:2]), int(s[2:4]), int(s[4:6])
        hh, mm = int(s[6:8]), int(s[8:10])
        sec = float(s[10:]) if len(s) > 10 else 0.0
        sec_i = int(sec)
        us = int(round((sec - sec_i) * 1_000_000))
        dt = datetime(2000 + yy, mo, dd, hh, mm, sec_i, us, tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.') + f'{us // 1000:03d}Z'
    except (ValueError, IndexError):
        return None


# GPMF metadata keys that contain no sensor data
_META_KEYS = {b'TSMP', b'SIUN', b'UNIT', b'MTRX', b'ORIN', b'ORIO',
              b'MRKR', b'STMP', b'STNM', b'SCAL', b'GPSU', b'DVNM',
              b'EMPT', b'TICK', b'TOCK'}


def scan_strm(data: bytes, target_key: bytes):
    """
    Scan a STRM block.
    Returns dict: name, scal, samples (list of floats), gpsu.
    Silently ignores unknown labels.
    """
    name = None
    scal = 1.0
    samples = []
    gpsu = None
    offset = 0

    while True:
        entry = _next_klv(data, offset)
        if entry is None:
            break
        key, type_char, elem_size, repeat, payload, next_off = entry

        if key == b'STNM':
            name = payload.decode('utf-8', errors='replace').rstrip('\x00')

        elif key == b'SCAL':
            vals = parse_payload(type_char, elem_size, repeat, payload)
            if isinstance(vals, list) and vals:
                scal = float(vals[0])

        elif key == b'GPSU':
            raw = payload.decode('ascii', errors='replace')
            parsed = parse_gpsu(raw)
            if parsed:
                gpsu = parsed

        elif key == target_key and key not in _META_KEYS:
            vals = parse_payload(type_char, elem_size, repeat, payload)
            if isinstance(vals, list):
                samples.extend(vals)

        # All other keys (known or unknown) are silently skipped

        offset = next_off

    return {'name': name, 'scal': scal, 'samples': samples, 'gpsu': gpsu}


def process_devc_block(block_data: bytes, target_key: bytes):
    """
    Parse one DEVC block (one MP4 packet worth of telemetry).
    Returns (device_name, stream_name, scaled_samples, gpsu).
    """
    device_name = None
    stream_name = None
    raw_samples = []
    scal = 1.0
    gpsu = None
    offset = 0

    while True:
        entry = _next_klv(block_data, offset)
        if entry is None:
            break
        key, type_char, elem_size, repeat, payload, next_off = entry

        if key == b'DVNM':
            device_name = payload.decode('utf-8', errors='replace').rstrip('\x00')

        elif key == b'STRM':
            info = scan_strm(payload, target_key)
            if info['gpsu']:
                gpsu = info['gpsu']
            if info['samples']:
                stream_name = info['name']
                raw_samples = info['samples']
                scal = info['scal']

        offset = next_off

    scaled = [v / scal if scal != 0 else v for v in raw_samples]
    return device_name, stream_name, scaled, gpsu


def split_devc_blocks(data: bytes) -> list[bytes]:
    """Split concatenated GPMF binary into individual DEVC block payloads."""
    blocks = []
    i = 0
    while i + 8 <= len(data):
        key = data[i:i+4]
        if key != b'DEVC':
            i += 1
            continue
        elem_size = data[i+5]
        repeat = struct.unpack_from('>H', data, i+6)[0]
        data_len = elem_size * repeat
        padded = (data_len + 3) & ~3
        blocks.append(data[i+8: i+8+data_len])
        i = i + 8 + padded
    return blocks


# ---------------------------------------------------------------------------
# MP4 probing (timestamps + fps)
# ---------------------------------------------------------------------------

def detect_gpmf_track(mp4_path: Path) -> int:
    """Return index of the GPMF data track (codec_tag 'gpmd')."""
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_streams',
         '-print_format', 'json', str(mp4_path)],
        capture_output=True, text=True, check=True,
    )
    for s in json.loads(r.stdout)['streams']:
        if s.get('codec_tag_string') == 'gpmd':
            return s['index']
    return 3  # fallback


def get_video_fps(mp4_path: Path) -> float:
    """Return video track frame rate."""
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-select_streams', 'v:0',
         '-show_streams', '-print_format', 'json', str(mp4_path)],
        capture_output=True, text=True, check=True,
    )
    streams = json.loads(r.stdout).get('streams', [])
    if streams:
        r_fps = streams[0].get('r_frame_rate', '30/1')
        n, d = r_fps.split('/')
        return float(n) / float(d)
    return 30.0


def get_packet_times(mp4_path: Path, track_idx: int) -> list[tuple[float, float]]:
    """Return (pts_seconds, duration_seconds) per GPMF packet."""
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-select_streams', str(track_idx),
         '-show_packets', '-print_format', 'json', str(mp4_path)],
        capture_output=True, text=True, check=True,
    )
    result = []
    for p in json.loads(r.stdout)['packets']:
        pts = float(p.get('pts_time') or p.get('dts_time') or 0)
        dur = float(p.get('duration_time') or 0)
        result.append((pts, dur))
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Extract GoPro GPMF telemetry to JSON.")
    ap.add_argument('mp4', help="GoPro MP4 file")
    ap.add_argument('output', help="Output JSON file")
    ap.add_argument('--bin', help="GPMF binary file (default: <mp4>.bin)")
    ap.add_argument('--track', type=int, default=None, help="GPMF track index (auto-detected)")
    ap.add_argument('--stream', default='SHUT', help="GPMF stream key to extract (default: SHUT)")
    args = ap.parse_args()

    mp4_path = Path(args.mp4)
    bin_path = Path(args.bin) if args.bin else mp4_path.with_suffix('.bin')
    out_path = Path(args.output)

    if not mp4_path.exists():
        print(f"Error: MP4 not found: {mp4_path}", file=sys.stderr); sys.exit(1)
    if not bin_path.exists():
        print(f"Error: binary not found: {bin_path}", file=sys.stderr); sys.exit(1)

    target_key = args.stream.encode('ascii')

    print(f"  MP4    : {mp4_path}")
    print(f"  Bin    : {bin_path}")

    # Probe MP4
    track_idx = args.track if args.track is not None else detect_gpmf_track(mp4_path)
    fps = get_video_fps(mp4_path)
    packet_times = get_packet_times(mp4_path, track_idx)
    print(f"  Track  : {track_idx}  |  fps: {fps:.3f}  |  packets: {len(packet_times)}")

    # Parse binary
    data = bin_path.read_bytes()
    blocks = split_devc_blocks(data)
    print(f"  DEVC blocks: {len(blocks)}")

    if len(blocks) != len(packet_times):
        print(f"  Warning: block/packet count mismatch ({len(blocks)} vs {len(packet_times)})",
              file=sys.stderr)

    # Build samples
    device_name = None
    stream_full_name = None
    all_samples = []
    current_date = None

    for i, block_data in enumerate(blocks):
        pts, dur = packet_times[i] if i < len(packet_times) else (0.0, 0.0)

        dev_name, strm_name, samples, gpsu = process_devc_block(block_data, target_key)

        if dev_name:
            device_name = dev_name
        if strm_name:
            stream_full_name = strm_name
        if gpsu:
            current_date = gpsu

        n = len(samples)
        if n == 0:
            continue

        for j, val in enumerate(samples):
            # CTS: position within the video output (0.1ms units)
            if dur > 0:
                sample_pts = pts + (j + 0.5) / n * dur
            else:
                sample_pts = pts
            cts = round(sample_pts * 10000)

            all_samples.append({
                'value': val,
                'cts': cts,
                'date': current_date or '1970-01-01T00:00:00.000Z',
            })

    print(f"  Samples: {len(all_samples)}")

    # Output JSON (same format as gopro2json)
    output = {
        'frames/second': fps,
        '1': {
            'device name': device_name or 'unknown',
            'streams': {
                args.stream: {
                    'name': stream_full_name or args.stream,
                    'samples': all_samples,
                }
            }
        }
    }

    out_path.write_text(json.dumps(output, indent=4))
    print(f"  Written: {out_path}")


if __name__ == '__main__':
    main()
