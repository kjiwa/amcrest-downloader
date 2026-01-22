import subprocess
from pathlib import Path

from logger import get_logger


class VideoMerger:
    SUPPORTED_FORMATS = {"mp4", "mkv", "avi"}

    def __init__(self, output_format: str = "mp4"):
        if output_format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {output_format}")
        self._output_format = output_format
        self._logger = get_logger(__name__)

    def merge(
        self, input_files: list[Path], output_file: Path, cleanup: bool = True
    ) -> bool:
        if not input_files:
            raise ValueError("No input files to merge")

        self._logger.info(
            f"Starting merge of {len(input_files)} files to {output_file}"
        )
        concat_file = self._create_concat_file(input_files)
        try:
            success = self._execute_ffmpeg(concat_file, output_file)
            if success:
                self._logger.info(f"Merge completed successfully: {output_file}")
                if cleanup:
                    self._cleanup_files(input_files, concat_file)
            else:
                self._logger.error(f"Merge failed for {output_file}")
                if not cleanup:
                    concat_file.unlink()

            if not cleanup and success:
                concat_file.unlink()

            return success

        except Exception as e:
            self._logger.error(f"Merge error: {e}")
            concat_file.unlink()
            raise RuntimeError(f"Merge failed: {e}")

    def _create_concat_file(self, input_files: list[Path]) -> Path:
        concat_file = input_files[0].parent / "concat_list.txt"
        self._logger.debug(f"Creating concat file: {concat_file}")
        with open(concat_file, "w") as f:
            for file_path in input_files:
                abs_path = file_path.resolve()
                f.write(f"file '{abs_path}'\n")

        return concat_file

    def _execute_ffmpeg(self, concat_file: Path, output_file: Path) -> bool:
        cmd = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-y",
            str(output_file),
        ]

        self._logger.debug(f"Executing ffmpeg command: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            self._logger.error(f"FFmpeg error (exit code {e.returncode}): {e.stderr}")
            print(f"FFmpeg error: {e.stderr}")
            return False
        except FileNotFoundError:
            self._logger.error("ffmpeg not found in PATH")
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")

    def _cleanup_files(self, input_files: list[Path], concat_file: Path):
        self._logger.debug(f"Cleaning up {len(input_files)} input files")
        for file_path in input_files:
            try:
                file_path.unlink()
            except Exception as e:
                self._logger.warning(f"Could not delete {file_path}: {e}")
                print(f"Warning: Could not delete {file_path}: {e}")

        try:
            concat_file.unlink()
        except Exception as e:
            self._logger.warning(f"Could not delete concat file {concat_file}: {e}")
