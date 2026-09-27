"""Stato di scadenza di un lotto. Stessa regola di web/expiry.js."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

EXPIRED = "expired"
EXPIRING = "expiring"
OK = "ok"


def today_in(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def days_left(expiry: date, today: date) -> int:
    return (expiry - today).days


def expiry_status(expiry: date, today: date, warn_days: int) -> str:
    days = days_left(expiry, today)
    if days < 0:
        return EXPIRED
    if days <= warn_days:
        return EXPIRING
    return OK
