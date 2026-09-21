from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_iso(dt: datetime) -> str:
    return to_utc(dt).isoformat()


def from_iso(text: str) -> datetime:
    return to_utc(datetime.fromisoformat(text))


def from_unix_epoch(ts: int | float) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=UTC)
