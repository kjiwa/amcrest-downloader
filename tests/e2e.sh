#!/bin/sh
set -eu

cleanup() {
    if [ -n "${MOCK_PID:-}" ]; then
        kill "$MOCK_PID" 2>/dev/null || true
    fi
    if [ -n "${WORK_DIR:-}" ]; then
        rm -rf "$WORK_DIR"
    fi
}

free_port() {
    python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

wait_for_mock() {
    _wait_for_mock_port="$1"
    _wait_for_mock_tries=0
    while [ "$_wait_for_mock_tries" -lt 50 ]; do
        _wait_for_mock_tries=$((_wait_for_mock_tries + 1))
        if curl -s "http://127.0.0.1:$_wait_for_mock_port/healthz" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    echo "Error: mock camera did not start" >&2
    return 1
}

main() {
    SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
    readonly SCRIPT_DIR
    readonly REPO_ROOT="$SCRIPT_DIR/.."
    readonly OUTPUT_NAME="e2e.mp4"

    WORK_DIR=$(mktemp -d)
    MOCK_PID=""
    trap cleanup EXIT INT TERM

    _main_port=$(free_port)
    python3 "$REPO_ROOT/demo/mock_camera.py" "$_main_port" </dev/null >/dev/null 2>&1 &
    MOCK_PID="$!"
    wait_for_mock "$_main_port"

    AMCREST_PASSWORD=secret amcrest-downloader \
        --host 127.0.0.1 --port "$_main_port" -u admin \
        --start 2026-09-09T08:00:00 --end 2026-09-09T08:30:00 \
        --output-dir "$WORK_DIR" --output-file "$OUTPUT_NAME"

    if [ ! -s "$WORK_DIR/$OUTPUT_NAME" ]; then
        echo "Error: $OUTPUT_NAME was not created" >&2
        return 1
    fi
    ffprobe -v error "$WORK_DIR/$OUTPUT_NAME"
    echo "e2e ok"
}

main "$@"
