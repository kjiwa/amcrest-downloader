# Amcrest Camera Recording Downloader

A Python utility to download and merge video recordings from Amcrest IP cameras using the HTTP API.

## Features

- Search for recordings by date/time range
- Concurrent downloads (default: 4 simultaneous)
- Automatic video merging using ffmpeg with stream copy and AAC fallback for PCM audio
- Support for multiple output formats (mp4, mkv, avi, mov, ts)
- Timezone-aware datetime input
- Automatic retry on failed downloads
- Environment variable configuration support
- Dry-run / listing mode (`--list-only`)

## Requirements

- Python 3.10+
- FFmpeg (must be installed and in PATH)
- Dependencies: `requests`

## Usage

```bash
python main.py --host CAMERA_HOST --username USERNAME --start START_TIME --end END_TIME
```

### Environment Variables

The CLI can read configuration from environment variables if command-line arguments are omitted:

- `AMCREST_HOST`: Camera IP address or hostname
- `AMCREST_PORT`: Camera HTTP/HTTPS port
- `AMCREST_USERNAME`: Camera username
- `AMCREST_PASSWORD`: Camera password
- `AMCREST_CHANNEL`: Camera channel index (default: 0)

### Required Arguments

- `--host`: Camera IP address or hostname (e.g., `192.168.1.100` or `[::1]`) (or env `AMCREST_HOST`)
- `--username`: Camera username (or env `AMCREST_USERNAME`)
- `--start`: Start time in ISO 8601 format (e.g., `2026-01-16T20:00:00` or `2026-01-16T20:00:00-08:00`)
- `--end`: End time in ISO 8601 format (e.g., `2026-01-16T22:00:00` or `2026-01-16T22:00:00-08:00`)

### Optional Arguments

- `--password`: Camera password (or env `AMCREST_PASSWORD`; prompts securely if omitted)
- `--port`: Camera port (default: 80 or 443 if `--ssl`)
- `--ssl`: Connect using HTTPS protocol
- `--no-verify-ssl`: Disable SSL/TLS certificate verification (useful for self-signed camera certificates)
- `--channel`: Camera channel index, 0-based (default: `0`, or env `AMCREST_CHANNEL`)
- `--output-format`: Output video format (`mp4`, `mkv`, `avi`, `mov`, `ts`, default: `mp4`)
- `--output-dir`: Output directory (default: current working directory)
- `--output-file`: Custom output filename (resolved relative to `--output-dir` if relative)
- `--keep-files`: Keep individual downloaded segment files after merge
- `--max-concurrent`: Maximum concurrent downloads (default: `4`)
- `--list-only`: List matching recordings in a table without downloading or merging
- `--log-level`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, default: `INFO`)
- `--log-file`: Optional file path to write log output

### Examples

Basic usage:
```bash
python main.py \
  --host 192.168.1.100 \
  --username admin \
  --start "2026-01-16T08:00:00" \
  --end "2026-01-16T18:00:00"
```

With timezone and HTTPS:
```bash
python main.py \
  --host kitchen.cameras.home.com \
  --username admin \
  --ssl \
  --start "2026-01-16T08:00:00-08:00" \
  --end "2026-01-16T18:00:00-08:00"
```

Custom output and settings:
```bash
python main.py \
  --host 192.168.1.100 \
  --username admin \
  --start "2026-01-16T20:00:00" \
  --end "2026-01-16T22:00:00" \
  --output-format mkv \
  --output-file my_recording.mkv \
  --max-concurrent 8 \
  --keep-files
```

List recordings only:
```bash
python main.py \
  --host 192.168.1.100 \
  --username admin \
  --start "2026-01-16T08:00:00" \
  --end "2026-01-16T10:00:00" \
  --list-only
```

## Notes

- Password is prompted securely when not provided via `--password` or `AMCREST_PASSWORD`.
- Individual recordings are downloaded to a temporary directory (`.amcrest_download`).
- Videos are concatenated in chronological order.
- Amcrest cameras often record audio in G.711 PCM (`pcm_alaw`/`pcm_mulaw`). If `-c copy` fails when targeting MP4, the merger automatically falls back to `-c:a aac` while keeping video lossless.
- Channel index is 0-based: `0` corresponds to the primary/only sensor on standalone cameras, and the first channel on multi-channel NVRs.
- Gaps in recording coverage will appear as time jumps in the merged video.
- Only mp4/dav video files are downloaded (jpg snapshots are skipped).
- API endpoints used:
  - `/cgi-bin/mediaFileFind.cgi` - Search for recordings
  - `/cgi-bin/RPC_Loadfile/` - Download video files
