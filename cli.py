import argparse
import getpass
import sys
from pathlib import Path

from amcrest_api import AmcrestClient
from downloader import RecordingDownloader
from merger import VideoMerger
from models import TimeRange


class CLI:
    def __init__(self):
        self._parser = self._create_parser()

    def _create_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Download and merge Amcrest camera recordings"
        )
        parser.add_argument(
            "--host", required=True, help="Camera IP address or hostname"
        )
        parser.add_argument("--username", required=True, help="Camera username")
        parser.add_argument(
            "--start", required=True, help="Start time (ISO 8601 format)"
        )
        parser.add_argument("--end", required=True, help="End time (ISO 8601 format)")
        parser.add_argument(
            "--output-format",
            default="mp4",
            choices=["mp4", "mkv", "avi"],
            help="Output video format (default: mp4)",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=Path.cwd(),
            help="Output directory (default: current directory)",
        )
        parser.add_argument(
            "--output-file",
            type=Path,
            help="Output file name (default: merged_YYYYMMDD_HHMMSS.format)",
        )
        parser.add_argument(
            "--keep-files",
            action="store_true",
            help="Keep individual downloaded files after merge",
        )
        parser.add_argument(
            "--max-concurrent",
            type=int,
            default=4,
            help="Maximum concurrent downloads (default: 4)",
        )
        parser.add_argument(
            "--channel", type=int, default=1, help="Camera channel (default: 1)"
        )
        return parser

    def run(self, args: list[str] = None) -> int:
        parsed_args = self._parser.parse_args(args)

        try:
            password = self._get_password()
            time_range = self._parse_time_range(parsed_args.start, parsed_args.end)

            client = self._create_client(
                parsed_args.host, parsed_args.username, password
            )
            try:
                recordings = self._search_recordings(
                    client, time_range, parsed_args.channel
                )
                if not recordings:
                    return 0

                downloaded_files = self._download_recordings(
                    client,
                    recordings,
                    parsed_args.output_dir,
                    parsed_args.max_concurrent,
                )
                if not downloaded_files:
                    return 1

                output_file = self._determine_output_file(
                    parsed_args.output_file,
                    parsed_args.output_dir,
                    parsed_args.output_format,
                    time_range,
                )

                if not self._merge_recordings(
                    downloaded_files,
                    output_file,
                    parsed_args.output_format,
                    parsed_args.keep_files,
                ):
                    return 1

                self._cleanup_work_dir(parsed_args.output_dir, parsed_args.keep_files)
                print(f"Successfully created: {output_file}")
                return 0

            finally:
                client.close()

        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return 130
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    def _get_password(self) -> str:
        return getpass.getpass("Password: ")

    def _parse_time_range(self, start_str: str, end_str: str) -> TimeRange:
        try:
            return TimeRange.from_iso8601(start_str, end_str)
        except ValueError as e:
            raise ValueError(f"Invalid date format: {e}")

    def _create_client(self, host: str, username: str, password: str) -> AmcrestClient:
        return AmcrestClient(host, username, password)

    def _search_recordings(
        self, client: AmcrestClient, time_range: TimeRange, channel: int
    ) -> list:
        start_str = time_range.start.isoformat()
        end_str = time_range.end.isoformat()
        print(f"Searching for recordings from {start_str} to {end_str}...")

        recordings = client.find_recordings(time_range, channel)

        if not recordings:
            print("No recordings found in the specified time range.")
        else:
            print(f"Found {len(recordings)} recording(s)")

        return recordings

    def _download_recordings(
        self,
        client: AmcrestClient,
        recordings: list,
        output_dir: Path,
        max_concurrent: int,
    ) -> list[Path]:
        downloader = RecordingDownloader(client, max_concurrent)
        work_dir = output_dir / ".amcrest_download"

        print("Downloading recordings...")
        downloaded_files = downloader.download_all(
            recordings, work_dir, progress_callback=self._print_progress
        )

        if not downloaded_files:
            print("No files were downloaded successfully.")

        return downloaded_files

    def _merge_recordings(
        self,
        downloaded_files: list[Path],
        output_file: Path,
        output_format: str,
        keep_files: bool,
    ) -> bool:
        print(f"\nMerging {len(downloaded_files)} file(s)...")

        merger = VideoMerger(output_format)
        success = merger.merge(downloaded_files, output_file, cleanup=not keep_files)

        if not success:
            print("Merge failed.", file=sys.stderr)

        return success

    def _cleanup_work_dir(self, output_dir: Path, keep_files: bool):
        if not keep_files:
            work_dir = output_dir / ".amcrest_download"
            try:
                work_dir.rmdir()
            except Exception:
                pass

    def _print_progress(self, completed: int, total: int):
        percent = (completed / total) * 100
        print(f"Progress: {completed}/{total} ({percent:.1f}%)", end="\r")

    def _determine_output_file(
        self,
        specified_output: Path,
        output_dir: Path,
        output_format: str,
        time_range: TimeRange,
    ) -> Path:
        if specified_output:
            return specified_output

        timestamp = time_range.start.strftime("%Y%m%d_%H%M%S")
        filename = f"merged_{timestamp}.{output_format}"
        return output_dir / filename
