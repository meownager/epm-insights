"""Known-answer tests for quality scoring (process rollup + outcome score)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from quality_scoring import (
    load_rubric,
    outcome_score,
    process_quality_score,
    score_portfolio,
)

RUBRIC = load_rubric()

CRITERIA = {
    "completed_projects": {
        "fixed_fee": {
            "budget": {"green_max": 0.15, "yellow_max": 0.30},
            "hours": {"green_max": 0.15, "yellow_max": 0.30},
            "schedule": {"green_max_days": 7, "yellow_max_days": 21},
        },
        "t_and_e": {
            "budget": {"green_max": 0.25, "yellow_max": 0.40},
            "hours": {"green_max": 0.15, "yellow_max": 0.30},
            "schedule": {"green_max_days": 7, "yellow_max_days": 21},
        },
    }
}


def _scores(rows):
    return pd.DataFrame(rows, columns=["project_id", "category", "score", "comments"])


# ── process quality rollup ───────────────────────────────────────────────────

def test_all_fours_scores_ten():
    rows = [["P1", c["name"], 4, ""] for c in RUBRIC["categories"]]
    res = process_quality_score(_scores(rows), RUBRIC)
    assert res["process_score_10"].iloc[0] == 10.0
    assert res["process_band"].iloc[0] == "Strong"


def test_all_ones_scores_two_point_five():
    rows = [["P1", c["name"], 1, ""] for c in RUBRIC["categories"]]
    res = process_quality_score(_scores(rows), RUBRIC)
    assert res["process_score_10"].iloc[0] == 2.5
    assert res["process_band"].iloc[0] == "Needs Improvement"


def test_celebration_removed_from_rubric():
    names = [c["name"] for c in RUBRIC["categories"]]
    assert "Celebration" not in names
    assert len(names) == 16


def test_na_excluded_from_rollup():
    # all 4s except one category marked na → still a perfect 10
    rows = [["P1", c["name"], "na" if c["name"] == "BoM" else 4, ""]
            for c in RUBRIC["categories"]]
    res = process_quality_score(_scores(rows), RUBRIC)
    assert res["process_score_10"].iloc[0] == 10.0
    assert res["categories_na"].iloc[0] == 1
    assert res["categories_scored"].iloc[0] == 15


def test_weights_matter():
    # 4 on a critical (weight 3) category and 1 on a standard (weight 1) category
    # → weighted better than the reverse
    high_crit = _scores([["P1", "Estimate", 4, ""], ["P1", "Closeout sent to customer", 1, ""]])
    low_crit = _scores([["P1", "Estimate", 1, ""], ["P1", "Closeout sent to customer", 4, ""]])
    hi = process_quality_score(high_crit, RUBRIC)["process_score_10"].iloc[0]
    lo = process_quality_score(low_crit, RUBRIC)["process_score_10"].iloc[0]
    assert hi > lo


def test_unknown_category_reported_not_crashed():
    res = process_quality_score(_scores([["P1", "Nonsense Category", 4, ""]]), RUBRIC)
    assert "Nonsense Category" in res["unknown_categories"].iloc[0]


def test_category_match_case_insensitive():
    res = process_quality_score(_scores([["P1", "estimate", 4, ""]]), RUBRIC)
    assert res["process_score_10"].iloc[0] == 10.0


# ── outcome score ────────────────────────────────────────────────────────────

def _metrics_row(budget=0.05, hours=0.05, days=2, billing="fixed_fee"):
    return pd.Series({
        "project_id": "P1",
        "budget_dev_pct": budget,
        "hours_dev_pct": hours,
        "schedule_dev_days": days,
        "billing_type": billing,
    })


def test_outcome_all_green_is_ten():
    res = outcome_score(_metrics_row(), CRITERIA, RUBRIC)
    assert res["outcome_score_10"] == 10.0


def test_outcome_all_beyond_yellow_is_zero():
    res = outcome_score(_metrics_row(budget=0.5, hours=0.5, days=60), CRITERIA, RUBRIC)
    assert res["outcome_score_10"] == 0.0


def test_outcome_yellow_gives_half_credit():
    res = outcome_score(_metrics_row(budget=0.2, hours=0.2, days=10), CRITERIA, RUBRIC)
    assert res["outcome_score_10"] == 5.0


def test_outcome_uses_billing_type_thresholds():
    # 20% budget: yellow for fixed_fee, green for t_and_e
    ff = outcome_score(_metrics_row(budget=0.2), CRITERIA, RUBRIC)
    te = outcome_score(_metrics_row(budget=0.2, billing="t_and_e"), CRITERIA, RUBRIC)
    assert te["outcome_score_10"] > ff["outcome_score_10"]


def test_outcome_margin_included_only_when_reliable():
    fin_full = pd.Series({"planned_margin_pct": 0.30, "actual_margin_pct": 0.10,
                          "margin_reliability": "full"})
    fin_partial = pd.Series({"planned_margin_pct": 0.30, "actual_margin_pct": 0.10,
                             "margin_reliability": "partial_hours_overstated"})
    with_margin = outcome_score(_metrics_row(), CRITERIA, RUBRIC, fin_full)
    without = outcome_score(_metrics_row(), CRITERIA, RUBRIC, fin_partial)
    assert "margin" in with_margin["outcome_metrics_used"]
    assert "margin" not in without["outcome_metrics_used"]
    # 20-point erosion is beyond yellow (15) → drags score below the no-margin case
    assert with_margin["outcome_score_10"] < without["outcome_score_10"]


def test_outcome_missing_metrics_excluded_not_perfect():
    row = _metrics_row()
    row["hours_dev_pct"] = float("nan")
    res = outcome_score(row, CRITERIA, RUBRIC)
    assert "hours" not in res["outcome_metrics_used"]
    assert res["outcome_score_10"] == 10.0  # remaining metrics all green


# ── portfolio + quadrants ────────────────────────────────────────────────────

def test_quadrant_labels():
    metrics = pd.DataFrame([
        {"project_id": "GOOD", "budget_dev_pct": 0.05, "hours_dev_pct": 0.05,
         "schedule_dev_days": 1, "billing_type": "fixed_fee"},
        {"project_id": "BAD", "budget_dev_pct": 0.50, "hours_dev_pct": 0.50,
         "schedule_dev_days": 60, "billing_type": "fixed_fee"},
    ])
    scores = _scores(
        [["GOOD", c["name"], 4, ""] for c in RUBRIC["categories"]] +
        [["BAD", c["name"], 1, ""] for c in RUBRIC["categories"]]
    )
    res = score_portfolio(metrics, CRITERIA, RUBRIC, scores=scores).set_index("project_id")
    assert res.loc["GOOD", "quadrant"] == "Model project"
    assert res.loc["BAD", "quadrant"] == "Systemic problem"


def test_portfolio_without_scores_still_outcomes():
    metrics = pd.DataFrame([
        {"project_id": "P1", "budget_dev_pct": 0.05, "hours_dev_pct": 0.05,
         "schedule_dev_days": 1, "billing_type": "t_and_e"},
    ])
    res = score_portfolio(metrics, CRITERIA, RUBRIC)
    assert res["outcome_score_10"].iloc[0] == 10.0
    assert res["process_band"].iloc[0] == "Not Scored"
