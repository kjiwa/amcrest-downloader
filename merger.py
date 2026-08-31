import subprocess
from pathlib import Path

from logger import get_logger


class VideoMerger:
    SUPPORTED_FORMATS = {"mp4", "mkv", "avi", "mov", "ts"}

    def __init__(self, output_format: str = "mp4"):
        if output_format.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {output_format}")
        self._output_format = output_format.lower()
        self._logger = get_logger(__name__)

    def merge(
        self, input_files: list[Path], output_file: Path, cleanup: bool = True
    ) -> bool:
        if not input_files:
            raise ValueError("No input files to merge")

        self._logger.info(
            f"Starting merge of {len(input_files)} files to {output_file}"
        )
        self._prepare_output_file(output_file)
        concat_file = self._create_concat_file(input_files)

        try:
            success = self._execute_ffmpeg(concat_file, output_file)
            if success:
                self._logger.info(f"Merge completed successfully: {output_file}")
                if cleanup:
                    self._cleanup_files(input_files)
            else:
                self._logger.error(f"Merge failed for {output_file}")

            return success

        except Exception as e:
            self._logger.error(f"Merge error: {e}")
            raise
        finally:
            if concat_file.exists():
                try:
                    concat_file.unlink()
                except Exception as e:
                    self._logger.warning(f"Could not delete concat file {concat_file}: {e}")

    def _prepare_output_file(self, output_file: Path) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)

    def _escape_path(self, path: Path) -> str:
        abs_str = str(path.resolve())
        return abs_str.replace("'", "'\\''")

    def _create_concat_file(self, input_files: list[Path]) -> Path:
        concat_file = input_files[0].parent / "concat_list.txt"
        self._logger.debug(f"Creating concat file: {concat_file}")
        with open(concat_file, "w", encoding="utf-8") as f:
            for file_path in input_files:
                escaped = self._escape_path(file_path)
                f.write(f"file '{escaped}'\n")

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
            return False
        except FileNotFoundError:
            self._logger.error("ffmpeg not found in PATH")
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")

    def _cleanup_files(self, input_files: list[Path]) -> None:
        self._logger.debug(f"Cleaning up {len(input_files)} input files")
        for file_path in input_files:
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                self._logger.warning(f"Could not delete {file_path}: {e}")

