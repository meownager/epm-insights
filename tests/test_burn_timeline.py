"""Known-answer tests for the budget/hours burn timeline classification."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from burn_timeline import compute_burn_series, first_crossing_dates


def _ledger(rows):
    return pd.DataFrame(rows)


def test_on_pace_stays_green():
    # $100k proposed over 100 days, spending exactly linearly
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_revenue": 0},
        {"date": "2026-02-10", "cumulative_revenue": 40000},   # day 40 of 100 -> pace 40000
        {"date": "2026-04-11", "cumulative_revenue": 100000},  # day 100 -> pace 100000
    ])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    assert (series["zone"] == "Green").all()


def test_overspending_early_crosses_to_red():
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_revenue": 0},
        {"date": "2026-01-11", "cumulative_revenue": 80000},   # day 10 of 100, pace=10000, actual=80000 -> way over
        {"date": "2026-04-11", "cumulative_revenue": 100000},  # day 100 -> pace 100000, on pace at the end
    ])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    assert series.iloc[1]["zone"] == "Red"
    assert series.iloc[2]["zone"] == "Green"  # ends on pace even though it spiked mid-project


def test_yellow_band_boundary():
    # day 50 of 100 -> pace 50000; actual 65000 -> dev 15% -> exactly at yellow boundary (green_max)
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_revenue": 0},
        {"date": "2026-02-20", "cumulative_revenue": 65000},
        {"date": "2026-04-11", "cumulative_revenue": 100000},
    ])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    assert series.iloc[1]["zone"] == "Green"  # exactly at green_max boundary → still Green


def test_negative_deviation_uses_absolute_value():
    # underspending relative to pace should also register as a deviation
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_revenue": 0},
        {"date": "2026-02-20", "cumulative_revenue": 0},  # day 50, pace 50000, actual 0 -> -100% dev
        {"date": "2026-04-11", "cumulative_revenue": 100000},
    ])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    assert series.iloc[1]["zone"] == "Red"


def test_no_proposed_value_returns_unavailable():
    ledger = _ledger([{"date": "2026-01-01", "cumulative_revenue": 1000}])
    series = compute_burn_series(ledger, None, "cumulative_revenue", 0.15, 0.30)
    assert (series["zone"] == "Unavailable").all()


def test_zero_proposed_value_returns_unavailable():
    ledger = _ledger([{"date": "2026-01-01", "cumulative_revenue": 1000}])
    series = compute_burn_series(ledger, 0, "cumulative_revenue", 0.15, 0.30)
    assert (series["zone"] == "Unavailable").all()


def test_empty_ledger_returns_empty():
    series = compute_burn_series(pd.DataFrame(columns=["date", "cumulative_revenue"]),
                                 100000, "cumulative_revenue", 0.15, 0.30)
    assert series.empty


def test_single_day_project_pace_is_full_amount():
    ledger = _ledger([{"date": "2026-01-01", "cumulative_revenue": 100000}])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    assert series.iloc[0]["expected_pace"] == 100000
    assert series.iloc[0]["zone"] == "Green"


def test_hours_column_works_the_same_way():
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_hours": 0},
        {"date": "2026-04-11", "cumulative_hours": 1000},
    ])
    series = compute_burn_series(ledger, 1000, "cumulative_hours", 0.15, 0.30)
    assert series.iloc[-1]["zone"] == "Green"


# ── first_crossing_dates ─────────────────────────────────────────────────────

def test_first_crossing_dates_finds_both():
    # day 19 of 100 -> pace 19000; actual 60000 -> dev 41% -> beyond yellow (30%) -> Red
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_revenue": 0},
        {"date": "2026-01-20", "cumulative_revenue": 60000},
        {"date": "2026-04-11", "cumulative_revenue": 100000},
    ])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    crossings = first_crossing_dates(series)
    assert crossings["first_red"] == pd.Timestamp("2026-01-20")


def test_first_crossing_dates_none_when_always_green():
    ledger = _ledger([
        {"date": "2026-01-01", "cumulative_revenue": 0},
        {"date": "2026-04-11", "cumulative_revenue": 100000},
    ])
    series = compute_burn_series(ledger, 100000, "cumulative_revenue", 0.15, 0.30)
    crossings = first_crossing_dates(series)
    assert crossings["first_yellow"] is None
    assert crossings["first_red"] is None
