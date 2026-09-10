import argparse
import getpass
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from amcrest_api import AmcrestClient
from downloader import RecordingDownloader
from logger import configure_logging, get_logger
from merger import VideoMerger
from models import Recording, TimeRange


class CLI:
    def __init__(self):
        self._parser = self._create_parser()
        self._logger = get_logger(__name__)

    def _create_parser(self) -> argparse.ArgumentParser:
        env_host = os.getenv("AMCREST_HOST")
        env_port = os.getenv("AMCREST_PORT")
        env_user = os.getenv("AMCREST_USERNAME")
        env_pass = os.getenv("AMCREST_PASSWORD")
        env_chan = os.getenv("AMCREST_CHANNEL")

        parsed_port: Optional[int] = None
        if env_port:
            try:
                parsed_port = int(env_port)
            except ValueError:
                pass

        parsed_channel = 0
        if env_chan:
            try:
                parsed_channel = int(env_chan)
            except ValueError:
                pass

        parser = argparse.ArgumentParser(
            description="Download and merge Amcrest/Dahua camera recordings"
        )
        parser.add_argument(
            "--host",
            default=env_host,
            required=env_host is None,
            help="Camera IP address or hostname (or env AMCREST_HOST)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=parsed_port,
            help="Camera HTTP/HTTPS port (or env AMCREST_PORT)",
        )
        parser.add_argument(
            "--username",
            default=env_user,
            required=env_user is None,
            help="Camera username (or env AMCREST_USERNAME)",
        )
        parser.add_argument(
            "--password",
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
            type=int,
            default=parsed_channel,
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
            type=int,
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

    def run(self, args: Optional[list[str]] = None) -> int:
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
            self._logger.error(f"Fatal error: {e}", exc_info=True)
            print(f"Error: {e}", file=sys.stderr)
            return 1


    def _execute(self, args: argparse.Namespace) -> int:
        self._logger.info("Starting Amcrest recording downloader")
        password = self._resolve_password(args.password)
        time_range = self._parse_time_range(args.start, args.end)

        with self._create_client(args, password) as client:
            recordings = self._search_recordings(client, time_range, args.channel)
            if not recordings:
                return 0

            if args.list_only:
                self._render_table(recordings)
                return 0

            downloaded_files = self._download_recordings(
                client, recordings, args.output_dir, args.max_concurrent
            )
            if not downloaded_files:
                print("No files were downloaded successfully.", file=sys.stderr)
                return 1

            if len(downloaded_files) < len(recordings):
                print(
                    f"Warning: Only {len(downloaded_files)} of {len(recordings)} segments downloaded successfully.",
                    file=sys.stderr,
                )

            output_file = self._determine_output_file(
                args.output_file, args.output_dir, args.output_format, time_range
            )
            try:
                merge_success = self._merge_recordings(
                    downloaded_files, output_file, args.output_format, args.keep_files
                )
            finally:
                self._cleanup_work_dir(args.output_dir, args.keep_files)

            if merge_success:
                print(f"Successfully generated: {output_file}")
                return 0
            return 1

    def _resolve_password(self, cli_password: Optional[str]) -> str:
        if cli_password:
            return cli_password
        env_password = os.getenv("AMCREST_PASSWORD")
        if env_password:
            return env_password
        try:
            return getpass.getpass("Camera Password: ")
        except (EOFError, Exception):
            raise ValueError(
                "Password required. Provide via AMCREST_PASSWORD env var or --password flag in non-interactive environments."
            )


    def _parse_time_range(self, start_str: str, end_str: str) -> TimeRange:
        try:
            return TimeRange.from_iso8601(start_str, end_str)
        except Exception as e:
            raise ValueError(f"Invalid date/time range: {e}")

    def _create_client(
        self, args: argparse.Namespace, password: str
    ) -> AmcrestClient:
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

        header = f"{'#':<4} {'Start Time':<20} {'End Time':<20} {'Duration':<10} {'Size':<10} {'File Path'}"
        divider = "-" * len(header)
        print("\n" + divider)
        print(header)
        print(divider)

        for idx, rec in enumerate(recordings, 1):
            dur = f"{int(rec.duration_seconds)}s"
            size = self._format_size(rec.file_size)
            print(
                f"{idx:<4} {str(rec.start_time):<20} {str(rec.end_time):<20} {dur:<10} {size:<10} {rec.file_path}"
            )

        print(divider)
        print(
            f"Total: {len(recordings)} files | Duration: {int(total_duration)}s | Size: {self._format_size(total_size)}\n"
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
        self._logger.info(
            f"Starting merge: {len(downloaded_files)} files -> {output_file}"
        )
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
        specified_output: Optional[Path],
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

