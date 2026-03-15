#!/usr/bin/env bash
# process_video.sh — Full GoPro GPMF extraction + speed detection pipeline
#
# Usage:
#   ./process_video.sh <video.mp4> [--clean]
#
# Options:
#   --clean   Delete the intermediate .bin file after JSON extraction
#
# Output (written next to the input MP4):
#   <basename>.bin                        intermediate GPMF binary
#   <basename>_1_SHUT.json                telemetry JSON
#   <basename>_1_SHUT_speed_timeline.json speed segment timeline

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
INPUT=""
CLEAN=false

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=true ;;
        *)       INPUT="$arg" ;;
    esac
done

if [[ -z "$INPUT" ]]; then
    echo "Usage: $0 <video.mp4> [--clean]" >&2
    exit 1
fi

if [[ ! -f "$INPUT" ]]; then
    echo "Error: file not found: $INPUT" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Check dependencies
# ---------------------------------------------------------------------------
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        echo "Error: '$1' not found. $2" >&2
        exit 1
    fi
}

check_dep ffmpeg  "Install with: brew install ffmpeg"
check_dep ffprobe "Install with: brew install ffmpeg"
check_dep python3 "Install Python 3 from https://python.org"

# ---------------------------------------------------------------------------
# Derive output paths
# ---------------------------------------------------------------------------
INPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
BASENAME="$(basename "$INPUT" .MP4)"
BASENAME="${BASENAME%.mp4}"  # handle lowercase extension too

BIN_OUT="$INPUT_DIR/${BASENAME}.bin"
JSON_OUT="$INPUT_DIR/${BASENAME}_1_SHUT.json"
TIMELINE_OUT="$INPUT_DIR/${BASENAME}_1_SHUT_speed_timeline.json"

echo "=== GoProTimeWarp pipeline ==="
echo "  Input   : $INPUT"
echo "  Bin     : $BIN_OUT"
echo "  JSON    : $JSON_OUT"
echo "  Timeline: $TIMELINE_OUT"
echo ""

# ---------------------------------------------------------------------------
# Step 1 — Probe GPMF track index
# ---------------------------------------------------------------------------
echo "[1/4] Probing GPMF track in $BASENAME …"
TRACK_IDX=$(ffprobe -v quiet -print_format json -show_streams "$INPUT" 2>/dev/null \
    | python3 -c "
import json, sys
streams = json.load(sys.stdin)['streams']
for s in streams:
    tag = s.get('codec_tag_string', '')
    handler = s.get('tags', {}).get('handler_name', '')
    if tag == 'gpmd' or 'MET' in handler or 'GoPro MET' in handler:
        print(s['index'])
        break
else:
    print(3)  # default fallback
")
echo "  GPMF track index: $TRACK_IDX"

# ---------------------------------------------------------------------------
# Step 2 — Extract GPMF binary
# ---------------------------------------------------------------------------
echo "[2/4] Extracting GPMF binary …"
ffmpeg -y -i "$INPUT" -map "0:$TRACK_IDX" -codec copy -f rawvideo "$BIN_OUT" \
    -loglevel error -stats
echo "  Written: $BIN_OUT"

# ---------------------------------------------------------------------------
# Step 3 — Convert binary to JSON
# ---------------------------------------------------------------------------
echo "[3/4] Converting GPMF binary to JSON …"
python3 "$SCRIPT_DIR/gpmf2json.py" "$INPUT" "$JSON_OUT" --bin "$BIN_OUT" --track "$TRACK_IDX"

# ---------------------------------------------------------------------------
# Optional cleanup
# ---------------------------------------------------------------------------
if [[ "$CLEAN" == true ]]; then
    rm "$BIN_OUT"
    echo "  Deleted: $BIN_OUT"
fi

# ---------------------------------------------------------------------------
# Step 4 — Detect speed segments
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Detecting speed segments …"
python3 "$SCRIPT_DIR/detect_speed.py" "$JSON_OUT"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Done ==="
[[ "$CLEAN" == false ]] && echo "  $BIN_OUT"
echo "  $JSON_OUT"
echo "  $TIMELINE_OUT"
