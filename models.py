from dataclasses import dataclass
from datetime import datetime
from functools import total_ordering
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
        return cls(
            start=datetime.fromisoformat(start_str), end=datetime.fromisoformat(end_str)
        )

    def to_amcrest_format(self) -> tuple[str, str]:
        fmt = "%Y-%m-%d %H:%M:%S"
        return self.start.strftime(fmt), self.end.strftime(fmt)


@total_ordering
@dataclass
class Recording:
    start_time: datetime
    end_time: datetime
    file_path: Path
    file_size: int = 0
    channel: int = 0

    def __post_init__(self):
        if isinstance(self.file_path, str):
            self.file_path = Path(self.file_path)

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    def __lt__(self, other: "Recording") -> bool:
        if not isinstance(other, Recording):
            return NotImplemented
        return (self.start_time, self.end_time, str(self.file_path)) < (
            other.start_time,
            other.end_time,
            str(other.file_path),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Recording):
            return NotImplemented
        return (
            self.start_time == other.start_time
            and self.end_time == other.end_time
            and self.file_path == other.file_path
            and self.file_size == other.file_size
            and self.channel == other.channel
        )


