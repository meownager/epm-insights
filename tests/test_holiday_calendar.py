"""Known-answer tests for the company holiday calendar.

Cross-checked two ways: against Python's stdlib `calendar` module (a
completely independent code path from the implementation) for the
nth/last-weekday logic, and against well-known real-world anchor dates
for the fixed-date + weekend-observed-shift logic.
"""

import calendar as stdlib_calendar
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from holiday_calendar import (
    MONDAY,
    THURSDAY,
    company_holidays,
    easter_sunday,
    holiday_dates_for_years,
    is_holiday,
    last_weekday_of_month,
    nth_weekday_of_month,
    observed,
)


# ── nth_weekday_of_month / last_weekday_of_month — cross-checked vs stdlib ──

def _stdlib_nth_weekday(year, month, weekday, n):
    """Independent reimplementation using calendar.monthcalendar, to cross-check."""
    weeks = stdlib_calendar.monthcalendar(year, month)
    matches = [week[weekday] for week in weeks if week[weekday] != 0]
    return date(year, month, matches[n - 1])


def _stdlib_last_weekday(year, month, weekday):
    weeks = stdlib_calendar.monthcalendar(year, month)
    matches = [week[weekday] for week in weeks if week[weekday] != 0]
    return date(year, month, matches[-1])


@pytest.mark.parametrize("year", [2024, 2025, 2026, 2027, 2028])
def test_nth_weekday_matches_stdlib_independent_calc(year):
    for month in range(1, 13):
        for weekday in range(7):
            assert nth_weekday_of_month(year, month, weekday, 1) == _stdlib_nth_weekday(year, month, weekday, 1)


@pytest.mark.parametrize("year", [2024, 2025, 2026, 2027, 2028])
def test_last_weekday_matches_stdlib_independent_calc(year):
    for month in range(1, 13):
        for weekday in range(7):
            assert last_weekday_of_month(year, month, weekday) == _stdlib_last_weekday(year, month, weekday)


# ── easter_sunday — known real dates ─────────────────────────────────────────

def test_easter_2024():
    assert easter_sunday(2024) == date(2024, 3, 31)


def test_easter_2025():
    assert easter_sunday(2025) == date(2025, 4, 20)


def test_easter_2026():
    assert easter_sunday(2026) == date(2026, 4, 5)


def test_good_friday_is_two_days_before_easter():
    h = company_holidays(2026)
    assert h["Good Friday"] == date(2026, 4, 3)


# ── observed() weekend-shift rule ────────────────────────────────────────────

def test_observed_saturday_shifts_to_friday():
    saturday = date(2026, 7, 4)  # July 4, 2026 is a Saturday (well-known: US 250th)
    assert saturday.weekday() == 5
    assert observed(saturday) == date(2026, 7, 3)


def test_observed_sunday_shifts_to_monday():
    # New Year's Day 2028 falls on a Saturday; New Year's Eve 2028 is Sunday
    assert date(2028, 12, 31).weekday() == 6  # Sunday
    assert observed(date(2028, 12, 31)) == date(2029, 1, 1)


def test_observed_weekday_unchanged():
    friday = date(2026, 12, 25)  # Christmas 2026 falls on a Friday
    assert friday.weekday() == 4
    assert observed(friday) == friday


# ── company_holidays — full known-answer year ────────────────────────────────

def test_holidays_2026_known_dates():
    h = company_holidays(2026)
    assert h["New Year's Day"] == date(2026, 1, 1)          # Thursday, no shift
    assert h["Independence Day"] == date(2026, 7, 3)         # July 4 is Saturday -> observed Friday
    assert h["Christmas Eve"] == date(2026, 12, 24)          # Thursday, no shift
    assert h["Christmas Day"] == date(2026, 12, 25)          # Friday, no shift
    assert h["Thanksgiving Day"] == date(2026, 11, 26)       # 4th Thursday of Nov 2026
    assert h["Friday after Thanksgiving Day"] == date(2026, 11, 27)


def test_all_11_holidays_present():
    h = company_holidays(2026)
    assert len(h) == 11


def test_named_weekday_holidays_always_fall_on_that_weekday():
    for year in [2024, 2025, 2026, 2027, 2028]:
        h = company_holidays(year)
        assert h["Martin Luther King Jr. Day"].weekday() == MONDAY
        assert h["Memorial Day"].weekday() == MONDAY
        assert h["Labor Day"].weekday() == MONDAY
        assert h["Thanksgiving Day"].weekday() == THURSDAY
        assert h["Good Friday"].weekday() == 4  # Friday


def test_holiday_never_falls_on_a_weekend_after_observation():
    for year in [2024, 2025, 2026, 2027, 2028, 2029, 2030]:
        h = company_holidays(year)
        for name, d in h.items():
            assert d.weekday() < 5, f"{name} in {year} fell on a weekend: {d}"


# ── holiday_dates_for_years / is_holiday ─────────────────────────────────────

def test_holiday_dates_for_years_spans_multiple_years():
    cal = holiday_dates_for_years([2025, 2026])
    assert date(2025, 12, 25) in cal
    assert date(2026, 12, 25) in cal


def test_is_holiday_true_for_recognized_date():
    cal = holiday_dates_for_years([2026])
    assert is_holiday(date(2026, 7, 3), cal) == "Independence Day"


def test_is_holiday_none_for_ordinary_date():
    cal = holiday_dates_for_years([2026])
    assert is_holiday(date(2026, 3, 15), cal) is None
