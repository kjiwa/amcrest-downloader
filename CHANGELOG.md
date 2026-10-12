# Changelog

## 0.3.0

amcrest-downloader is now published on PyPI. Install it with `pipx install
amcrest-downloader` or `uv tool install amcrest-downloader`, then run
`amcrest-downloader`. `--version` prints the installed version.

The code now lives in the `amcrest_downloader` package. `python main.py` and the
top-level modules (`cli`, `models`, `logger`, and the rest) are gone; use the
`amcrest-downloader` command or `python -m amcrest_downloader`.

Fixes:

- A failure at the default log level prints one `Error: <message>` line instead of a
  traceback; `--log-level debug` shows the traceback.
- `--start` and `--end` values with a UTC offset are converted to the camera's clock
  using the camera's current offset, so `08:00-08:00` and `08:00+00:00` no longer
  search the same window. Values without an offset are used as given.
- An authentication error during a download stops the run instead of being swallowed,
  and queued downloads are cancelled on any failure or Ctrl-C.
- A missing `ffmpeg` is reported before any download starts.
- The `.amcrest_download` working directory is removed after a failed or interrupted
  run, unless `--keep-files` is set.
- Downloaded segments are kept in `.amcrest_download` when the merge fails, and the
  path is printed, so the download need not be repeated.
- A run where only some segments downloaded still writes the merged file but exits 1.
- `--start` and `--end` accept a trailing `Z` on Python 3.10.
- An invalid `AMCREST_PORT` or `AMCREST_CHANNEL` is now an error rather than being
  ignored. `--max-concurrent` must be positive, and `--channel` and `--port` are
  range-checked.
