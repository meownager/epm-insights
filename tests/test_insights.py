"""Known-answer tests for the Phase 5 insights engine."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from insights import (
    analyse_patterns,
    build_notes_index,
    check_ollama,
    search_notes,
)


CRITERIA = {
    "completed_projects": {
        "fixed_fee": {
            "budget":   {"green_max": 0.15, "yellow_max": 0.30},
            "hours":    {"green_max": 0.15, "yellow_max": 0.30},
            "schedule": {"green_max_days": 7, "yellow_max_days": 21},
        },
        "t_and_e": {
            "budget":   {"green_max": 0.25, "yellow_max": 0.40},
            "hours":    {"green_max": 0.15, "yellow_max": 0.30},
            "schedule": {"green_max_days": 7, "yellow_max_days": 21},
        },
    }
}


def _make_metrics(**overrides) -> pd.DataFrame:
    base = {
        "project_id":        "P001",
        "project_name":      "Test Project",
        "project_manager":   "A. Smith",
        "client":            "Acme Corp",
        "billing_type":      "fixed_fee",
        "health_status":     "Green",
        "budget_dev_abs":    5_000,
        "budget_dev_pct":    0.05,
        "hours_dev_abs":     50,
        "hours_dev_pct":     0.05,
        "schedule_dev_days": 3,
        "closeout_notes":    "Smooth delivery.",
    }
    base.update(overrides)
    return pd.DataFrame([base])


def test_patterns_returns_list():
    assert isinstance(analyse_patterns(_make_metrics(), CRITERIA), list)


def test_patterns_empty_df_returns_empty():
    assert analyse_patterns(pd.DataFrame(), CRITERIA) == []


def test_overview_finding_always_present():
    titles = [f.title for f in analyse_patterns(_make_metrics(), CRITERIA)]
    assert "Portfolio Health Overview" in titles


def test_margin_exposure_finding_for_red_fixed_fee_overrun():
    df = _make_metrics(health_status="Red", billing_type="fixed_fee",
                       budget_dev_abs=50_000, budget_dev_pct=0.35)
    titles = [f.title for f in analyse_patterns(df, CRITERIA)]
    assert "Margin Exposure — Red Fixed-Fee Overruns" in titles


def test_no_margin_exposure_for_red_t_and_e():
    df = _make_metrics(health_status="Red", billing_type="t_and_e",
                       budget_dev_abs=50_000, budget_dev_pct=0.35)
    titles = [f.title for f in analyse_patterns(df, CRITERIA)]
    assert "Margin Exposure — Red Fixed-Fee Overruns" not in titles


def test_scope_finding_triggers_on_keyword_without_change_order():
    df = _make_metrics(health_status="Red", budget_dev_pct=0.35,
                       closeout_notes="Scope grew from four to seven compressors after kickoff.")
    titles = [f.title for f in analyse_patterns(df, CRITERIA)]
    assert "Potential Scope Growth Without Change Order" in titles


def test_scope_finding_not_triggered_when_change_order_present():
    df = _make_metrics(health_status="Red", budget_dev_pct=0.35,
                       closeout_notes="Scope expanded; change order raised and approved.")
    titles = [f.title for f in analyse_patterns(df, CRITERIA)]
    assert "Potential Scope Growth Without Change Order" not in titles


def test_scope_finding_not_triggered_for_green_project():
    df = _make_metrics(health_status="Green", budget_dev_pct=0.05,
                       closeout_notes="Scope grew slightly but within budget.")
    titles = [f.title for f in analyse_patterns(df, CRITERIA)]
    assert "Potential Scope Growth Without Change Order" not in titles


def test_pm_finding_identifies_worst_pm():
    rows = [
        {"project_id": "P001", "project_name": "A", "project_manager": "B. Jones",
         "client": "X", "billing_type": "fixed_fee", "health_status": "Red",
         "budget_dev_abs": 0, "budget_dev_pct": 0.35, "hours_dev_pct": 0.10,
         "schedule_dev_days": 5, "closeout_notes": ""},
        {"project_id": "P002", "project_name": "B", "project_manager": "B. Jones",
         "client": "Y", "billing_type": "fixed_fee", "health_status": "Red",
         "budget_dev_abs": 0, "budget_dev_pct": 0.35, "hours_dev_pct": 0.10,
         "schedule_dev_days": 5, "closeout_notes": ""},
        {"project_id": "P003", "project_name": "C", "project_manager": "C. Lee",
         "client": "Z", "billing_type": "fixed_fee", "health_status": "Green",
         "budget_dev_abs": 0, "budget_dev_pct": 0.05, "hours_dev_pct": 0.05,
         "schedule_dev_days": 2, "closeout_notes": ""},
    ]
    findings = analyse_patterns(pd.DataFrame(rows), CRITERIA)
    pm_finding = next((f for f in findings if "PM with Most" in f.title), None)
    assert pm_finding is not None
    assert "B. Jones" in pm_finding.body


def test_finding_severity_critical_for_high_red_rate():
    rows = [
        {"project_id": f"P{i:03d}", "project_name": f"Proj {i}",
         "project_manager": "A", "client": "X", "billing_type": "fixed_fee",
         "health_status": "Red", "budget_dev_abs": 0, "budget_dev_pct": 0.35,
         "hours_dev_pct": 0.10, "schedule_dev_days": 5, "closeout_notes": ""}
        for i in range(4)
    ]
    findings = analyse_patterns(pd.DataFrame(rows), CRITERIA)
    overview = next(f for f in findings if f.title == "Portfolio Health Overview")
    assert overview.severity == "critical"


def _notes_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"project_id": "P001", "project_name": "Alpha", "health_status": "Red",
         "closeout_notes": "Vendor firmware defect caused six week delay on site acceptance."},
        {"project_id": "P002", "project_name": "Beta",  "health_status": "Yellow",
         "closeout_notes": "Robot reach issue found at FAT required new gripper design."},
        {"project_id": "P003", "project_name": "Gamma", "health_status": "Green",
         "closeout_notes": "Smooth commissioning, delivered under budget and on schedule."},
    ])


def test_build_notes_index_returns_index():
    idx = build_notes_index(_notes_df())
    assert idx is not None
    assert len(idx.project_ids) == 3


def test_search_notes_returns_most_relevant():
    df = _notes_df()
    idx = build_notes_index(df)
    results = search_notes("vendor firmware delay", idx, df, top_k=1)
    assert len(results) == 1
    assert results[0]["project_id"] == "P001"


def test_search_notes_respects_top_k():
    df = _notes_df()
    idx = build_notes_index(df)
    assert len(search_notes("project", idx, df, top_k=2)) <= 2


def test_search_notes_score_between_zero_and_one():
    df = _notes_df()
    idx = build_notes_index(df)
    for r in search_notes("gripper robot", idx, df, top_k=3):
        assert 0.0 <= r["score"] <= 1.0


def test_build_notes_index_returns_none_for_empty_df():
    df = pd.DataFrame(columns=["project_id", "closeout_notes"])
    assert build_notes_index(df) is None


def test_check_ollama_returns_empty_when_not_running():
    assert check_ollama("http://localhost:19999") == []


def test_check_ollama_returns_list():
    assert isinstance(check_ollama("http://localhost:19999"), list)