"""Known-answer tests for the completed project health audit engine.

Every test supplies a fixed input and checks the exact expected output.
These tests prove the deviation math and Green/Yellow/Red classification
are correct at every boundary defined in the Audit Criteria Register,
for both billing types (fixed_fee and t_and_e).
"""

import pandas as pd
import pytest

from completed_project_health import (
    classify_health,
    compute_metrics,
    build_finding,
    get_billing_thresholds,
)

# Thresholds matching config/audit_criteria.yaml v2.0.0
GREEN_PCT_FF = 0.15
YELLOW_PCT_FF = 0.30
GREEN_PCT_TE = 0.25
YELLOW_PCT_TE = 0.40
GREEN_DAYS = 7
YELLOW_DAYS = 21

CRITERIA = {
    "version": "2.0.0",
    "completed_projects": {
        "eligible_statuses": ["completed", "closed"],
        "fixed_fee": {
            "budget": {"green_max": GREEN_PCT_FF, "yellow_max": YELLOW_PCT_FF},
            "hours": {"green_max": GREEN_PCT_FF, "yellow_max": YELLOW_PCT_FF},
            "schedule": {"green_max_days": GREEN_DAYS, "yellow_max_days": YELLOW_DAYS},
        },
        "t_and_e": {
            "budget": {"green_max": GREEN_PCT_TE, "yellow_max": YELLOW_PCT_TE},
            "hours": {"green_max": GREEN_PCT_FF, "yellow_max": YELLOW_PCT_FF},
            "schedule": {"green_max_days": GREEN_DAYS, "yellow_max_days": YELLOW_DAYS},
        },
    },
}


# ---------------------------------------------------------------------------
# classify_health — boundary tests (billing-type-agnostic; thresholds passed in)
# ---------------------------------------------------------------------------

def _row(budget_pct, hours_pct, schedule_days):
    return pd.Series({
        "budget_dev_pct": budget_pct,
        "hours_dev_pct": hours_pct,
        "schedule_dev_days": schedule_days,
    })


def test_green_all_within_limits():
    assert classify_health(_row(0.10, 0.10, 5), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Green"


def test_green_at_exact_boundary():
    assert classify_health(_row(0.15, 0.15, 7), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Green"


def test_yellow_budget_just_over_green():
    assert classify_health(_row(0.151, 0.10, 5), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Yellow"


def test_yellow_at_exact_yellow_boundary():
    assert classify_health(_row(0.30, 0.30, 21), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Yellow"


def test_yellow_schedule_just_over_green():
    assert classify_health(_row(0.10, 0.10, 8), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Yellow"


def test_red_budget_over_yellow():
    assert classify_health(_row(0.31, 0.10, 5), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_red_hours_over_yellow():
    assert classify_health(_row(0.10, 0.31, 5), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_red_schedule_over_yellow():
    assert classify_health(_row(0.10, 0.10, 22), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_red_all_over_yellow():
    assert classify_health(_row(0.50, 0.50, 30), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_green_negative_deviation():
    assert classify_health(_row(-0.10, -0.10, 0), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Green"


def test_red_large_under_budget_still_classifies():
    assert classify_health(_row(-0.40, 0.10, 5), GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Red"


def test_missing_metrics_defaults_to_zero():
    row = pd.Series({"budget_dev_pct": float("nan"), "hours_dev_pct": float("nan"), "schedule_dev_days": float("nan")})
    assert classify_health(row, GREEN_PCT_FF, YELLOW_PCT_FF, GREEN_DAYS, YELLOW_DAYS) == "Green"


# ---------------------------------------------------------------------------
# get_billing_thresholds — routing tests
# ---------------------------------------------------------------------------

def test_fixed_fee_thresholds_loaded():
    t = get_billing_thresholds("fixed_fee", CRITERIA)
    assert t["green_pct"] == GREEN_PCT_FF
    assert t["yellow_pct"] == YELLOW_PCT_FF


def test_t_and_e_thresholds_loaded():
    t = get_billing_thresholds("t_and_e", CRITERIA)
    assert t["green_pct"] == GREEN_PCT_TE
    assert t["yellow_pct"] == YELLOW_PCT_TE


def test_unknown_billing_type_defaults_to_fixed_fee():
    t = get_billing_thresholds("unknown_type", CRITERIA)
    assert t["green_pct"] == GREEN_PCT_FF


def test_empty_billing_type_defaults_to_fixed_fee():
    t = get_billing_thresholds("", CRITERIA)
    assert t["green_pct"] == GREEN_PCT_FF


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
    billing_type="fixed_fee",
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
        "billing_type": billing_type,
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
    return compute_metrics(proposal, actual, CRITERIA)


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
    proposal, actual = _make_dataframes(proposed_end="2025-06-01", actual_end="2025-06-08")
    result = _run(proposal, actual)
    assert result["schedule_dev_days"].iloc[0] == 7


def test_schedule_deviation_early_finish():
    proposal, actual = _make_dataframes(proposed_end="2025-06-01", actual_end="2025-05-29")
    result = _run(proposal, actual)
    assert result["schedule_dev_days"].iloc[0] == -3


def test_resource_deviation():
    proposal, actual = _make_dataframes(proposed_resources=4, actual_resources=5)
    result = _run(proposal, actual)
    assert result["resource_dev_abs"].iloc[0] == 1
    assert abs(result["resource_dev_pct"].iloc[0] - 0.25) < 1e-9


def test_health_green_on_good_fixed_fee_project():
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=110_000,
        proposed_hours=1000, actual_hours=1050,
        proposed_end="2025-06-01", actual_end="2025-06-05",
        billing_type="fixed_fee",
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Green"


def test_health_red_on_overrun_fixed_fee_project():
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=145_000,
        proposed_hours=1000, actual_hours=1400,
        proposed_end="2025-06-01", actual_end="2025-07-15",
        billing_type="fixed_fee",
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
# Billing-type threshold routing tests
# ---------------------------------------------------------------------------

def test_t_and_e_20pct_budget_is_green():
    # 20% budget deviation: Yellow under fixed_fee (>15%), Green under t_and_e (≤25%)
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=120_000,  # +20%
        proposed_hours=1000, actual_hours=1000,
        proposed_end="2025-06-01", actual_end="2025-06-01",
        billing_type="t_and_e",
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Green"


def test_fixed_fee_20pct_budget_is_yellow():
    # Same 20% deviation is Yellow under fixed_fee
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=120_000,  # +20%
        proposed_hours=1000, actual_hours=1000,
        proposed_end="2025-06-01", actual_end="2025-06-01",
        billing_type="fixed_fee",
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Yellow"


def test_t_and_e_35pct_budget_is_yellow():
    # 35% budget deviation: Red under fixed_fee (>30%), Yellow under t_and_e (≤40%)
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=135_000,  # +35%
        proposed_hours=1000, actual_hours=1000,
        proposed_end="2025-06-01", actual_end="2025-06-01",
        billing_type="t_and_e",
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Yellow"


def test_fixed_fee_35pct_budget_is_red():
    # Same 35% deviation is Red under fixed_fee
    proposal, actual = _make_dataframes(
        proposed_budget=100_000, actual_budget=135_000,  # +35%
        proposed_hours=1000, actual_hours=1000,
        proposed_end="2025-06-01", actual_end="2025-06-01",
        billing_type="fixed_fee",
    )
    result = _run(proposal, actual)
    assert result["health_status"].iloc[0] == "Red"


def test_t_and_e_hours_threshold_same_as_fixed_fee():
    # Hours threshold is identical for both billing types — 20% hours = Yellow for both
    for billing_type in ["fixed_fee", "t_and_e"]:
        proposal, actual = _make_dataframes(
            proposed_budget=100_000, actual_budget=100_000,
            proposed_hours=1000, actual_hours=1200,  # +20%
            proposed_end="2025-06-01", actual_end="2025-06-01",
            billing_type=billing_type,
        )
        result = _run(proposal, actual)
        assert result["health_status"].iloc[0] == "Yellow", f"Expected Yellow for {billing_type}"


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
