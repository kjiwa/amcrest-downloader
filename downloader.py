from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from amcrest_api import AmcrestClient
from models import Recording


class RecordingDownloader:
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
        downloaded_files = []

        with ThreadPoolExecutor(max_workers=self._max_concurrent) as executor:
            futures = {}

            for idx, recording in enumerate(recordings):
                output_file = self._generate_filename(recording, output_dir, idx)
                future = executor.submit(
                    self._download_with_retry, recording, output_file
                )
                futures[future] = (recording, output_file)

            completed = 0
            total = len(recordings)

            for future in as_completed(futures):
                recording, output_file = futures[future]

                try:
                    success = future.result()
                    if success:
                        downloaded_files.append(output_file)
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

                except Exception:
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

        downloaded_files.sort()
        return downloaded_files

    def _generate_filename(
        self, recording: Recording, output_dir: Path, index: int
    ) -> Path:
        timestamp = recording.start_time.strftime("%Y%m%d_%H%M%S")
        return output_dir / f"recording_{index:04d}_{timestamp}.mp4"

    def _download_with_retry(
        self, recording: Recording, output_path: Path, max_retries: int = 3
    ) -> bool:
        for attempt in range(max_retries):
            try:
                return self._client.download_recording(recording, output_path)
            except Exception:
                if attempt == max_retries - 1:
                    raise

        return False
