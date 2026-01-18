from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class TimeRange:
    start: datetime
    end: datetime

    @classmethod
    def from_iso8601(cls, start_str: str, end_str: str) -> "TimeRange":
        return cls(
            start=datetime.fromisoformat(start_str), end=datetime.fromisoformat(end_str)
        )

    def to_amcrest_format(self) -> tuple[str, str]:
        fmt = "%Y-%m-%d %H:%M:%S"
        start = self.start.replace(tzinfo=None) if self.start.tzinfo else self.start
        end = self.end.replace(tzinfo=None) if self.end.tzinfo else self.end
        return start.strftime(fmt), end.strftime(fmt)


@dataclass
class Recording:
    start_time: datetime
    end_time: datetime
    file_path: Path
    channel: int = 0

    def __post_init__(self):
        if isinstance(self.file_path, str):
            self.file_path = Path(self.file_path)
