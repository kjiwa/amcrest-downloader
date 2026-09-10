import subprocess
import tempfile
from pathlib import Path
from typing import Optional

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
            if not success and self._output_format == "mp4":
                self._logger.warning(
                    "Direct stream copy failed for MP4; retrying with audio transcode to AAC"
                )
                success = self._execute_ffmpeg(
                    concat_file, output_file, audio_codec="aac"
                )

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
        abs_str = str(path.resolve()).replace("\\", "\\\\").replace("'", "'\\''")
        return abs_str

    def _create_concat_file(self, input_files: list[Path]) -> Path:
        parent_dir = input_files[0].parent
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            prefix="concat_",
            dir=parent_dir,
            delete=False,
        ) as f:
            for file_path in input_files:
                escaped = self._escape_path(file_path)
                f.write(f"file '{escaped}'\n")
            concat_path = Path(f.name)

        self._logger.debug(f"Creating concat file: {concat_path}")
        return concat_path

    def _execute_ffmpeg(
        self,
        concat_file: Path,
        output_file: Path,
        audio_codec: Optional[str] = None,
    ) -> bool:
        cmd = [
            "ffmpeg",
            "-fflags",
            "+genpts",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
        ]
        if audio_codec:
            cmd.extend(["-c:v", "copy", "-c:a", audio_codec])
        else:
            cmd.extend(["-c", "copy"])

        cmd.extend(["-avoid_negative_ts", "make_zero", "-y", str(output_file)])

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


