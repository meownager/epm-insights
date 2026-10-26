"""Known-answer tests for the active-project burn rate (docs/active-projects-spec.md).

Cases 1-10 match the spec's test-case tables exactly. The shared scenario:
budget 100,000 and 500 hours; planned start 2025-12-21; as of 2026-03-01
(10 weeks in); 40,000 spent, of which 20,000 is time in the last 28 days and
8,000 is expenses from before the window.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from active_project_health import (
    assess_portfolio, assess_project, load_settings, red_line_days, window_days,
)

# Matches config/audit_criteria.yaml v3.0.0, pinned so these known answers stay fixed
SETTINGS = {
    "window": {"pct": 0.25, "min_days": 3, "max_days": 28},
    "red_line": {"pct": 0.10, "min_days": 1},
}
AS_OF = "2026-03-01"
START = "2025-12-21"


def _project(planned_end, **extra):
    return {"project_id": "10001-T", "billing_type": "t_and_e",
            "planned_start": START, "planned_end": planned_end, **extra}


def _shared_transactions(spent_outside_window=12000):
    """40,000 spent: 12,000 time early on, 8,000 expenses early on, 20,000 time in the window."""
    rows = [
        {"date": START, "kind": "budget", "amount": 100000, "approved": True, "hours": 500},
        {"date": "2026-01-10", "kind": "expense", "amount": 8000},
        {"date": "2026-01-15", "kind": "time", "amount": spent_outside_window},
    ]
    rows += [{"date": d, "kind": "time", "amount": 5000}
             for d in ("2026-02-08", "2026-02-15", "2026-02-22", "2026-03-01")]
    df = pd.DataFrame(rows)
    df["project_id"] = "10001-T"
    return df


def _time_entries(hours_in_window, total=200):
    """`total` hours used, of which `hours_in_window` fall in the last 28 days."""
    per_day = hours_in_window / 4
    rows = [{"date": "2026-01-15", "hours": total - hours_in_window, "approval": "approved"}]
    rows += [{"date": d, "hours": per_day, "approval": "approved"}
             for d in ("2026-02-08", "2026-02-15", "2026-02-22", "2026-03-01")]
    df = pd.DataFrame(rows)
    df["project_id"] = "10001-T"
    return df


def _assess(planned_end, tx=None, te=None):
    return assess_project(_project(planned_end), _shared_transactions() if tx is None else tx,
                          te, SETTINGS, AS_OF)


# %% settings %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def test_register_has_active_projects_section():
    path = Path(__file__).parent.parent / "config" / "audit_criteria.yaml"
    criteria = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert load_settings(criteria) == SETTINGS


def test_missing_section_is_a_clear_error():
    with pytest.raises(ValueError, match="active_projects"):
        load_settings({"version": "x"})


@pytest.mark.parametrize("duration, window, red", [
    (140, 28, 14.0),   # 20 weeks: window hits the 28-day cap
    (28, 7, 2.8),      # 4 weeks
    (7, 3, 1.0),       # 1-week CO project: window floor 3, red line floor 1
])
def test_window_and_red_line_scale_with_duration(duration, window, red):
    assert window_days(duration, SETTINGS) == window
    assert red_line_days(duration, SETTINGS) == pytest.approx(red)


# %% spec cases 1-6: dollars %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def test_shared_burn_numbers():
    r = _assess("2026-06-30")
    assert r["time_burn_wk"] == pytest.approx(5000)
    assert r["expense_burn_wk"] == pytest.approx(800)
    assert r["weekly_burn"] == pytest.approx(5800)
    assert r["remaining"] == pytest.approx(60000)
    assert r["runout_date"] == pd.Timestamp("2026-05-12")


def test_case1_runs_out_early_is_red():
    r = _assess("2026-06-30")
    assert r["days_early"] == 49
    assert r["red_line_days"] == pytest.approx(19.1)
    assert r["status"] == "Red"
    assert r["variance_at_planned_end"] == pytest.approx(-40257.14, abs=0.01)


def test_case2_on_track_is_green():
    r = _assess("2026-05-01")
    assert r["days_early"] == -11
    assert r["status"] == "Green"
    assert r["variance_at_planned_end"] == pytest.approx(9457.14, abs=0.01)


def test_case3_slightly_early_is_yellow():
    r = _assess("2026-05-20")
    assert r["days_early"] == 8
    assert r["red_line_days"] == pytest.approx(15)
    assert r["status"] == "Yellow"


def test_case4_pending_co_shown_but_not_counted():
    tx = pd.concat([_shared_transactions(), pd.DataFrame([{
        "project_id": "10001-T", "date": "2026-02-20", "kind": "change_order",
        "amount": 20000, "approved": False}])], ignore_index=True)
    r = _assess("2026-06-30", tx=tx)
    assert r["approved_budget"] == pytest.approx(100000)
    assert r["pending_co"] == pytest.approx(20000)
    assert r["runout_date"] == pd.Timestamp("2026-05-12")
    assert r["status"] == "Red"
    assert r["runout_if_pending_approved"] == pd.Timestamp("2026-06-05")


def test_case5_over_budget_is_red():
    r = _assess("2026-06-30", tx=_shared_transactions(spent_outside_window=77000))
    assert r["spent_to_date"] == pytest.approx(105000)
    assert r["remaining"] == pytest.approx(-5000)
    assert r["status"] == "Red"
    assert "over budget" in r["reason"]
    assert r["runout_date"] is None


def test_case6_travel_burst_outside_window_still_forecast():
    # no expenses in the last 28 days, but travel is averaged project-to-date
    assert _assess("2026-06-30")["expense_burn_wk"] == pytest.approx(800)


# %% spec cases 7-8: short project, rolled-up CO project %%%%%%%%%%%%%%%%%%%%%%%%%%

def test_case7_short_project_turns_red_where_fixed_rule_would_not():
    project = {"project_id": "20002-T", "planned_start": "2026-03-02", "planned_end": "2026-03-30"}
    tx = pd.DataFrame([
        {"date": "2026-03-02", "kind": "budget", "amount": 20000, "approved": True},
        {"date": "2026-03-04", "kind": "expense", "amount": 1000},
        {"date": "2026-03-05", "kind": "time", "amount": 6000},
        {"date": "2026-03-12", "kind": "time", "amount": 2500},
        {"date": "2026-03-16", "kind": "time", "amount": 2500},
    ])
    r = assess_project(project, tx, None, SETTINGS, "2026-03-16")
    assert r["window_days"] == 7
    assert r["weekly_burn"] == pytest.approx(5500)
    assert r["runout_date"] == pd.Timestamp("2026-03-26")
    assert r["days_early"] == 4
    assert r["red_line_days"] == pytest.approx(2.8)
    assert r["status"] == "Red"   # a fixed 14-day Red line would have said Yellow


def test_case8_rolled_up_co_project_merges_into_parent():
    projects = pd.DataFrame([
        {"project_id": "10001-T", "billing_type": "t_and_e", "planned_start": START,
         "planned_end": "2026-06-30", "parent_project_id": None, "roll_up": "no"},
        {"project_id": "10002-T", "billing_type": "t_and_e", "planned_start": "2026-02-15",
         "planned_end": "2026-03-01", "parent_project_id": "10001-T", "roll_up": "yes"},
    ])
    tx = pd.concat([_shared_transactions(), pd.DataFrame([{
        "project_id": "10002-T", "date": "2026-02-15", "kind": "budget",
        "amount": 10000, "approved": True}])], ignore_index=True)
    df = assess_portfolio(projects, tx, None, SETTINGS, AS_OF)
    assert len(df) == 1   # one family row, not two
    r = df.iloc[0]
    assert r["project_id"] == "10001-T"
    assert r["rolled_up"] == "10002-T"
    assert r["approved_budget"] == pytest.approx(110000)
    assert r["remaining"] == pytest.approx(70000)
    assert r["runout_date"] == pd.Timestamp("2026-05-24")
    assert r["days_early"] == 37
    assert r["status"] == "Red"


def test_linked_but_not_rolled_up_stays_separate():
    projects = pd.DataFrame([
        {"project_id": "10001-T", "planned_start": START, "planned_end": "2026-06-30",
         "parent_project_id": None, "roll_up": "no"},
        {"project_id": "10002-T", "planned_start": "2026-02-15", "planned_end": "2026-03-15",
         "parent_project_id": "10001-T", "roll_up": "no"},
    ])
    tx = pd.concat([_shared_transactions(), pd.DataFrame([{
        "project_id": "10002-T", "date": "2026-02-15", "kind": "budget",
        "amount": 10000, "approved": True}])], ignore_index=True)
    df = assess_portfolio(projects, tx, None, SETTINGS, AS_OF)
    assert set(df["project_id"]) == {"10001-T", "10002-T"}
    child = df[df["project_id"] == "10002-T"].iloc[0]
    assert child["parent_project_id"] == "10001-T"
    assert child["approved_budget"] == pytest.approx(10000)


# %% spec cases 9-10: hours %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def test_case9_hours_run_out_before_dollars():
    r = _assess("2026-06-30", te=_time_entries(hours_in_window=120))
    assert r["hours_burn_wk"] == pytest.approx(30)
    assert r["hours_remaining"] == pytest.approx(300)
    assert r["hours_runout_date"] == pd.Timestamp("2026-05-10")   # 2 days before the dollars
    assert r["hours_days_early"] == 51
    assert r["effective_rate"] == pytest.approx(166.67, abs=0.01)
    assert r["status"] == "Red"
    assert r["driver"] == "hours"   # both Red; hours run out first


def test_case10_hours_drive_status_when_dollars_are_green():
    r = _assess("2026-05-01", te=_time_entries(hours_in_window=160))
    assert r["hours_burn_wk"] == pytest.approx(40)
    assert r["hours_runout_date"] == pd.Timestamp("2026-04-22")
    assert r["hours_days_early"] == 9
    assert r["budget_status"] == "Green"
    assert r["hours_status"] == "Yellow"
    assert r["status"] == "Yellow"
    assert r["driver"] == "hours"
    assert r["effective_rate"] == pytest.approx(125)


# %% time-entry rules and edge cases %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def test_unapproved_hours_count_and_are_reported_rejected_never_count():
    te = pd.concat([_time_entries(hours_in_window=120), pd.DataFrame([
        {"project_id": "10001-T", "date": "2026-02-28", "hours": 10, "approval": "unapproved"},
        {"project_id": "10001-T", "date": "2026-02-28", "hours": 50, "approval": "rejected"},
    ])], ignore_index=True)
    r = _assess("2026-06-30", te=te)
    assert r["hours_used"] == pytest.approx(210)        # 200 approved + 10 unapproved
    assert r["unapproved_hours"] == pytest.approx(10)


def test_no_hours_budget_means_hours_not_measured():
    tx = _shared_transactions()
    tx["hours"] = None
    r = _assess("2026-06-30", tx=tx, te=_time_entries(120))
    assert r["hours_status"] == "Not measured"
    assert r["driver"] == "budget"
    assert "hours not measured" in r["reason"]


def test_missing_planned_end_needs_input():
    r = _assess(None)
    assert r["status"] == "Needs input"


def test_no_recent_spend_has_no_runout_and_stays_green():
    tx = pd.DataFrame([
        {"project_id": "10001-T", "date": START, "kind": "budget", "amount": 100000, "approved": True},
        {"project_id": "10001-T", "date": "2026-01-15", "kind": "time", "amount": 10000},
    ])
    project = _project("2026-06-30")
    r = assess_project(project, tx, None, SETTINGS, AS_OF)
    assert r["time_burn_wk"] == 0
    assert r["status"] == "Green"
    assert "no recent spend" in r["reason"]


def test_past_planned_end_is_red():
    r = _assess("2026-02-15")   # planned end before as_of, project still active
    assert r["status"] == "Red"
    assert "past planned end" in r["reason"]


def test_spend_after_as_of_is_ignored():
    tx = pd.concat([_shared_transactions(), pd.DataFrame([{
        "project_id": "10001-T", "date": "2026-03-10", "kind": "time", "amount": 99999}])],
        ignore_index=True)
    assert _assess("2026-06-30", tx=tx)["spent_to_date"] == pytest.approx(40000)


def test_portfolio_sorts_worst_first():
    projects = pd.DataFrame([
        {"project_id": "A", "planned_start": START, "planned_end": "2026-05-01"},   # Green
        {"project_id": "B", "planned_start": START, "planned_end": "2026-06-30"},   # Red
    ])
    tx = pd.concat([_shared_transactions().assign(project_id=p) for p in ("A", "B")],
                   ignore_index=True)
    df = assess_portfolio(projects, tx, None, SETTINGS, AS_OF)
    assert list(df["project_id"]) == ["B", "A"]
