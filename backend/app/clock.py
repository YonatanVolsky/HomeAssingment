from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def iso(moment: datetime) -> str:
    """ISO 8601 UTC with milliseconds and a Z, e.g. 2026-10-29T12:00:00.000Z."""
    return moment.astimezone(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
