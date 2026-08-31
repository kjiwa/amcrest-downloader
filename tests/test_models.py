import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from models import TimeRange, Recording


class TestTimeRange(unittest.TestCase):
    def test_valid_time_range(self):
        start = datetime(2026, 1, 16, 8, 0, 0)
        end = datetime(2026, 1, 16, 10, 0, 0)
        tr = TimeRange(start=start, end=end)
        self.assertEqual(tr.start, start)
        self.assertEqual(tr.end, end)

    def test_start_after_end_raises_value_error(self):
        start = datetime(2026, 1, 16, 10, 0, 0)
        end = datetime(2026, 1, 16, 8, 0, 0)
        with self.assertRaises(ValueError):
            TimeRange(start=start, end=end)

    def test_from_iso8601_valid(self):
        tr = TimeRange.from_iso8601("2026-01-16T08:00:00", "2026-01-16T10:00:00")
        self.assertEqual(tr.start, datetime(2026, 1, 16, 8, 0, 0))
        self.assertEqual(tr.end, datetime(2026, 1, 16, 10, 0, 0))

    def test_to_amcrest_format_naive(self):
        tr = TimeRange(
            start=datetime(2026, 1, 16, 8, 0, 0),
            end=datetime(2026, 1, 16, 10, 0, 0),
        )
        start_str, end_str = tr.to_amcrest_format()
        self.assertEqual(start_str, "2026-01-16 08:00:00")
        self.assertEqual(end_str, "2026-01-16 10:00:00")

    def test_to_amcrest_format_timezone(self):
        tz = timezone(timedelta(hours=-5))
        tr = TimeRange(
            start=datetime(2026, 1, 16, 8, 0, 0, tzinfo=tz),
            end=datetime(2026, 1, 16, 10, 0, 0, tzinfo=tz),
        )
        start_str, end_str = tr.to_amcrest_format()
        self.assertEqual(start_str, "2026-01-16 08:00:00")
        self.assertEqual(end_str, "2026-01-16 10:00:00")


class TestRecording(unittest.TestCase):
    def test_recording_creation_and_attributes(self):
        start = datetime(2026, 1, 16, 8, 0, 0)
        end = datetime(2026, 1, 16, 8, 15, 0)
        rec = Recording(
            start_time=start,
            end_time=end,
            file_path="/mnt/sd/test.mp4",
            file_size=15000000,
            channel=0,
        )
        self.assertEqual(rec.file_path, Path("/mnt/sd/test.mp4"))
        self.assertEqual(rec.duration_seconds, 900)
        self.assertEqual(rec.file_size, 15000000)

    def test_recording_ordering(self):
        rec1 = Recording(
            start_time=datetime(2026, 1, 16, 8, 0, 0),
            end_time=datetime(2026, 1, 16, 8, 15, 0),
            file_path=Path("/mnt/sd/1.mp4"),
        )
        rec2 = Recording(
            start_time=datetime(2026, 1, 16, 8, 15, 0),
            end_time=datetime(2026, 1, 16, 8, 30, 0),
            file_path=Path("/mnt/sd/2.mp4"),
        )
        self.assertLess(rec1, rec2)
        self.assertEqual(sorted([rec2, rec1]), [rec1, rec2])


if __name__ == "__main__":
    unittest.main()
