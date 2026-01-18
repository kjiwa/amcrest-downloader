from pathlib import Path
from typing import Optional
from datetime import datetime
from urllib.parse import urlencode, quote
import requests
from requests.auth import HTTPDigestAuth

from models import Recording, TimeRange


class AmcrestClient:
    DEFAULT_TIMEOUT = 10
    SEARCH_TIMEOUT = 30
    DOWNLOAD_TIMEOUT = 60
    BATCH_SIZE = 100
    CHUNK_SIZE = 8192

    def __init__(self, host: str, username: str, password: str):
        self._host = host.rstrip("/")
        self._auth = HTTPDigestAuth(username, password)
        self._session = requests.Session()
        self._session.auth = self._auth

    def _build_url(self, endpoint: str, params: dict = None) -> str:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        url = f"http://{self._host}{endpoint}"

        if params:
            encoded_params = urlencode(params, quote_via=quote, safe="")
            url = f"{url}?{encoded_params}"

        return url

    def _get(
        self, endpoint: str, params: dict = None, timeout: int = None
    ) -> requests.Response:
        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT
        url = self._build_url(endpoint, params)
        response = self._session.get(url, timeout=timeout)
        response.raise_for_status()
        return response

    def find_recordings(
        self, time_range: TimeRange, channel: int = 0
    ) -> list[Recording]:
        start_str, end_str = time_range.to_amcrest_format()

        params = {"action": "factory.create"}
        response = self._get("/cgi-bin/mediaFileFind.cgi", params=params)

        object_id = self._parse_object_id(response.text)
        if not object_id:
            raise RuntimeError("Failed to create media file finder")

        return self._fetch_recordings(object_id, start_str, end_str, channel)

    def _parse_object_id(self, response_text: str) -> Optional[str]:
        for line in response_text.splitlines():
            if line.startswith("result="):
                return line.split("=", 1)[1].strip()
        return None

    def _fetch_recordings(
        self, object_id: str, start_time: str, end_time: str, channel: int
    ) -> list[Recording]:
        self._initiate_search(object_id, start_time, end_time, channel)
        recordings = self._collect_all_batches(object_id)
        self._close_finder(object_id)
        return recordings

    def _initiate_search(
        self, object_id: str, start_time: str, end_time: str, channel: int
    ) -> None:
        params = {
            "action": "findFile",
            "object": object_id,
            "condition.Channel": channel,
            "condition.StartTime": start_time,
            "condition.EndTime": end_time,
        }
        response = self._get(
            "/cgi-bin/mediaFileFind.cgi", params=params, timeout=self.SEARCH_TIMEOUT
        )
        self._validate_search_response(response.text, object_id)

    def _validate_search_response(self, response_text: str, object_id: str) -> None:
        if "ok" not in response_text.lower():
            self._close_finder(object_id)
            raise RuntimeError(f"Search failed: {response_text}")

    def _collect_all_batches(self, object_id: str) -> list[Recording]:
        recordings = []
        while True:
            next_response = self._fetch_next_batch(object_id)
            if not next_response:
                break

            batch_recordings = self._parse_recordings(next_response)
            if not batch_recordings:
                break

            recordings.extend(batch_recordings)
        return recordings

    def _fetch_next_batch(self, object_id: str) -> str:
        params = {
            "action": "findNextFile",
            "object": object_id,
            "count": self.BATCH_SIZE,
        }
        response = self._get(
            "/cgi-bin/mediaFileFind.cgi", params=params, timeout=self.SEARCH_TIMEOUT
        )

        lines = response.text.split("\n", 1)
        if not lines:
            return ""

        first_line = lines[0].strip()
        if not first_line.startswith("found="):
            return ""

        count_str = first_line.split("=", 1)[1]
        try:
            file_count = int(count_str)
            if file_count == 0:
                return ""
        except ValueError:
            return ""

        return response.text

    def _parse_recordings(self, response_text: str) -> list[Recording]:
        recordings = []
        current_file = {}

        for line in response_text.splitlines():
            line = line.strip()
            if not line or line.startswith("found="):
                continue

            if line.startswith("items[") and self._is_complete_recording(current_file):
                try:
                    recording = self._create_recording(current_file)
                    if self._should_include_recording(recording):
                        recordings.append(recording)
                except Exception:
                    pass
                current_file = {}

            key, value = self._parse_recording_line(line)
            if key:
                current_file[key] = value

        if self._is_complete_recording(current_file):
            try:
                recording = self._create_recording(current_file)
                if self._should_include_recording(recording):
                    recordings.append(recording)
            except Exception:
                pass

        return recordings

    def _parse_recording_line(self, line: str) -> tuple[Optional[str], Optional[str]]:
        if ".FilePath=" in line:
            return "FilePath", line.split("=", 1)[1]
        elif ".StartTime=" in line:
            return "StartTime", line.split("=", 1)[1]
        elif ".EndTime=" in line:
            return "EndTime", line.split("=", 1)[1]
        elif ".Channel=" in line:
            return "Channel", int(line.split("=", 1)[1])
        return None, None

    def _is_complete_recording(self, file_data: dict) -> bool:
        return "FilePath" in file_data and "StartTime" in file_data

    def _should_include_recording(self, recording: Recording) -> bool:
        return ".mp4" in str(recording.file_path)

    def _create_recording(self, file_data: dict) -> Recording:
        start_time = datetime.strptime(file_data["StartTime"], "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(file_data["EndTime"], "%Y-%m-%d %H:%M:%S")

        file_path = Path(file_data["FilePath"])
        channel = file_data.get("Channel", 0)

        return Recording(
            start_time=start_time,
            end_time=end_time,
            file_path=file_path,
            channel=channel,
        )

    def _close_finder(self, object_id: str):
        params = {
            "action": "destroy",
            "object": object_id,
        }
        try:
            self._get("/cgi-bin/mediaFileFind.cgi", params=params)
        except Exception:
            pass

    def download_recording(self, recording: Recording, output_path: Path) -> bool:
        file_path = str(recording.file_path)
        endpoint = f"/cgi-bin/RPC_Loadfile{file_path}"
        url = self._build_url(endpoint)

        try:
            response = self._session.get(
                url, stream=True, timeout=self.DOWNLOAD_TIMEOUT
            )
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)

            return True
        except Exception as e:
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError(f"Failed to download recording: {e}")

    def close(self):
        self._session.close()
