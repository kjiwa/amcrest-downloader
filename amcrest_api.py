import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode, urlsplit
import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPDigestAuth

from logger import get_logger
from models import Recording, TimeRange


class AmcrestClient:
    DEFAULT_TIMEOUT = 10
    SEARCH_TIMEOUT = 30
    DOWNLOAD_TIMEOUT = 60
    BATCH_SIZE = 100
    CHUNK_SIZE = 8192
    SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".dav", ".mkv", ".avi", ".asf", ".264"}

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: Optional[int] = None,
        ssl: bool = False,
        verify_ssl: bool = True,
        max_connections: int = 10,
    ):
        self._base_url = self._format_base_url(host, port, ssl)
        self._auth = HTTPDigestAuth(username, password)
        self._verify_ssl = verify_ssl
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.verify = verify_ssl

        adapter = HTTPAdapter(
            pool_connections=max_connections,
            pool_maxsize=max_connections,
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        self._logger = get_logger(__name__)

    def __enter__(self) -> "AmcrestClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _format_base_url(self, host: str, port: Optional[int], ssl: bool) -> str:
        clean_host = host.strip()
        if clean_host.startswith(("http://", "https://")):
            parsed = urlsplit(clean_host)
            scheme = parsed.scheme
            hostname = parsed.hostname or ""
            target_port = port if port is not None else parsed.port
        else:
            scheme = "https" if ssl else "http"
            if clean_host.startswith("[") and "]" in clean_host:
                bracket_end = clean_host.index("]")
                hostname = clean_host[1:bracket_end]
                remainder = clean_host[bracket_end + 1 :]
                if remainder.startswith(":"):
                    target_port = port if port is not None else int(remainder[1:])
                else:
                    target_port = port
            elif clean_host.count(":") > 1:
                hostname = clean_host
                target_port = port
            elif ":" in clean_host:
                parts = clean_host.split(":", 1)
                hostname = parts[0]
                target_port = port if port is not None else int(parts[1])
            else:
                hostname = clean_host
                target_port = port

        host_str = (
            f"[{hostname}]"
            if ":" in hostname and not hostname.startswith("[")
            else hostname
        )

        if target_port:
            return f"{scheme}://{host_str}:{target_port}"
        return f"{scheme}://{host_str}"

    def _build_url(self, endpoint: str, params: Optional[dict] = None) -> str:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"

        url = f"{self._base_url}{endpoint}"
        if params:
            encoded_params = urlencode(params, quote_via=quote, safe=":")
            url = f"{url}?{encoded_params}"

        return url

    def _get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        timeout: Optional[int] = None,
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
        finder_id = self._create_finder()
        try:
            if not self._start_search(finder_id, start_str, end_str, channel):
                return []
            recordings = self._retrieve_all_results(finder_id)
            return sorted(recordings)
        finally:
            self._close_finder(finder_id)
            self._destroy_finder(finder_id)

    def _create_finder(self) -> str:
        self._logger.debug("Creating media file finder")
        params = {"action": "factory.create"}
        response = self._get("/cgi-bin/mediaFileFind.cgi", params=params)

        object_id = self._parse_object_id(response.text)
        if not object_id:
            self._logger.error(
                "Failed to create media file finder: no object ID returned"
            )
            raise RuntimeError("Failed to create media file finder")

        self._logger.debug(f"Created finder with ID: {object_id}")
        return object_id

    def _parse_object_id(self, response_text: str) -> Optional[str]:
        for line in response_text.splitlines():
            line = line.strip()
            if line.startswith("result="):
                return line.split("=", 1)[1].strip()
        return None

    def _start_search(
        self, finder_id: str, start_time: str, end_time: str, channel: int
    ) -> bool:
        self._logger.info(
            f"Starting search: channel={channel}, start={start_time}, end={end_time}"
        )
        params = {
            "action": "findFile",
            "object": finder_id,
            "condition.Channel": channel + 1,
            "condition.StartTime": start_time,
            "condition.EndTime": end_time,
        }
        try:
            response = self._get(
                "/cgi-bin/mediaFileFind.cgi", params=params, timeout=self.SEARCH_TIMEOUT
            )
            return "ok" in response.text.lower()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                self._logger.debug(
                    f"Search returned HTTP 400 (no recordings found): {e}"
                )
                return False
            raise


    def _retrieve_all_results(self, finder_id: str) -> list[Recording]:
        recordings: list[Recording] = []
        batch_num = 0

        while True:
            batch_text, file_count = self._fetch_next_batch(finder_id)
            if file_count == 0 or not batch_text:
                break

            batch_num += 1
            batch_recordings = self._parse_recordings(batch_text)
            self._logger.debug(
                f"Retrieved batch {batch_num} ({file_count} raw items, {len(batch_recordings)} video recordings)"
            )
            recordings.extend(batch_recordings)

        self._logger.info(
            f"Search completed: found {len(recordings)} recordings across {batch_num} batches"
        )
        return recordings

    def _fetch_next_batch(self, finder_id: str) -> tuple[str, int]:
        params = {
            "action": "findNextFile",
            "object": finder_id,
            "count": self.BATCH_SIZE,
        }
        response = self._get(
            "/cgi-bin/mediaFileFind.cgi", params=params, timeout=self.SEARCH_TIMEOUT
        )

        for line in response.text.splitlines():
            clean_line = line.strip()
            if clean_line.startswith("found="):
                count_str = clean_line.split("=", 1)[1].strip()
                try:
                    return response.text, int(count_str)
                except ValueError:
                    return "", 0

        return "", 0

    def _parse_recordings(self, response_text: str) -> list[Recording]:
        item_pattern = re.compile(r"^items\[(\d+)\]\.(.+?)=(.*)$")
        raw_items: dict[int, dict[str, str]] = {}

        for line in response_text.splitlines():
            match = item_pattern.match(line.strip())
            if not match:
                continue
            idx = int(match.group(1))
            key = match.group(2)
            val = match.group(3)
            if idx not in raw_items:
                raw_items[idx] = {}
            raw_items[idx][key] = val

        recordings: list[Recording] = []
        for idx in sorted(raw_items.keys()):
            recording = self._create_recording(raw_items[idx])
            if recording:
                recordings.append(recording)

        return recordings

    def _create_recording(self, file_data: dict[str, str]) -> Optional[Recording]:
        if "FilePath" not in file_data or "StartTime" not in file_data or "EndTime" not in file_data:
            return None

        file_path = Path(file_data["FilePath"])
        if file_path.suffix.lower() not in self.SUPPORTED_VIDEO_EXTENSIONS:
            return None

        try:
            start_time = datetime.strptime(file_data["StartTime"], "%Y-%m-%d %H:%M:%S")
            end_time = datetime.strptime(file_data["EndTime"], "%Y-%m-%d %H:%M:%S")
            file_size = int(file_data.get("Length", 0))
            channel = int(file_data.get("Channel", 0))

            return Recording(
                start_time=start_time,
                end_time=end_time,
                file_path=file_path,
                file_size=file_size,
                channel=channel,
            )
        except Exception as e:
            self._logger.warning(
                f"Failed to parse recording item {file_data}: {e}"
            )
            return None

    def _close_finder(self, finder_id: str) -> None:
        self._logger.debug(f"Closing finder with ID: {finder_id}")
        params = {
            "action": "close",
            "object": finder_id,
        }
        try:
            self._get("/cgi-bin/mediaFileFind.cgi", params=params)
            self._logger.debug(f"Successfully closed finder {finder_id}")
        except Exception as e:
            self._logger.warning(f"Failed to close finder {finder_id}: {e}")

    def _destroy_finder(self, finder_id: str) -> None:
        self._logger.debug(f"Destroying finder with ID: {finder_id}")
        params = {
            "action": "destroy",
            "object": finder_id,
        }
        try:
            self._get("/cgi-bin/mediaFileFind.cgi", params=params)
            self._logger.debug(f"Successfully destroyed finder {finder_id}")
        except Exception as e:
            self._logger.warning(f"Failed to destroy finder {finder_id}: {e}")

    def download_recording(self, recording: Recording, output_path: Path) -> bool:
        self._logger.debug(f"Starting download: {recording.file_path} -> {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = output_path.with_name(f"{output_path.name}.part")

        endpoint = f"/cgi-bin/RPC_Loadfile{str(recording.file_path)}"
        url = self._build_url(endpoint)

        try:
            self._stream_to_file(url, part_path)
            part_path.replace(output_path)
            self._logger.info(f"Successfully downloaded: {output_path.name}")
            return True
        except Exception as e:
            if part_path.exists():
                part_path.unlink()
            self._logger.error(f"Download failed for {recording.file_path}: {e}")
            raise RuntimeError(f"Failed to download recording: {e}")

    def _stream_to_file(self, url: str, local_path: Path) -> None:
        response = self._session.get(url, stream=True, timeout=self.DOWNLOAD_TIMEOUT)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                if chunk:
                    f.write(chunk)

    def close(self) -> None:
        self._session.close()

