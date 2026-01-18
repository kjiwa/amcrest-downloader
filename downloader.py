from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from amcrest_api import AmcrestClient
from models import Recording


class RecordingDownloader:
    DEFAULT_MAX_RETRIES = 3

    def __init__(self, client: AmcrestClient, max_concurrent: int = 4):
        self._client = client
        self._max_concurrent = max_concurrent

    def download_all(
        self,
        recordings: list[Recording],
        output_dir: Path,
        progress_callback: Callable[[int, int], None] = None,
    ) -> list[Path]:
        if not recordings:
            return []

        output_dir.mkdir(parents=True, exist_ok=True)

        futures = self._submit_download_tasks(recordings, output_dir)
        downloaded_files = self._await_completion(futures, progress_callback)

        return sorted(downloaded_files)

    def _submit_download_tasks(
        self, recordings: list[Recording], output_dir: Path
    ) -> dict:
        executor = ThreadPoolExecutor(max_workers=self._max_concurrent)
        futures = {}

        for idx, recording in enumerate(recordings):
            output_file = self._generate_filename(recording, output_dir, idx)
            future = executor.submit(self._download_with_retry, recording, output_file)
            futures[future] = (recording, output_file, executor)

        return futures

    def _await_completion(
        self, futures: dict, progress_callback: Callable[[int, int], None]
    ) -> list[Path]:
        downloaded_files = []
        completed = 0
        total = len(futures)
        executor = None

        try:
            for future in as_completed(futures):
                recording, output_file, executor = futures[future]

                try:
                    success = self._handle_download_result(future)
                    if success:
                        downloaded_files.append(output_file)
                except Exception:
                    pass

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
        finally:
            if executor:
                executor.shutdown(wait=True)

        return downloaded_files

    def _handle_download_result(self, future) -> bool:
        return future.result()

    def _generate_filename(
        self, recording: Recording, output_dir: Path, index: int
    ) -> Path:
        timestamp = recording.start_time.strftime("%Y%m%d_%H%M%S")
        return output_dir / f"recording_{index:04d}_{timestamp}.mp4"

    def _download_with_retry(self, recording: Recording, output_path: Path) -> bool:
        for attempt in range(self.DEFAULT_MAX_RETRIES):
            try:
                return self._client.download_recording(recording, output_path)
            except Exception:
                if attempt == self.DEFAULT_MAX_RETRIES - 1:
                    raise

        return False
