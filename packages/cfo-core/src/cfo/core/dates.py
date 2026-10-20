"""Calendar-date helpers. Everything is a plain date; 'today' is injected by callers."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    return datetime.now(IST).date()


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def clamp_day(year: int, month: int, day: int) -> date:
    """The given day of the month, or the month's last day when it has no such day."""
    return date(year, month, min(day, last_day_of_month(year, month)))


def parse_month(month: str) -> tuple[int, int]:
    year_text, _, month_text = month.partition("-")
    year, mon = int(year_text), int(month_text)
    if not (1 <= mon <= 12) or len(year_text) != 4 or len(month_text) != 2:
        raise ValueError(f"month must be YYYY-MM: {month!r}")
    return year, mon


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = parse_month(month)
    return date(year, mon, 1), date(year, mon, last_day_of_month(year, mon))


def previous_month(month: str) -> str:
    start, _ = month_bounds(month)
    return month_key(start - timedelta(days=1))


def next_month(month: str) -> str:
    _, end = month_bounds(month)
    return month_key(end + timedelta(days=1))
