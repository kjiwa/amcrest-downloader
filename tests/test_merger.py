import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import subprocess

from merger import VideoMerger


class TestVideoMerger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.merger = VideoMerger("mp4")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unsupported_format(self):
        with self.assertRaises(ValueError):
            VideoMerger("flv")

    def test_empty_input_files_raises_error(self):
        with self.assertRaises(ValueError):
            self.merger.merge([], self.temp_dir / "out.mp4")

    def test_concat_file_escapes_single_quotes(self):
        special_dir = self.temp_dir / "user's directory"
        special_dir.mkdir()
        file1 = special_dir / "clip'1.mp4"
        file1.write_text("dummy")

        concat_file = self.merger._create_concat_file([file1])
        self.assertTrue(concat_file.exists())
        content = concat_file.read_text()
        self.assertIn("user'\\''s directory", content)
        self.assertIn("clip'\\''1.mp4", content)

    @patch("subprocess.run")
    def test_merge_success_cleans_up_input_files(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        file1 = self.temp_dir / "1.mp4"
        file2 = self.temp_dir / "2.mp4"
        file1.write_text("data1")
        file2.write_text("data2")
        output_file = self.temp_dir / "merged.mp4"

        success = self.merger.merge([file1, file2], output_file, cleanup=True)
        self.assertTrue(success)
        self.assertFalse(file1.exists())
        self.assertFalse(file2.exists())
        concat_files = list(self.temp_dir.glob("concat_*.txt"))
        self.assertEqual(concat_files, [])

    @patch("subprocess.run")
    def test_merge_failure_cleans_up_concat_file(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg", stderr="error")

        file1 = self.temp_dir / "1.mp4"
        file1.write_text("data1")
        output_file = self.temp_dir / "merged.mp4"

        success = self.merger.merge([file1], output_file, cleanup=True)
        self.assertFalse(success)
        self.assertTrue(file1.exists())  # input file kept on failure
        concat_files = list(self.temp_dir.glob("concat_*.txt"))
        self.assertEqual(concat_files, [])

    @patch("subprocess.run")
    def test_merge_fallback_to_aac_on_mp4_failure(self, mock_run):
        file1 = self.temp_dir / "1.mp4"
        file1.write_text("data1")
        output_file = self.temp_dir / "merged.mp4"

        mock_run.side_effect = [
            subprocess.CalledProcessError(
                1, "ffmpeg", stderr="Could not find tag for codec pcm_alaw"
            ),
            MagicMock(returncode=0),
        ]

        success = self.merger.merge([file1], output_file, cleanup=False)
        self.assertTrue(success)
        self.assertEqual(mock_run.call_count, 2)
        second_cmd = mock_run.call_args_list[1][0][0]
        self.assertIn("-c:a", second_cmd)
        self.assertIn("aac", second_cmd)

    @patch("subprocess.run")
    def test_merge_ffmpeg_missing_raises_runtime_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        file1 = self.temp_dir / "1.mp4"
        file1.write_text("data1")
        output_file = self.temp_dir / "merged.mp4"
        with self.assertRaises(RuntimeError):
            self.merger.merge([file1], output_file)


if __name__ == "__main__":
    unittest.main()
