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
        password = getpass.getpass("Password: ")
        try:
            time_range = TimeRange.from_iso8601(parsed_args.start, parsed_args.end)
        except ValueError as e:
            print(f"Error: Invalid date format: {e}", file=sys.stderr)
            return 1

        client = None
        try:
            client = AmcrestClient(parsed_args.host, parsed_args.username, password)

            print(
                f"Searching for recordings from {parsed_args.start} to {parsed_args.end}..."
            )
            recordings = client.find_recordings(time_range, parsed_args.channel)
            if not recordings:
                print("No recordings found in the specified time range.")
                return 0

            print(f"Found {len(recordings)} recording(s)")
            downloader = RecordingDownloader(client, parsed_args.max_concurrent)
            work_dir = parsed_args.output_dir / ".amcrest_download"

            print("Downloading recordings...")
            downloaded_files = downloader.download_all(
                recordings, work_dir, progress_callback=self._print_progress
            )
            if not downloaded_files:
                print("No files were downloaded successfully.")
                return 1

            print(f"\nMerging {len(downloaded_files)} file(s)...")
            output_file = self._determine_output_file(
                parsed_args.output_file,
                parsed_args.output_dir,
                parsed_args.output_format,
                time_range,
            )
            merger = VideoMerger(parsed_args.output_format)
            success = merger.merge(
                downloaded_files, output_file, cleanup=not parsed_args.keep_files
            )

            if success:
                print(f"Successfully created: {output_file}")

                if not parsed_args.keep_files:
                    try:
                        work_dir.rmdir()
                    except Exception:
                        pass

                return 0
            else:
                print("Merge failed.", file=sys.stderr)
                return 1

        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return 130
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        finally:
            if client:
                client.close()

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
