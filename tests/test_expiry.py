from datetime import date

import pytest

from freezer.expiry import EXPIRED, EXPIRING, OK, days_left, expiry_status, today_in

TODAY = date(2026, 9, 27)


def test_days_left_crosses_month():
    assert days_left(date(2026, 10, 2), TODAY) == 5


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        (date(2026, 9, 26), EXPIRED),   # ieri
        (date(2026, 9, 27), EXPIRING),  # oggi
        (date(2026, 9, 28), EXPIRING),  # domani
        (date(2026, 10, 4), EXPIRING),  # oggi + 7
        (date(2026, 10, 5), OK),        # oggi + 8
    ],
)
def test_expiry_status_boundaries(expiry, expected):
    assert expiry_status(expiry, TODAY, 7) == expected


def test_warn_days_zero_only_today_is_expiring():
    assert expiry_status(TODAY, TODAY, 0) == EXPIRING
    assert expiry_status(date(2026, 9, 28), TODAY, 0) == OK


def test_today_in_returns_a_date():
    assert isinstance(today_in("Europe/Rome"), date)
