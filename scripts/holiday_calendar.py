"""Company holiday calendar for the active-projects rate engine.

Computes the 11 recognized holidays for any year, applying the
weekend-observed rule (Saturday holiday -> observed Friday before;
Sunday holiday -> observed Monday after). Holidays that are already
defined as a specific weekday (e.g. "3rd Monday of January") never need
shifting — only the fixed-calendar-date holidays do.

This is pure calendar math — no project data required, so it's testable
and correct independent of anything else in the active-projects work.
"""

from __future__ import annotations

from datetime import date, timedelta

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


def easter_sunday(year: int) -> date:
    """Meeus/Jones/Butcher Gregorian algorithm for the date of Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th occurrence (1-indexed) of `weekday` in the given month."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    d += timedelta(days=offset)
    d += timedelta(weeks=n - 1)
    return d


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """The last occurrence of `weekday` in the given month."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    d = next_month_first - timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)


def observed(d: date) -> date:
    """Weekend-observed shift: Saturday -> Friday before, Sunday -> Monday after."""
    if d.weekday() == SATURDAY:
        return d - timedelta(days=1)
    if d.weekday() == SUNDAY:
        return d + timedelta(days=1)
    return d


def company_holidays(year: int) -> dict[str, date]:
    """All 11 recognized holidays for the given year, weekend-shift applied
    only to the fixed-calendar-date holidays (the named-weekday ones never
    fall on a weekend by construction)."""
    good_friday = easter_sunday(year) - timedelta(days=2)
    thanksgiving = nth_weekday_of_month(year, 11, THURSDAY, 4)

    return {
        "New Year's Day": observed(date(year, 1, 1)),
        "Martin Luther King Jr. Day": nth_weekday_of_month(year, 1, MONDAY, 3),
        "Good Friday": good_friday,
        "Memorial Day": last_weekday_of_month(year, 5, MONDAY),
        "Independence Day": observed(date(year, 7, 4)),
        "Labor Day": nth_weekday_of_month(year, 9, MONDAY, 1),
        "Thanksgiving Day": thanksgiving,
        "Friday after Thanksgiving Day": thanksgiving + timedelta(days=1),
        "Christmas Eve": observed(date(year, 12, 24)),
        "Christmas Day": observed(date(year, 12, 25)),
        "New Year's Eve": observed(date(year, 12, 31)),
    }


def holiday_dates_for_years(years: range | list[int]) -> dict[date, str]:
    """Flat {date: holiday_name} map spanning multiple years — the lookup
    table the rate engine actually queries against a timesheet date."""
    out: dict[date, str] = {}
    for year in years:
        for name, d in company_holidays(year).items():
            out[d] = name
    return out


def is_holiday(d: date, calendar: dict[date, str]) -> str | None:
    """Return the holiday name if `d` is a recognized (observed) holiday, else None."""
    return calendar.get(d)
