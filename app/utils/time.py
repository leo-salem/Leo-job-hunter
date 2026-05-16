from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as dateparser


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Greenhouse sometimes ships millisecond epochs as strings; handle both.
        if value.isdigit():
            ts = int(value)
            if ts > 10_000_000_000:  # ms
                ts //= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        dt = dateparser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def parse_epoch_ms(value: int | float | None) -> Optional[datetime]:
    if value is None:
        return None
    try:
        v = float(value)
        if v > 10_000_000_000:  # ms
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    except (ValueError, TypeError):
        return None
