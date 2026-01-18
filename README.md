# Amcrest Camera Recording Downloader

A Python utility to download and merge video recordings from Amcrest IP cameras using the HTTP API.

## Features

- Search for recordings by date/time range
- Concurrent downloads (default: 4 simultaneous)
- Automatic video merging using ffmpeg
- Support for multiple output formats (mp4, mkv, avi)
- Timezone-aware datetime input
- Automatic retry on failed downloads

## Requirements

- Python 3.10+
- FFmpeg (must be installed and in PATH)
- Dependencies: `requests`

## Usage

```bash
python main.py --host CAMERA_HOST --username USERNAME --start START_TIME --end END_TIME
```

### Required Arguments

- `--host`: Camera IP address or hostname (e.g., `192.168.1.100` or `kitchen.cameras.home.com`)
- `--username`: Camera username
- `--start`: Start time in ISO 8601 format (e.g., `2026-01-16T20:00:00`)
- `--end`: End time in ISO 8601 format (e.g., `2026-01-16T22:00:00`)

### Optional Arguments

- `--channel`: Camera channel (default: 1)
- `--output-format`: Output video format - `mp4`, `mkv`, or `avi` (default: `mp4`)
- `--output-dir`: Output directory (default: current directory)
- `--output-file`: Custom output filename
- `--keep-files`: Keep individual downloaded files after merge
- `--max-concurrent`: Maximum concurrent downloads (default: 4)

### Examples

Basic usage:
```bash
python main.py \
  --host 192.168.1.100 \
  --username admin \
  --start "2026-01-16T08:00:00" \
  --end "2026-01-16T18:00:00"
```

With timezone:
```bash
python main.py \
  --host kitchen.cameras.home.com \
  --username admin \
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

## Notes

- Password is prompted securely (not passed as command-line argument)
- Individual recordings are downloaded to a temporary directory (`.amcrest_download`)
- Videos are concatenated in chronological order
- Gaps in recording coverage will appear as time jumps in the merged video
- Only mp4 video files are downloaded (jpg snapshots are skipped)
- Default channel is 1 (channel 0 may not work on all camera models)
- API endpoints used:
  - `/cgi-bin/mediaFileFind.cgi` - Search for recordings
  - `/cgi-bin/RPC_Loadfile/` - Download video files
