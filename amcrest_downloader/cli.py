import argparse
import getpass
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from amcrest_downloader.api import AmcrestClient
from amcrest_downloader.downloader import RecordingDownloader
from amcrest_downloader.merger import VideoMerger
from amcrest_downloader.models import Recording, TimeRange


def _version() -> str:
    try:
        return version("amcrest-downloader")
    except PackageNotFoundError:
        return "unknown"


def configure_logging(
    level: str = "warning",
    log_file: Path | None = None,
) -> None:
    log_level = getattr(logging, level.upper(), logging.WARNING)
    handler: logging.Handler = (
        logging.FileHandler(log_file, mode="a", encoding="utf-8")
        if log_file
        else logging.StreamHandler(sys.stderr)
    )
    handler.setLevel(log_level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
    logging.basicConfig(level=log_level, handlers=[handler], force=True)


def _int_in_range(low: int, high: int | None = None):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from None
        if number < low or (high is not None and number > high):
            bound = f">= {low}" if high is None else f"between {low} and {high}"
            raise argparse.ArgumentTypeError(f"must be {bound}, got {number}")
        return number

    return parse


class CLI:
    def __init__(self):
        self._parser = self._create_parser()
        self._logger = logging.getLogger(__name__)

    def _create_parser(self) -> argparse.ArgumentParser:
        env_host = os.getenv("AMCREST_HOST")
        env_port = os.getenv("AMCREST_PORT") or None
        env_user = os.getenv("AMCREST_USERNAME")
        env_pass = os.getenv("AMCREST_PASSWORD")
        env_chan = os.getenv("AMCREST_CHANNEL") or "0"

        parser = argparse.ArgumentParser(
            prog="amcrest-downloader",
            description="Download and merge Amcrest/Dahua camera recordings",
        )
        parser.add_argument(
            "--version",
            action="version",
            version=f"%(prog)s {_version()}",
        )
        parser.add_argument(
            "--host",
            default=env_host,
            required=env_host is None,
            help="Camera IP address or hostname (or env AMCREST_HOST)",
        )
        parser.add_argument(
            "--port",
            type=_int_in_range(1, 65535),
            default=env_port,
            help="Camera HTTP/HTTPS port (or env AMCREST_PORT)",
        )
        parser.add_argument(
            "-u",
            "--username",
            "--user",
            dest="username",
            default=env_user,
            required=env_user is None,
            help="Camera username (or env AMCREST_USERNAME)",
        )
        parser.add_argument(
            "-p",
            "--password",
            dest="password",
            default=env_pass,
            help="Camera password (or env AMCREST_PASSWORD, prompts if omitted)",
        )
        parser.add_argument(
            "--ssl",
            action="store_true",
            help="Connect using HTTPS protocol",
        )
        parser.add_argument(
            "--no-verify-ssl",
            action="store_true",
            help="Disable SSL/TLS certificate verification",
        )
        parser.add_argument(
            "--start",
            required=True,
            help="Start time (ISO 8601 format, e.g. 2026-01-16T08:00:00)",
        )
        parser.add_argument(
            "--end",
            required=True,
            help="End time (ISO 8601 format, e.g. 2026-01-16T10:00:00)",
        )
        parser.add_argument(
            "--channel",
            type=_int_in_range(0),
            default=env_chan,
            help="Camera channel index (default: 0, or env AMCREST_CHANNEL)",
        )
        parser.add_argument(
            "--output-format",
            default="mp4",
            choices=["mp4", "mkv", "avi", "mov", "ts"],
            help="Output video format (default: mp4)",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=Path.cwd(),
            help="Output directory (default: current working directory)",
        )
        parser.add_argument(
            "--output-file",
            type=Path,
            help="Custom output file name (default: merged_YYYYMMDD_HHMMSS.format)",
        )
        parser.add_argument(
            "--keep-files",
            action="store_true",
            help="Keep individual downloaded segment files after merge",
        )
        parser.add_argument(
            "--max-concurrent",
            type=_int_in_range(1),
            default=4,
            help="Maximum concurrent downloads (default: 4)",
        )
        parser.add_argument(
            "--list-only",
            action="store_true",
            help="List matching recordings in a table without downloading",
        )
        parser.add_argument(
            "--log-level",
            choices=["debug", "info", "warning", "error", "critical"],
            default="warning",
            help="Set logging verbosity (default: warning)",
        )
        parser.add_argument(
            "--log-file",
            type=Path,
            help="Write logs to file instead of stderr",
        )
        return parser

    def run(self, args: list[str] | None = None) -> int:
        try:
            parsed_args = self._parser.parse_args(args)
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else 2

        configure_logging(
            level=parsed_args.log_level,
            log_file=parsed_args.log_file,
        )

        try:
            return self._execute(parsed_args)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.", file=sys.stderr)
            return 130
        except Exception as e:
            self._logger.debug("Fatal error", exc_info=True)
            print(f"Error: {e}", file=sys.stderr)
            return 1

    def _execute(self, args: argparse.Namespace) -> int:
        self._logger.info("Starting Amcrest recording downloader")
        if not args.list_only and shutil.which("ffmpeg") is None:
            print("Error: ffmpeg not found. Please install ffmpeg.", file=sys.stderr)
            return 1

        password = self._resolve_password(args.password)
        time_range = self._parse_time_range(args.start, args.end)

        with self._create_client(args, password) as client:
            search_range = self._to_camera_range(client, time_range)
            recordings = self._search_recordings(client, search_range, args.channel)
            if not recordings:
                return 0

            if args.list_only:
                self._render_table(recordings)
                return 0

            try:
                return self._download_and_merge(client, recordings, args, time_range)
            finally:
                self._cleanup_work_dir(args.output_dir, args.keep_files)

    def _download_and_merge(
        self,
        client: AmcrestClient,
        recordings: list[Recording],
        args: argparse.Namespace,
        time_range: TimeRange,
    ) -> int:
        downloaded_files = self._download_recordings(
            client, recordings, args.output_dir, args.max_concurrent
        )
        if not downloaded_files:
            print("No files were downloaded successfully.", file=sys.stderr)
            return 1

        if len(downloaded_files) < len(recordings):
            print(
                f"Warning: Only {len(downloaded_files)} of {len(recordings)} "
                "segments downloaded successfully.",
                file=sys.stderr,
            )

        output_format = args.output_format
        if args.output_file and args.output_file.suffix:
            suffix_fmt = args.output_file.suffix.lstrip(".").lower()
            if suffix_fmt in VideoMerger.SUPPORTED_FORMATS:
                output_format = suffix_fmt

        output_file = self._determine_output_file(
            args.output_file, args.output_dir, output_format, time_range
        )
        if self._merge_recordings(downloaded_files, output_file, output_format, args.keep_files):
            print(f"Successfully generated: {output_file}")
            return 0
        return 1

    def _resolve_password(self, cli_password: str | None) -> str:
        if cli_password:
            return cli_password
        try:
            return getpass.getpass("Camera Password: ")
        except (EOFError, Exception) as e:
            raise ValueError(
                "Password required. Provide via AMCREST_PASSWORD env var or --password flag "
                "in non-interactive environments."
            ) from e

    def _parse_time_range(self, start_str: str, end_str: str) -> TimeRange:
        try:
            return TimeRange.from_iso8601(start_str, end_str)
        except Exception as e:
            raise ValueError(f"Invalid date/time range: {e}") from e

    def _to_camera_range(self, client: AmcrestClient, time_range: TimeRange) -> TimeRange:
        if time_range.start.tzinfo is None:
            return time_range
        camera_now = client.current_time()
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
        quarter_hours = round((camera_now - utc_now).total_seconds() / 900)
        offset = timedelta(minutes=15 * quarter_hours)
        self._logger.info(f"Camera UTC offset: {offset}")
        return time_range.to_camera_local(offset)

    def _create_client(self, args: argparse.Namespace, password: str) -> AmcrestClient:
        return AmcrestClient(
            host=args.host,
            username=args.username,
            password=password,
            port=args.port,
            ssl=args.ssl,
            verify_ssl=not args.no_verify_ssl,
            max_connections=args.max_concurrent,
        )

    def _search_recordings(
        self, client: AmcrestClient, time_range: TimeRange, channel: int
    ) -> list[Recording]:
        start_str, end_str = time_range.to_amcrest_format()
        self._logger.info(
            f"Searching for recordings: channel={channel}, start={start_str}, end={end_str}"
        )
        print(f"Searching for channel {channel} recordings between {start_str} and {end_str}...")

        recordings = client.find_recordings(time_range, channel)
        if not recordings:
            print("No recordings found in the specified time range.")
        else:
            print(f"Found {len(recordings)} recording segment(s).")

        return recordings

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit_idx = 0
        while size >= 1024.0 and unit_idx < len(units) - 1:
            size /= 1024.0
            unit_idx += 1
        return f"{size:.1f} {units[unit_idx]}"

    def _render_table(self, recordings: list[Recording]) -> None:
        total_size = sum(r.file_size for r in recordings)
        total_duration = sum(r.duration_seconds for r in recordings)

        header = (
            f"{'#':<4} {'Start Time':<20} {'End Time':<20} "
            f"{'Duration':<10} {'Size':<10} {'File Path'}"
        )
        divider = "-" * len(header)
        print("\n" + divider)
        print(header)
        print(divider)

        for idx, rec in enumerate(recordings, 1):
            dur = f"{int(rec.duration_seconds)}s"
            size = self._format_size(rec.file_size)
            print(
                f"{idx:<4} {rec.start_time!s:<20} {rec.end_time!s:<20} "
                f"{dur:<10} {size:<10} {rec.file_path}"
            )

        print(divider)
        print(
            f"Total: {len(recordings)} files | Duration: {int(total_duration)}s | "
            f"Size: {self._format_size(total_size)}\n"
        )

    def _download_recordings(
        self,
        client: AmcrestClient,
        recordings: list[Recording],
        output_dir: Path,
        max_concurrent: int,
    ) -> list[Path]:
        downloader = RecordingDownloader(client, max_concurrent=max_concurrent)
        work_dir = output_dir / ".amcrest_download"

        self._logger.info(
            f"Starting download: {len(recordings)} recordings, max_concurrent={max_concurrent}"
        )
        print("Downloading recording segments...")
        downloaded_files = downloader.download_all(
            recordings, work_dir, progress_callback=self._print_progress
        )
        print()
        return downloaded_files

    def _merge_recordings(
        self,
        downloaded_files: list[Path],
        output_file: Path,
        output_format: str,
        keep_files: bool,
    ) -> bool:
        self._logger.info(f"Starting merge: {len(downloaded_files)} files -> {output_file}")
        print(f"Merging {len(downloaded_files)} segment(s) into {output_file.name}...")

        merger = VideoMerger(output_format)
        return merger.merge(downloaded_files, output_file, cleanup=not keep_files)

    def _cleanup_work_dir(self, output_dir: Path, keep_files: bool) -> None:
        if not keep_files:
            work_dir = output_dir / ".amcrest_download"
            self._logger.debug(f"Cleaning up work directory: {work_dir}")
            try:
                if work_dir.exists():
                    shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as e:
                self._logger.warning(f"Could not remove work directory {work_dir}: {e}")

    def _print_progress(self, completed: int, total: int) -> None:
        percent = (completed / total) * 100 if total > 0 else 0
        print(f"Progress: [{completed}/{total}] ({percent:.1f}%)", end="\r", flush=True)

    def _determine_output_file(
        self,
        specified_output: Path | None,
        output_dir: Path,
        output_format: str,
        time_range: TimeRange,
    ) -> Path:
        if specified_output:
            if specified_output.is_absolute():
                return specified_output
            return output_dir / specified_output

        timestamp = time_range.start.strftime("%Y%m%d_%H%M%S")
        filename = f"merged_{timestamp}.{output_format}"
        return output_dir / filename


def main(argv: list[str] | None = None) -> int:
    return CLI().run(argv)
