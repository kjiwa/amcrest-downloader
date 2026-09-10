import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import os

from cli import CLI
from models import Recording
from amcrest_api import AmcrestAuthError
from datetime import datetime


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.cli = CLI()
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_time_range_valid(self):
        tr = self.cli._parse_time_range("2026-01-16T08:00:00", "2026-01-16T10:00:00")
        self.assertEqual(tr.start, datetime(2026, 1, 16, 8, 0, 0))
        self.assertEqual(tr.end, datetime(2026, 1, 16, 10, 0, 0))

    def test_parse_time_range_invalid_format(self):
        with self.assertRaises(ValueError):
            self.cli._parse_time_range("not-a-date", "2026-01-16T10:00:00")

    def test_determine_output_file_default(self):
        tr = self.cli._parse_time_range("2026-01-16T08:00:00", "2026-01-16T10:00:00")
        out = self.cli._determine_output_file(None, self.temp_dir, "mp4", tr)
        self.assertEqual(out, self.temp_dir / "merged_20260116_080000.mp4")

    def test_determine_output_file_specified(self):
        tr = self.cli._parse_time_range("2026-01-16T08:00:00", "2026-01-16T10:00:00")
        custom_path = self.temp_dir / "custom.mp4"
        out = self.cli._determine_output_file(custom_path, self.temp_dir, "mp4", tr)
        self.assertEqual(out, custom_path)

    def test_determine_output_file_relative_uses_output_dir(self):
        tr = self.cli._parse_time_range("2026-01-16T08:00:00", "2026-01-16T10:00:00")
        relative_path = Path("custom.mp4")
        out = self.cli._determine_output_file(relative_path, self.temp_dir, "mp4", tr)
        self.assertEqual(out, self.temp_dir / "custom.mp4")

    @patch.dict(os.environ, {"AMCREST_PORT": "notanumber", "AMCREST_CHANNEL": "invalid"})
    def test_env_port_and_channel_invalid_fallbacks(self):
        cli = CLI()
        args = cli._parser.parse_args([
            "--host", "192.168.1.100",
            "--username", "admin",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T10:00:00",
        ])
        self.assertIsNone(args.port)
        self.assertEqual(args.channel, 0)

    def test_cleanup_work_dir_removes_non_empty_dir(self):
        work_dir = self.temp_dir / ".amcrest_download"
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "leftover.mp4").write_text("data")
        self.cli._cleanup_work_dir(self.temp_dir, keep_files=False)
        self.assertFalse(work_dir.exists())

    @patch.dict(os.environ, {"AMCREST_PASSWORD": "env_password"})
    @patch("cli.AmcrestClient")
    def test_run_with_env_password_and_list_only(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client
        mock_client.find_recordings.return_value = [
            Recording(
                start_time=datetime(2026, 1, 16, 8, 0, 0),
                end_time=datetime(2026, 1, 16, 8, 15, 0),
                file_path=Path("/mnt/sd/test1.mp4"),
                file_size=1048576,
            )
        ]

        exit_code = self.cli.run([
            "--host", "192.168.1.100",
            "--username", "admin",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T09:00:00",
            "--list-only",
        ])

        self.assertEqual(exit_code, 0)
        mock_client.find_recordings.assert_called_once()
        mock_client.download_recording.assert_not_called()



    def test_format_size(self):
        self.assertEqual(self.cli._format_size(0), "0 B")
        self.assertEqual(self.cli._format_size(500), "500.0 B")
        self.assertEqual(self.cli._format_size(1024), "1.0 KB")
        self.assertEqual(self.cli._format_size(1048576), "1.0 MB")
        self.assertEqual(self.cli._format_size(1073741824), "1.0 GB")

    def test_missing_required_args_returns_code_2(self):
        exit_code = self.cli.run([])
        self.assertEqual(exit_code, 2)

    @patch("cli.AmcrestClient")
    def test_run_keyboard_interrupt_returns_130(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = KeyboardInterrupt()
        mock_client_cls.return_value = mock_client

        exit_code = self.cli.run([
            "--host", "192.168.1.100",
            "--username", "admin",
            "--password", "pass",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T09:00:00",
        ])
        self.assertEqual(exit_code, 130)

    @patch("cli.VideoMerger")
    @patch("cli.RecordingDownloader")
    @patch("cli.AmcrestClient")
    def test_full_download_and_merge_flow(
        self, mock_client_cls, mock_downloader_cls, mock_merger_cls
    ):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client_cls.return_value = mock_client

        rec = Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/test1.mp4"),
            file_size=1048576,
        )
        mock_client.find_recordings.return_value = [rec]

        mock_downloader = MagicMock()
        mock_downloader.download_all.return_value = [self.temp_dir / "rec1.mp4"]
        mock_downloader_cls.return_value = mock_downloader

        mock_merger = MagicMock()
        mock_merger.merge.return_value = True
        mock_merger_cls.return_value = mock_merger

        exit_code = self.cli.run([
            "--host", "192.168.1.100",
            "--username", "admin",
            "--password", "pass",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T09:00:00",
            "--output-dir", str(self.temp_dir),
        ])

        self.assertEqual(exit_code, 0)
        mock_client.find_recordings.assert_called_once()
        mock_downloader.download_all.assert_called_once()
        mock_merger.merge.assert_called_once()

    def test_cli_argument_aliases(self):
        args1 = self.cli._parser.parse_args([
            "--host", "192.168.1.100",
            "-u", "myuser",
            "-p", "mypass",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T09:00:00",
        ])
        self.assertEqual(args1.username, "myuser")
        self.assertEqual(args1.password, "mypass")

        args2 = self.cli._parser.parse_args([
            "--host", "192.168.1.100",
            "--user", "myuser2",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T09:00:00",
        ])
        self.assertEqual(args2.username, "myuser2")

    @patch("cli.AmcrestClient")
    def test_run_auth_error_returns_1(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = AmcrestAuthError(
            "Authentication failed: invalid username or password"
        )
        mock_client_cls.return_value = mock_client

        exit_code = self.cli.run([
            "--host", "192.168.1.100",
            "--username", "admin",
            "--password", "wrong",
            "--start", "2026-01-16T08:00:00",
            "--end", "2026-01-16T09:00:00",
        ])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()

