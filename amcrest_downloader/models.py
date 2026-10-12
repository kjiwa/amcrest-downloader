from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime

    def __post_init__(self):
        if (self.start.tzinfo is None) != (self.end.tzinfo is None):
            raise ValueError(
                "Start and end times must both be timezone-aware or both be timezone-naive"
            )
        if self.start > self.end:
            raise ValueError(
                f"Start time ({self.start}) must be before or equal to end time ({self.end})"
            )

    @classmethod
    def from_iso8601(cls, start_str: str, end_str: str) -> "TimeRange":
        return cls(start=cls._parse_iso8601(start_str), end=cls._parse_iso8601(end_str))

    @staticmethod
    def _parse_iso8601(value: str) -> datetime:
        if value[-1:] in ("Z", "z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    def to_camera_local(self, offset: timedelta) -> "TimeRange":
        if self.start.tzinfo is None:
            return self
        return TimeRange(
            self._to_camera_clock(self.start, offset), self._to_camera_clock(self.end, offset)
        )

    @staticmethod
    def _to_camera_clock(moment: datetime, offset: timedelta) -> datetime:
        return moment.astimezone(timezone.utc).replace(tzinfo=None) + offset

    def to_amcrest_format(self) -> tuple[str, str]:
        fmt = "%Y-%m-%d %H:%M:%S"
        return self.start.strftime(fmt), self.end.strftime(fmt)


@dataclass(frozen=True, order=True)
class Recording:
    start_time: datetime
    end_time: datetime
    file_path: Path
    file_size: int = 0
    channel: int = 0

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
