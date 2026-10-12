import io
import logging
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from amcrest_downloader.api import AmcrestAuthError
from amcrest_downloader.cli import CLI, configure_logging, main
from amcrest_downloader.models import Recording


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.cli = CLI()
        self.temp_dir = Path(tempfile.mkdtemp())
        self._stdout_patch = patch("sys.stdout", new_callable=io.StringIO)
        self._stderr_patch = patch("sys.stderr", new_callable=io.StringIO)
        self.mock_stdout = self._stdout_patch.start()
        self.mock_stderr = self._stderr_patch.start()
        self._which_patch = patch(
            "amcrest_downloader.cli.shutil.which", return_value="/usr/bin/ffmpeg"
        )
        self._which_patch.start()

    def tearDown(self):
        self._which_patch.stop()
        self._stdout_patch.stop()
        self._stderr_patch.stop()
        logging.getLogger().handlers = []
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

    def _base_args(self, *extra):
        return [
            "--host",
            "192.168.1.100",
            "--username",
            "admin",
            "--password",
            "pass",
            "--start",
            "2026-01-16T08:00:00",
            "--end",
            "2026-01-16T10:00:00",
            *extra,
        ]

    def test_invalid_env_port_is_an_error(self):
        with patch.dict(os.environ, {"AMCREST_PORT": "notanumber"}):
            self.assertEqual(CLI().run(self._base_args()), 2)
        self.assertIn("--port", self.mock_stderr.getvalue())

    def test_invalid_env_channel_is_an_error(self):
        with patch.dict(os.environ, {"AMCREST_CHANNEL": "invalid"}):
            self.assertEqual(CLI().run(self._base_args()), 2)
        self.assertIn("--channel", self.mock_stderr.getvalue())

    def test_valid_env_port_and_channel_are_used(self):
        with patch.dict(os.environ, {"AMCREST_PORT": "8080", "AMCREST_CHANNEL": "2"}):
            args = CLI()._parser.parse_args(self._base_args())
        self.assertEqual(args.port, 8080)
        self.assertEqual(args.channel, 2)

    def test_out_of_range_numeric_options_are_errors(self):
        for extra in (
            ["--max-concurrent", "0"],
            ["--port", "0"],
            ["--port", "65536"],
            ["--channel", "-1"],
            ["--port", "abc"],
        ):
            with self.subTest(extra=extra):
                self.assertEqual(self.cli.run(self._base_args(*extra)), 2)

    def test_numeric_option_bounds_are_accepted(self):
        args = self.cli._parser.parse_args(
            self._base_args("--max-concurrent", "1", "--port", "65535", "--channel", "0")
        )
        self.assertEqual((args.max_concurrent, args.port, args.channel), (1, 65535, 0))

    def test_cleanup_work_dir_removes_non_empty_dir(self):
        work_dir = self.temp_dir / ".amcrest_download"
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "leftover.mp4").write_text("data")
        self.cli._cleanup_work_dir(self.temp_dir, keep_files=False)
        self.assertFalse(work_dir.exists())

    @patch.dict(os.environ, {"AMCREST_PASSWORD": "env_password"})
    @patch("amcrest_downloader.cli.AmcrestClient")
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

        exit_code = CLI().run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
                "--list-only",
            ]
        )

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

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_run_keyboard_interrupt_returns_130(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = KeyboardInterrupt()
        mock_client_cls.return_value = mock_client

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(exit_code, 130)

    @patch("amcrest_downloader.cli.VideoMerger")
    @patch("amcrest_downloader.cli.RecordingDownloader")
    @patch("amcrest_downloader.cli.AmcrestClient")
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

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
                "--output-dir",
                str(self.temp_dir),
            ]
        )

        self.assertEqual(exit_code, 0)
        mock_client.find_recordings.assert_called_once()
        mock_downloader.download_all.assert_called_once()
        mock_merger.merge.assert_called_once()

    def test_cli_argument_aliases(self):
        args1 = self.cli._parser.parse_args(
            [
                "--host",
                "192.168.1.100",
                "-u",
                "myuser",
                "-p",
                "mypass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(args1.username, "myuser")
        self.assertEqual(args1.password, "mypass")

        args2 = self.cli._parser.parse_args(
            [
                "--host",
                "192.168.1.100",
                "--user",
                "myuser2",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(args2.username, "myuser2")

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_run_auth_error_returns_1(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = AmcrestAuthError(
            "Authentication failed: invalid username or password"
        )
        mock_client_cls.return_value = mock_client

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "wrong",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(exit_code, 1)

    @patch("getpass.getpass", return_value="prompted_pass")
    def test_resolve_password_prompt_success(self, mock_getpass):
        password = self.cli._resolve_password(None)
        self.assertEqual(password, "prompted_pass")
        mock_getpass.assert_called_once()

    @patch("getpass.getpass", side_effect=EOFError)
    def test_resolve_password_prompt_eof(self, mock_getpass):
        with self.assertRaises(ValueError):
            self.cli._resolve_password(None)

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_run_no_recordings_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = []
        mock_client_cls.return_value = mock_client

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(exit_code, 0)

    @patch("amcrest_downloader.cli.RecordingDownloader")
    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_run_download_none_succeeded(self, mock_client_cls, mock_downloader_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = [
            Recording(
                start_time=datetime(2026, 1, 16, 8, 0, 0),
                end_time=datetime(2026, 1, 16, 8, 15, 0),
                file_path=Path("/mnt/sd/test1.mp4"),
                file_size=1024,
            )
        ]
        mock_client_cls.return_value = mock_client

        mock_downloader = MagicMock()
        mock_downloader.download_all.return_value = []
        mock_downloader_cls.return_value = mock_downloader

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(exit_code, 1)

    @patch("amcrest_downloader.cli.VideoMerger")
    @patch("amcrest_downloader.cli.RecordingDownloader")
    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_run_merge_failure(self, mock_client_cls, mock_downloader_cls, mock_merger_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = [
            Recording(
                start_time=datetime(2026, 1, 16, 8, 0, 0),
                end_time=datetime(2026, 1, 16, 8, 15, 0),
                file_path=Path("/mnt/sd/test1.mp4"),
                file_size=1024,
            )
        ]
        mock_client_cls.return_value = mock_client

        mock_downloader = MagicMock()
        mock_downloader.download_all.return_value = [self.temp_dir / "rec1.mp4"]
        mock_downloader_cls.return_value = mock_downloader

        mock_merger = MagicMock()
        mock_merger.merge.return_value = False
        mock_merger_cls.return_value = mock_merger

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
                "--output-dir",
                str(self.temp_dir),
            ]
        )
        self.assertEqual(exit_code, 1)

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_run_unhandled_exception(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = RuntimeError("Fatal hardware failure")
        mock_client_cls.return_value = mock_client

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
            ]
        )
        self.assertEqual(exit_code, 1)

    @patch("amcrest_downloader.cli.VideoMerger")
    @patch("amcrest_downloader.cli.RecordingDownloader")
    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_output_format_inferred_from_output_file(
        self, mock_client_cls, mock_downloader_cls, mock_merger_cls
    ):
        mock_merger_cls.SUPPORTED_FORMATS = {"mp4", "mkv", "avi", "mov", "ts"}
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = [
            Recording(
                start_time=datetime(2026, 1, 16, 8, 0, 0),
                end_time=datetime(2026, 1, 16, 8, 15, 0),
                file_path=Path("/mnt/sd/test1.mp4"),
                file_size=1024,
            )
        ]
        mock_client_cls.return_value = mock_client

        mock_downloader = MagicMock()
        mock_downloader.download_all.return_value = [self.temp_dir / "rec1.mp4"]
        mock_downloader_cls.return_value = mock_downloader

        mock_merger = MagicMock()
        mock_merger.merge.return_value = True
        mock_merger_cls.return_value = mock_merger

        exit_code = self.cli.run(
            [
                "--host",
                "192.168.1.100",
                "--username",
                "admin",
                "--password",
                "pass",
                "--start",
                "2026-01-16T08:00:00",
                "--end",
                "2026-01-16T09:00:00",
                "--output-dir",
                str(self.temp_dir),
                "--output-file",
                "final_video.mkv",
            ]
        )
        self.assertEqual(exit_code, 0)
        mock_merger_cls.assert_called_with("mkv")

    def _rec(self):
        return Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/test1.mp4"),
            file_size=1024,
        )

    def _enable_logging(self):
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable, logging.CRITICAL)

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_fatal_error_prints_one_error_line_and_no_traceback(self, mock_client_cls):
        self._enable_logging()
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = RuntimeError("Fatal hardware failure")
        mock_client_cls.return_value = mock_client

        self.assertEqual(self.cli.run(self._base_args()), 1)
        lines = self.mock_stderr.getvalue().splitlines()
        self.assertEqual(
            [x for x in lines if "Fatal hardware failure" in x], ["Error: Fatal hardware failure"]
        )
        self.assertNotIn("Traceback", self.mock_stderr.getvalue())

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_auth_error_prints_one_error_line(self, mock_client_cls):
        self._enable_logging()
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = AmcrestAuthError("bad credentials")
        mock_client_cls.return_value = mock_client

        self.assertEqual(self.cli.run(self._base_args()), 1)
        lines = self.mock_stderr.getvalue().splitlines()
        self.assertEqual([x for x in lines if "bad credentials" in x], ["Error: bad credentials"])

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_fatal_error_traceback_logged_at_debug(self, mock_client_cls):
        self._enable_logging()
        mock_client = MagicMock()
        mock_client.__enter__.side_effect = RuntimeError("Fatal hardware failure")
        mock_client_cls.return_value = mock_client

        self.assertEqual(self.cli.run(self._base_args("--log-level", "debug")), 1)
        self.assertIn("Traceback", self.mock_stderr.getvalue())

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_aware_inputs_for_same_instant_produce_identical_queries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = []
        mock_client.current_time.side_effect = lambda: (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=8)
        )
        mock_client_cls.return_value = mock_client

        queries = []
        for start, end in (
            ("2026-01-16T08:00:00-08:00", "2026-01-16T10:00:00-08:00"),
            ("2026-01-16T16:00:00+00:00", "2026-01-16T18:00:00+00:00"),
        ):
            args = self._base_args()
            args[args.index("--start") + 1] = start
            args[args.index("--end") + 1] = end
            self.assertEqual(self.cli.run(args), 0)
            time_range = mock_client.find_recordings.call_args.args[0]
            queries.append(time_range.to_amcrest_format())

        self.assertEqual(queries[0], queries[1])
        self.assertEqual(queries[0], ("2026-01-16 08:00:00", "2026-01-16 10:00:00"))

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_naive_inputs_do_not_query_camera_time(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = []
        mock_client_cls.return_value = mock_client

        self.assertEqual(self.cli.run(self._base_args()), 0)
        mock_client.current_time.assert_not_called()

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_missing_ffmpeg_fails_before_searching(self, mock_client_cls):
        with patch("amcrest_downloader.cli.shutil.which", return_value=None):
            self.assertEqual(self.cli.run(self._base_args()), 1)
        self.assertIn(
            "Error: ffmpeg not found. Please install ffmpeg.", self.mock_stderr.getvalue()
        )
        mock_client_cls.assert_not_called()

    @patch("amcrest_downloader.cli.AmcrestClient")
    def test_missing_ffmpeg_allowed_for_list_only(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.find_recordings.return_value = [self._rec()]
        mock_client_cls.return_value = mock_client

        with patch("amcrest_downloader.cli.shutil.which", return_value=None):
            self.assertEqual(self.cli.run(self._base_args("--list-only")), 0)

    def _run_with_failing_download(self, download_all, *extra):
        with (
            patch("amcrest_downloader.cli.AmcrestClient") as mock_client_cls,
            patch("amcrest_downloader.cli.RecordingDownloader") as mock_downloader_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.find_recordings.return_value = [self._rec()]
            mock_client_cls.return_value = mock_client
            mock_downloader_cls.return_value.download_all.side_effect = download_all
            return self.cli.run(self._base_args("--output-dir", str(self.temp_dir), *extra))

    def test_work_dir_removed_when_download_raises(self):
        def download_all(recordings, work_dir, progress_callback=None):
            work_dir.mkdir(parents=True)
            (work_dir / "partial.mp4").write_text("data")
            raise AmcrestAuthError("bad credentials")

        self.assertEqual(self._run_with_failing_download(download_all), 1)
        self.assertFalse((self.temp_dir / ".amcrest_download").exists())

    def test_work_dir_removed_when_nothing_downloaded(self):
        def download_all(recordings, work_dir, progress_callback=None):
            work_dir.mkdir(parents=True)
            return []

        self.assertEqual(self._run_with_failing_download(download_all), 1)
        self.assertFalse((self.temp_dir / ".amcrest_download").exists())

    def test_work_dir_kept_with_keep_files_when_download_raises(self):
        def download_all(recordings, work_dir, progress_callback=None):
            work_dir.mkdir(parents=True)
            raise RuntimeError("boom")

        self.assertEqual(self._run_with_failing_download(download_all, "--keep-files"), 1)
        self.assertTrue((self.temp_dir / ".amcrest_download").exists())

    def _run_with_merge(self, merge_result, downloaded=1, found=1, *extra):
        def download_all(recordings, work_dir, progress_callback=None):
            work_dir.mkdir(parents=True)
            return [work_dir / f"seg{i}.mp4" for i in range(downloaded)]

        with (
            patch("amcrest_downloader.cli.AmcrestClient") as mock_client_cls,
            patch("amcrest_downloader.cli.RecordingDownloader") as mock_downloader_cls,
            patch("amcrest_downloader.cli.VideoMerger") as mock_merger_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.find_recordings.return_value = [self._rec()] * found
            mock_client_cls.return_value = mock_client
            mock_downloader_cls.return_value.download_all.side_effect = download_all
            if isinstance(merge_result, Exception):
                mock_merger_cls.return_value.merge.side_effect = merge_result
            else:
                mock_merger_cls.return_value.merge.return_value = merge_result
            return self.cli.run(self._base_args("--output-dir", str(self.temp_dir), *extra))

    def test_work_dir_removed_when_merge_succeeds(self):
        self.assertEqual(self._run_with_merge(True), 0)
        self.assertFalse((self.temp_dir / ".amcrest_download").exists())

    def test_work_dir_kept_when_merge_returns_false(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            self.assertEqual(self._run_with_merge(False), 1)
        work_dir = self.temp_dir / ".amcrest_download"
        self.assertTrue(work_dir.exists())
        self.assertIn(f"Merge failed; segments kept in {work_dir}", stderr.getvalue())

    def test_work_dir_kept_when_merge_raises(self):
        self.assertEqual(self._run_with_merge(RuntimeError("ffmpeg died")), 1)
        self.assertTrue((self.temp_dir / ".amcrest_download").exists())

    def test_partial_download_exits_1_but_merges(self):
        self.assertEqual(self._run_with_merge(True, downloaded=1, found=2), 1)

    def test_work_dir_removed_on_keyboard_interrupt(self):
        def download_all(recordings, work_dir, progress_callback=None):
            work_dir.mkdir(parents=True)
            raise KeyboardInterrupt

        self.assertEqual(self._run_with_failing_download(download_all), 130)
        self.assertFalse((self.temp_dir / ".amcrest_download").exists())


class TestConfigureLogging(unittest.TestCase):
    def tearDown(self):
        for handler in logging.getLogger().handlers:
            handler.close()
        logging.getLogger().handlers = []

    def test_configure_logging_console(self):
        configure_logging("info")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.INFO)
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in root.handlers))

    def test_configure_logging_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            configure_logging("debug", log_file=log_file)
            root = logging.getLogger()
            self.assertEqual(root.level, logging.DEBUG)
            self.assertTrue(any(isinstance(h, logging.FileHandler) for h in root.handlers))
            logging.getLogger().handlers[0].close()


class TestMain(unittest.TestCase):
    @patch("amcrest_downloader.cli.CLI")
    def test_main_delegates_to_cli_run(self, mock_cli_cls):
        mock_cli_cls.return_value.run.return_value = 0
        self.assertEqual(main(["--help"]), 0)
        mock_cli_cls.return_value.run.assert_called_once_with(["--help"])

    def test_version_flag(self):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(CLI().run(["--version"]), 0)
        self.assertIn("amcrest-downloader", out.getvalue())


if __name__ == "__main__":
    unittest.main()
