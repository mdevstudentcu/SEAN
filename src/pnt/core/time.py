"""Time base (ADR-0008): int64 nanoseconds of GPS time since the GPS epoch.

This module is the only place that converts between GPS time and anything else.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

NS = 1_000_000_000
GPS_EPOCH = datetime(1980, 1, 6, tzinfo=UTC)
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# GPS - UTC since 2017-01-01. No leap second has been announced since; update if IERS does.
LEAP_SECONDS = 18
WEEK_NS = 7 * 86_400 * NS


def s_to_ns(seconds: float) -> int:
    return round(seconds * NS)


def ns_to_s(t_ns: int) -> float:
    return t_ns / NS


def utc_to_gps_ns(dt: datetime) -> int:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    delta = dt.astimezone(UTC) - GPS_EPOCH + timedelta(seconds=LEAP_SECONDS)
    return (delta.days * 86_400 + delta.seconds) * NS + delta.microseconds * 1_000


def gps_ns_to_utc(t_ns: int) -> datetime:
    return GPS_EPOCH + timedelta(microseconds=t_ns // 1_000) - timedelta(seconds=LEAP_SECONDS)


def gps_ns_to_unix_ns(t_ns: int) -> int:
    """Unix time in ns (UTC, leap seconds not counted) for GPS time `t_ns`, for tools that
    read timestamps as Unix time, such as Foxglove. Integer arithmetic, so no rounding. Like
    `gps_ns_to_utc`, it applies today's `LEAP_SECONDS` to every time, so it is only right for
    times after 2017-01-01."""
    epoch_offset_s = (GPS_EPOCH - UNIX_EPOCH) // timedelta(seconds=1)
    return t_ns + (epoch_offset_s - LEAP_SECONDS) * NS


def unix_ns_to_gps_ns(t_ns: int) -> int:
    """GPS time in ns for Unix time `t_ns` (inverse of `gps_ns_to_unix_ns`, same leap-second
    caveat)."""
    epoch_offset_s = (GPS_EPOCH - UNIX_EPOCH) // timedelta(seconds=1)
    return t_ns - (epoch_offset_s - LEAP_SECONDS) * NS


def now_gps_ns() -> int:
    """The host clock as GPS ns. On the payload the clock is disciplined to GPS PPS by chrony
    (ASM-04), so this is the timestamp every captured record carries."""
    return unix_ns_to_gps_ns(time.time_ns())


def week_tow_to_gps_ns(week: int, tow_s: float) -> int:
    return week * WEEK_NS + s_to_ns(tow_s)


def gps_ns_to_week_tow(t_ns: int) -> tuple[int, float]:
    week, rem = divmod(t_ns, WEEK_NS)
    return week, rem / NS
