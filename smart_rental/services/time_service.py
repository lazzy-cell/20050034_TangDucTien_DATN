"""Centralized timezone helpers.

Firestore stores instants; the backend writes UTC-aware timestamps and clients
format them in their local timezone. Business-day calculations that belong to
the property use Asia/Ho_Chi_Minh explicitly.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def iso_utc(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "to_datetime"):
        value = value.to_datetime()
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        # Legacy records were written by a UTC server with naive datetimes.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
