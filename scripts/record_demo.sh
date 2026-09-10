#!/bin/sh
set -eu

readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly ASSETS_DIR="$REPO_ROOT/assets"
readonly FRAMES_DIR="$ASSETS_DIR/demo_frames.png"
readonly OUTPUT_GIF="$ASSETS_DIR/demo.gif"
readonly MOCK_PORT="8765"

main() {
    _main_status=0

    cd "$REPO_ROOT"
    mkdir -p "$ASSETS_DIR"
    rm -rf "$FRAMES_DIR"

    # Start mock camera server
    python3 "$REPO_ROOT/demo/mock_camera.py" "$MOCK_PORT" </dev/null >/dev/null 2>&1 &
    _mock_pid="$!"

    # Wait for mock camera server to be ready
    _ready=0
    for _i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
        if curl -s "http://127.0.0.1:$MOCK_PORT/healthz" >/dev/null 2>&1; then
            _ready=1
            break
        fi
        sleep 0.1
    done

    if [ "$_ready" -ne 1 ]; then
        echo "Error: mock camera server failed to start" >&2
        kill "$_mock_pid" 2>/dev/null || true
        return 1
    fi

    vhs demo.tape

    # Shutdown mock camera server
    curl -s "http://127.0.0.1:$MOCK_PORT/shutdown" >/dev/null 2>&1 || true
    wait "$_mock_pid" 2>/dev/null || true

    if [ -d "$FRAMES_DIR" ]; then
        ffmpeg -y \
            -framerate 50 \
            -start_number 1 \
            -i "$FRAMES_DIR/frame-text-%05d.png" \
            -framerate 50 \
            -start_number 1 \
            -i "$FRAMES_DIR/frame-cursor-%05d.png" \
            -filter_complex "[0][1]overlay[merged];[merged]fps=10,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
            "$OUTPUT_GIF" >/dev/null 2>&1
        rm -rf "$FRAMES_DIR"
    fi

    if [ -f "$OUTPUT_GIF" ]; then
        ls -lh "$OUTPUT_GIF"
    else
        echo "Error: failed to generate $OUTPUT_GIF" >&2
        _main_status=1
    fi

    return "$_main_status"
}

main "$@"


