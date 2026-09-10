import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from downloader import RecordingDownloader
from models import Recording
from amcrest_api import AmcrestAuthError


class TestRecordingDownloader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_client = MagicMock()
        self.downloader = RecordingDownloader(self.mock_client, max_concurrent=2)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_download_all_empty(self):
        results = self.downloader.download_all([], self.temp_dir)
        self.assertEqual(results, [])

    def test_download_all_success(self):
        rec1 = Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/test1.mp4"),
        )
        rec2 = Recording(
            start_time=datetime(2026, 1, 16, 8, 15, 0),
            end_time=datetime(2026, 1, 16, 8, 30, 0),
            file_path=Path("/mnt/sd/test2.mp4"),
        )

        def mock_download(recording, output_path):
            output_path.write_text("fake video content")
            return True

        self.mock_client.download_recording.side_effect = mock_download

        progress_calls = []
        downloaded = self.downloader.download_all(
            [rec1, rec2],
            self.temp_dir,
            progress_callback=lambda c, t: progress_calls.append((c, t)),
        )

        self.assertEqual(len(downloaded), 2)
        self.assertEqual(len(progress_calls), 2)
        self.assertEqual(progress_calls[-1], (2, 2))

    def test_download_all_preserves_chronological_order(self):
        rec_late = Recording(
            start_time=datetime(2026, 1, 16, 9, 0, 0),
            end_time=datetime(2026, 1, 16, 9, 15, 0),
            file_path=Path("/mnt/sd/late.mp4"),
        )
        rec_early = Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/early.mp4"),
        )

        created_files = []

        def mock_download(recording, output_path):
            created_files.append((recording, output_path))
            output_path.write_text("data")
            return True

        self.mock_client.download_recording.side_effect = mock_download
        downloaded = self.downloader.download_all([rec_late, rec_early], self.temp_dir)

        self.assertEqual(len(downloaded), 2)
        early_call = [p for r, p in created_files if r == rec_early][0]
        late_call = [p for r, p in created_files if r == rec_late][0]
        self.assertIn("recording_0000_", early_call.name)
        self.assertIn("recording_0001_", late_call.name)

    @patch("time.sleep")
    def test_download_retry_with_backoff(self, mock_sleep):
        rec = Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/test1.mp4"),
        )

        attempts = 0

        def mock_download(recording, output_path):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("Network glitch")
            output_path.write_text("success")
            return True

        self.mock_client.download_recording.side_effect = mock_download
        dest = self.temp_dir / "out.mp4"
        success = self.downloader._download_with_retry(rec, dest)

        self.assertTrue(success)
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("time.sleep")
    def test_download_auth_error_not_retried(self, mock_sleep):
        rec = Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/test1.mp4"),
        )
        self.mock_client.download_recording.side_effect = AmcrestAuthError("Unauthorized")
        dest = self.temp_dir / "out.mp4"
        with self.assertRaises(AmcrestAuthError):
            self.downloader._download_with_retry(rec, dest)
        mock_sleep.assert_not_called()
        self.assertEqual(self.mock_client.download_recording.call_count, 1)


if __name__ == "__main__":
    unittest.main()
