"""Known-answer tests for the completed project health audit engine.

Every test supplies a fixed input and checks the exact expected output.
These tests prove the deviation math and Green/Yellow/Red classification
are correct at every boundary defined in the Audit Criteria Register.
"""

import pandas as pd
import pytest

from completed_project_health import classify_health, compute_metrics, build_finding

# Thresholds matching config/audit_criteria.yaml v1.0.0
GREEN_PCT = 0.15
YELLOW_PCT = 0.30
GREEN_DAYS = 7
YELLOW_DAYS = 21


# ---------------------------------------------------------------------------
# classify_health — boundary tests
# ---------------------------------------------------------------------------

def _row(budget_pct, hours_pct, schedule_days):
    """Build a minimal Series for classify_health."""
    return pd.Series({
        "budget_dev_pct": budget_pct,
        "hours_dev_pct": hours_pct,
        "schedule_dev_days": schedule_days,
    })


def test_green_all_within_limits():
    assert classify_health(_row(0.10, 0.10, 5), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Green"


def test_green_at_exact_boundary():
    # Exactly at the green limit on all dimensions → still Green
    assert classify_health(_row(0.15, 0.15, 7), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Green"


def test_yellow_budget_just_over_green():
    # 15.1% budget deviation pushes out of Green
    assert classify_health(_row(0.151, 0.10, 5), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Yellow"


def test_yellow_at_exact_yellow_boundary():
    # Exactly at the yellow limit on all dimensions → still Yellow
    assert classify_health(_row(0.30, 0.30, 21), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Yellow"


def test_yellow_schedule_just_over_green():
    # 8-day slip pushes schedule out of Green; budget/hours still Green → Yellow
    assert classify_health(_row(0.10, 0.10, 8), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Yellow"


def test_red_budget_over_yellow():
    # 31% budget deviation → Red regardless of hours/schedule
    assert classify_health(_row(0.31, 0.10, 5), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_red_hours_over_yellow():
    # Hours over yellow limit → Red
    assert classify_health(_row(0.10, 0.31, 5), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_red_schedule_over_yellow():
    # 22-day slip → Red
    assert classify_health(_row(0.10, 0.10, 22), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_red_all_over_yellow():
    assert classify_health(_row(0.50, 0.50, 30), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_green_negative_deviation():
    # Coming in under budget/hours is still Green if within ±15%
    assert classify_health(_row(-0.10, -0.10, 0), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Green"


def test_red_large_under_budget_still_classifies():
    # Absolute value is used, so -40% is Red just like +40%
    assert classify_health(_row(-0.40, 0.10, 5), GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_missing_metrics_defaults_to_zero():
    # NaN values are treated as 0 deviation — project gets benefit of the doubt
    row = pd.Series({"budget_dev_pct": float("nan"), "hours_dev_pct": float("nan"), "schedule_dev_days": float("nan")})
    assert classify_health(row, GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS) == "Green"


# ---------------------------------------------------------------------------
# compute_metrics — deviation math tests
# ---------------------------------------------------------------------------

def _make_dataframes(
    proposed_budget=100_000,
    actual_budget=115_000,
    proposed_hours=1000,
    actual_hours=1100,
    proposed_start="2025-01-01",
    proposed_end="2025-06-01",
    actual_start="2025-01-01",
    actual_end="2025-06-08",
    status="completed",
    proposed_resources=4,
    actual_resources=4,
):
    proposal = pd.DataFrame([{
        "project_id": "TEST-001",
        "project_name": "Test Project",
        "proposed_budget": proposed_budget,
        "proposed_hours": proposed_hours,
        "proposed_start_date": proposed_start,
        "proposed_end_date": proposed_end,
        "proposed_resource_count": proposed_resources,
        "project_manager": "Test PM",
        "client": "Test Client",
        "project_type": "Automation",
    }])
    actual = pd.DataFrame([{
        "project_id": "TEST-001",
        "actual_budget": actual_budget,
        "actual_hours": actual_hours,
        "actual_start_date": actual_start,
        "actual_end_date": actual_end,
        "status": status,
        "actual_resource_count": actual_resources,
        "closeout_notes": "",
    }])
    return proposal, actual


def _run(proposal, actual):
    return compute_metrics(proposal, actual, GREEN_PCT, YELLOW_PCT, GREEN_DAYS, YELLOW_DAYS)


def test_budget_deviation_absolute():
    proposal, actual = _make_dataframes(proposed_budget=100_000, actual_budget=115_000)
    result = _run(proposal, actual)
    assert result["budget_dev_abs"].iloc[0] == 15_000


def test_budget_deviation_percent():
    proposal, actual = _make_dataframes(proposed_budget=100_000, actual_budget=115_000)
    result = _run(proposal, actual)
    assert abs(result["budget_dev_pct"].iloc[0] - 0.15) < 1e-9


def test_hours_deviation_absolute():
    proposal, actual = _make_dataframes(proposed_hours=1000, actual_hours=1100)
    result = _run(proposal, actual)
    assert result["hours_dev_abs"].iloc[0] == 100


def test_hours_deviation_percent():
    proposal, actual = _make_dataframes(proposed_hours=1000, actual_hours=1100)
    result = _run(proposal, actual)
    assert abs(result["hours_dev_pct"].iloc[0] - 0.10) < 1e-9


def test_schedule_deviation_days():
    # proposed end 2025-06-01, actual end 2025-06-08 → 7-day slip
    proposal, actual = _make_dataframes(proposed_end="2025-06-01", actual_end="2025-06-08")
    result = _run(proposal, actual)
    assert result["schedule_dev_days"].iloc[0] == 7


def test_schedule_deviation_early_finish():
    # Finished 3 days early → negative deviation
    proposal, actual = _make_dataframes(proposed_end="2025-06-01", actual_end="2025-05-29")
    result = _run(proposal, actual)
    assert result["schedule_dev_days"].iloc[0] == -3


def test_resource_deviation():
    proposal, actual = _make_dataframes(proposed_resources=4, actual_resources=5)
    result = _run(proposal, actual)
    assert result["resource_dev_abs"].iloc[0] == 1
    assert abs(result["resource_dev_pct"].iloc[0] - 0.25) < 1e-9


def test_health_green_on_good_project():
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=110_000,   # +10% → Green
        proposed_hours=1000, actual_hours=1050,            # +5% → Green
        proposed_end="2025-06-01", actual_end="2025-06-05",  # 4 days → Green
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Green"


def test_health_red_on_overrun_project():
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=145_000,   # +45% → Red
        proposed_hours=1000, actual_hours=1400,            # +40% → Red
        proposed_end="2025-06-01", actual_end="2025-07-15",  # 44 days → Red
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Red"


def test_closed_status_included():
    proposal, actual = _make_dataframes(status="closed")
    result = _run(proposal, actual)
    assert len(result) == 1


def test_non_eligible_status_excluded():
    proposal, actual = _make_dataframes(status="active")
    result = _run(proposal, actual)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# build_finding — output text tests
# ---------------------------------------------------------------------------

def test_finding_contains_all_three_metrics():
    row = pd.Series({
        "budget_dev_pct": 0.20,
        "hours_dev_pct": 0.10,
        "schedule_dev_days": 15,
    })
    finding = build_finding(row)
    assert "budget deviation" in finding
    assert "hours deviation" in finding
    assert "schedule deviation" in finding


def test_finding_fallback_when_all_nan():
    row = pd.Series({
        "budget_dev_pct": float("nan"),
        "hours_dev_pct": float("nan"),
        "schedule_dev_days": float("nan"),
    })
    finding = build_finding(row)
    assert "Review required" in finding
