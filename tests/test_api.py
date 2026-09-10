import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from pathlib import Path
import requests

from amcrest_api import AmcrestClient
from models import TimeRange, Recording


class TestAmcrestClientParsing(unittest.TestCase):
    def setUp(self):
        self.client = AmcrestClient("192.168.1.100", "admin", "password")

    def test_parse_object_id_valid(self):
        response_text = "result=12345\r\n"
        self.assertEqual(self.client._parse_object_id(response_text), "12345")

    def test_parse_object_id_missing(self):
        response_text = "error\r\n"
        self.assertIsNone(self.client._parse_object_id(response_text))

    def test_parse_recordings_out_of_order_fields(self):
        payload = (
            "found=1\n"
            "items[0].Channel=0\n"
            "items[0].StartTime=2026-01-16 08:00:00\n"
            "items[0].FilePath=/mnt/sd/test.mp4\n"
            "items[0].EndTime=2026-01-16 08:15:00\n"
            "items[0].Length=1048576\n"
        )
        recordings = self.client._parse_recordings(payload)
        self.assertEqual(len(recordings), 1)
        self.assertEqual(recordings[0].start_time, datetime(2026, 1, 16, 8, 0, 0))
        self.assertEqual(recordings[0].end_time, datetime(2026, 1, 16, 8, 15, 0))
        self.assertEqual(recordings[0].file_path, Path("/mnt/sd/test.mp4"))
        self.assertEqual(recordings[0].file_size, 1048576)

    def test_parse_recordings_multiple_items_mixed_types(self):
        payload = (
            "found=3\n"
            "items[0].Channel=0\n"
            "items[0].StartTime=2026-01-16 08:00:00\n"
            "items[0].EndTime=2026-01-16 08:15:00\n"
            "items[0].FilePath=/mnt/sd/001.mp4\n"
            "items[0].Length=1000\n"
            "items[1].Channel=0\n"
            "items[1].StartTime=2026-01-16 08:15:00\n"
            "items[1].EndTime=2026-01-16 08:15:05\n"
            "items[1].FilePath=/mnt/sd/001.jpg\n"
            "items[1].Length=500\n"
            "items[2].Channel=0\n"
            "items[2].StartTime=2026-01-16 08:15:00\n"
            "items[2].EndTime=2026-01-16 08:30:00\n"
            "items[2].FilePath=/mnt/sd/002.dav\n"
            "items[2].Length=2000\n"
        )
        recordings = self.client._parse_recordings(payload)
        self.assertEqual(len(recordings), 2)
        self.assertEqual(recordings[0].file_path, Path("/mnt/sd/001.mp4"))
        self.assertEqual(recordings[1].file_path, Path("/mnt/sd/002.dav"))

    def test_url_construction(self):
        c1 = AmcrestClient("192.168.1.50", "admin", "pass")
        self.assertEqual(c1._build_url("/cgi-bin/test.cgi"), "http://192.168.1.50/cgi-bin/test.cgi")

        c2 = AmcrestClient("http://192.168.1.50:8080", "admin", "pass")
        self.assertEqual(c2._build_url("cgi-bin/test.cgi"), "http://192.168.1.50:8080/cgi-bin/test.cgi")

        c3 = AmcrestClient("https://camera.local:8443/", "admin", "pass")
        self.assertEqual(c3._build_url("/cgi-bin/test.cgi"), "https://camera.local:8443/cgi-bin/test.cgi")

        c4 = AmcrestClient("camera.local", "admin", "pass", port=8000, ssl=True)
        self.assertEqual(c4._build_url("api"), "https://camera.local:8000/api")

    def test_url_construction_preserves_colons_in_query_params(self):
        c = AmcrestClient("192.168.1.50", "admin", "pass")
        params = {"condition.StartTime": "2026-09-09 19:00:00", "action": "findFile"}
        url = c._build_url("/cgi-bin/mediaFileFind.cgi", params=params)
        self.assertIn("condition.StartTime=2026-09-09%2019:00:00", url)
        self.assertNotIn("%3A", url)

    @patch.object(AmcrestClient, "_get")
    def test_start_search_maps_zero_based_channel_to_one_based(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = "OK\r\n"
        mock_get.return_value = mock_resp

        self.client._start_search(
            finder_id="123",
            start_time="2026-09-09 19:00:00",
            end_time="2026-09-09 20:00:00",
            channel=0,
        )
        mock_get.assert_called_once_with(
            "/cgi-bin/mediaFileFind.cgi",
            params={
                "action": "findFile",
                "object": "123",
                "condition.Channel": 1,
                "condition.StartTime": "2026-09-09 19:00:00",
                "condition.EndTime": "2026-09-09 20:00:00",
            },
            timeout=self.client.SEARCH_TIMEOUT,
        )

    @patch.object(AmcrestClient, "_get")
    def test_start_search_returns_false_on_http_400(self, mock_get):
        resp = MagicMock()
        resp.status_code = 400
        mock_get.side_effect = requests.exceptions.HTTPError(response=resp)

        result = self.client._start_search(
            finder_id="123",
            start_time="2026-09-09 19:00:00",
            end_time="2026-09-09 20:00:00",
            channel=0,
        )
        self.assertFalse(result)

    @patch.object(AmcrestClient, "_get")
    def test_start_search_returns_false_on_non_ok_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = "Error\r\n"
        mock_get.return_value = mock_resp

        result = self.client._start_search(
            finder_id="123",
            start_time="2026-09-09 19:00:00",
            end_time="2026-09-09 20:00:00",
            channel=0,
        )
        self.assertFalse(result)

    @patch.object(AmcrestClient, "_get")
    def test_start_search_reraises_non_400_http_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 500
        mock_get.side_effect = requests.exceptions.HTTPError(response=resp)

        with self.assertRaises(requests.exceptions.HTTPError):
            self.client._start_search(
                finder_id="123",
                start_time="2026-09-09 19:00:00",
                end_time="2026-09-09 20:00:00",
                channel=0,
            )

    @patch.object(AmcrestClient, "_get")
    def test_find_recordings_returns_empty_list_on_http_400(self, mock_get):
        create_resp = MagicMock(text="result=999\n")
        err_resp = MagicMock()
        err_resp.status_code = 400
        search_err = requests.exceptions.HTTPError(response=err_resp)
        close_resp = MagicMock(text="OK\n")
        destroy_resp = MagicMock(text="OK\n")

        mock_get.side_effect = [
            create_resp,
            search_err,
            close_resp,
            destroy_resp,
        ]

        tr = TimeRange(
            start=datetime(2026, 1, 16, 8, 0, 0),
            end=datetime(2026, 1, 16, 10, 0, 0),
        )
        recordings = self.client.find_recordings(tr, channel=0)
        self.assertEqual(recordings, [])
        self.assertEqual(mock_get.call_count, 4)


    @patch.object(AmcrestClient, "_get")
    def test_find_recordings_pagination_continues_after_snapshot_batch(self, mock_get):
        batch1_resp = MagicMock()
        batch1_resp.text = "found=1\nitems[0].FilePath=/mnt/sd/snap.jpg\nitems[0].StartTime=2026-01-16 08:00:00\nitems[0].EndTime=2026-01-16 08:00:01\n"

        batch2_resp = MagicMock()
        batch2_resp.text = "found=1\nitems[0].FilePath=/mnt/sd/video.mp4\nitems[0].StartTime=2026-01-16 08:00:00\nitems[0].EndTime=2026-01-16 08:15:00\n"

        batch3_resp = MagicMock()
        batch3_resp.text = "found=0\n"

        create_resp = MagicMock(text="result=999\n")
        search_resp = MagicMock(text="OK\n")
        close_resp = MagicMock(text="OK\n")
        destroy_resp = MagicMock(text="OK\n")

        mock_get.side_effect = [
            create_resp,
            search_resp,
            batch1_resp,
            batch2_resp,
            batch3_resp,
            close_resp,
            destroy_resp,
        ]

        tr = TimeRange(
            start=datetime(2026, 1, 16, 8, 0, 0),
            end=datetime(2026, 1, 16, 10, 0, 0),
        )
        recordings = self.client.find_recordings(tr, channel=0)
        self.assertEqual(len(recordings), 1)
        self.assertEqual(recordings[0].file_path, Path("/mnt/sd/video.mp4"))

    @patch.object(AmcrestClient, "_stream_to_file")
    def test_download_recording_atomic(self, mock_stream):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rec = Recording(
                start_time=datetime(2026, 1, 16, 8, 0, 0),
                end_time=datetime(2026, 1, 16, 8, 15, 0),
                file_path=Path("/mnt/sd/test.mp4"),
            )
            dest = Path(td) / "out.mp4"

            def simulate_stream(url, local_path):
                local_path.write_text("video binary data")

            mock_stream.side_effect = simulate_stream
            success = self.client.download_recording(rec, dest)
            self.assertTrue(success)
            self.assertTrue(dest.exists())
            self.assertFalse((Path(td) / "out.mp4.part").exists())

    @patch.object(AmcrestClient, "_stream_to_file")
    def test_download_recording_cleans_up_on_failure(self, mock_stream):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rec = Recording(
                start_time=datetime(2026, 1, 16, 8, 0, 0),
                end_time=datetime(2026, 1, 16, 8, 15, 0),
                file_path=Path("/mnt/sd/test.mp4"),
            )
            dest = Path(td) / "out.mp4"

            def simulate_fail(url, local_path):
                local_path.write_text("partial corrupt data")
                raise ConnectionResetError("Connection lost")

            mock_stream.side_effect = simulate_fail
            with self.assertRaises(RuntimeError):
                self.client.download_recording(rec, dest)

            self.assertFalse(dest.exists())
            self.assertFalse((Path(td) / "out.mp4.part").exists())


    def test_url_construction_ipv6(self):
        c1 = AmcrestClient("[::1]", "admin", "pass")
        self.assertEqual(c1._build_url("api"), "http://[::1]/api")

        c2 = AmcrestClient("[::1]:8080", "admin", "pass")
        self.assertEqual(c2._build_url("api"), "http://[::1]:8080/api")

        c3 = AmcrestClient("::1", "admin", "pass", port=8443, ssl=True)
        self.assertEqual(c3._build_url("api"), "https://[::1]:8443/api")

    @patch.object(AmcrestClient, "_get")
    def test_fetch_next_batch_handles_leading_blank_lines(self, mock_get):
        resp = MagicMock()
        resp.text = "\r\n\r\nfound=1\r\nitems[0].FilePath=/mnt/sd/test.mp4\r\n"
        mock_get.return_value = resp

        text, count = self.client._fetch_next_batch("finder_123")
        self.assertEqual(count, 1)
        self.assertIn("found=1", text)

    @patch.object(AmcrestClient, "_get")
    def test_find_recordings_sorts_chronologically(self, mock_get):
        batch1_resp = MagicMock()
        batch1_resp.text = (
            "found=2\n"
            "items[0].FilePath=/mnt/sd/late.mp4\n"
            "items[0].StartTime=2026-01-16 09:00:00\n"
            "items[0].EndTime=2026-01-16 09:15:00\n"
            "items[1].FilePath=/mnt/sd/early.mp4\n"
            "items[1].StartTime=2026-01-16 08:00:00\n"
            "items[1].EndTime=2026-01-16 08:15:00\n"
        )
        batch2_resp = MagicMock(text="found=0\n")
        create_resp = MagicMock(text="result=111\n")
        search_resp = MagicMock(text="OK\n")
        close_resp = MagicMock(text="OK\n")
        destroy_resp = MagicMock(text="OK\n")

        mock_get.side_effect = [
            create_resp,
            search_resp,
            batch1_resp,
            batch2_resp,
            close_resp,
            destroy_resp,
        ]

        tr = TimeRange(
            start=datetime(2026, 1, 16, 8, 0, 0),
            end=datetime(2026, 1, 16, 10, 0, 0),
        )
        recordings = self.client.find_recordings(tr, channel=0)
        self.assertEqual(len(recordings), 2)
        self.assertEqual(recordings[0].file_path, Path("/mnt/sd/early.mp4"))
        self.assertEqual(recordings[1].file_path, Path("/mnt/sd/late.mp4"))


if __name__ == "__main__":
    unittest.main()

