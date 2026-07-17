"""Quality scoring — anchored 1-4 category scores rolled up to 0-10.

Process Quality (0-10): EPM-entered category scores (1-4 against the rubric
anchors in config/quality_rubric.yaml), weighted by category tier, N/A excluded.

Outcome Performance (0-10): computed from audit metrics (budget/hours/schedule
deviations plus margin erosion) — no human input.

Scores input CSV format (one row per project-category):
    project_id,category,score,comments
    25718-F,Estimate,3,Matches PO
    25718-F,Celebration,na,Small project
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

DEFAULT_RUBRIC_PATH = Path(__file__).parent.parent / "config" / "quality_rubric.yaml"


def load_rubric(path: Path = DEFAULT_RUBRIC_PATH) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ── Process Quality (rubric rollup) ─────────────────────────────────────────

def process_quality_score(scores: pd.DataFrame, rubric: dict) -> pd.DataFrame:
    """Roll up per-category 1-4 scores into a weighted 0-10 per project.

    scores: columns project_id, category, score (1-4, or blank/na for N/A).
    Returns one row per project: process_score_10, band, categories_scored,
    categories_na, unknown_categories.
    """
    weights = {c["name"].strip().lower(): c["weight"] for c in rubric["categories"]}
    bands = rubric.get("bands", {"strong": 8.5, "adequate": 7.0})

    rows = []
    for pid, grp in scores.groupby("project_id"):
        w_score = w_possible = 0.0
        n_scored = n_na = 0
        unknown = []
        for _, r in grp.iterrows():
            cat = str(r["category"]).strip().lower()
            if cat not in weights:
                unknown.append(str(r["category"]).strip())
                continue
            raw = str(r.get("score", "")).strip().lower()
            if raw in ("", "na", "n/a", "nan", "none"):
                n_na += 1
                continue
            val = pd.to_numeric(raw, errors="coerce")
            if pd.isna(val) or not (1 <= val <= 4):
                unknown.append(f"{r['category']} (bad score: {r.get('score')})")
                continue
            w = weights[cat]
            w_score += float(val) * w
            w_possible += 4.0 * w
            n_scored += 1

        score10 = round(w_score / w_possible * 10, 2) if w_possible else None
        if score10 is None:
            band = "Not Scored"
        elif score10 >= bands["strong"]:
            band = "Strong"
        elif score10 >= bands["adequate"]:
            band = "Adequate"
        else:
            band = "Needs Improvement"

        rows.append({
            "project_id": pid,
            "process_score_10": score10,
            "process_band": band,
            "categories_scored": n_scored,
            "categories_na": n_na,
            "unknown_categories": "; ".join(unknown),
        })
    return pd.DataFrame(rows)


# ── Outcome Performance (computed) ──────────────────────────────────────────

def _metric_credit(value: float | None, green_max: float, yellow_max: float) -> float | None:
    """1.0 within green, 0.5 within yellow, 0.0 beyond. None if not measurable."""
    if value is None or pd.isna(value):
        return None
    v = abs(value)
    if v <= green_max:
        return 1.0
    if v <= yellow_max:
        return 0.5
    return 0.0


def outcome_score(
    metrics_row: pd.Series,
    criteria: dict,
    rubric: dict,
    financials_row: pd.Series | None = None,
) -> dict:
    """Compute the 0-10 Outcome Performance score for one audited project.

    metrics_row: a row from the audit engine output (has *_dev_pct / schedule_dev_days
    and billing_type). financials_row: optional row from project_financials.csv
    (adds margin erosion). Metrics that can't be measured are excluded from the
    weighted average rather than counted as perfect.
    """
    cfg = rubric["outcome_score"]
    weights = cfg["weights"]
    cp = criteria["completed_projects"]
    bt = str(metrics_row.get("billing_type", "fixed_fee")).strip().lower()
    if bt not in cp:
        bt = "fixed_fee"
    th = cp[bt]

    credits: dict[str, float | None] = {
        "budget": _metric_credit(
            metrics_row.get("budget_dev_pct"),
            th["budget"]["green_max"], th["budget"]["yellow_max"],
        ),
        "hours": _metric_credit(
            metrics_row.get("hours_dev_pct"),
            th["hours"]["green_max"], th["hours"]["yellow_max"],
        ),
        "schedule": _metric_credit(
            metrics_row.get("schedule_dev_days"),
            th["schedule"]["green_max_days"], th["schedule"]["yellow_max_days"],
        ),
        "margin": None,
    }

    if financials_row is not None:
        planned = pd.to_numeric(financials_row.get("planned_margin_pct"), errors="coerce")
        actual = pd.to_numeric(financials_row.get("actual_margin_pct"), errors="coerce")
        reliability = str(financials_row.get("margin_reliability", ""))
        if pd.notna(planned) and pd.notna(actual) and reliability == "full":
            erosion = max(0.0, float(planned) - float(actual))
            credits["margin"] = _metric_credit(
                erosion, cfg["margin_erosion_green_max"], cfg["margin_erosion_yellow_max"],
            )

    total_w = sum(weights[m] for m, c in credits.items() if c is not None)
    if total_w == 0:
        return {"outcome_score_10": None, "outcome_metrics_used": ""}
    weighted = sum(weights[m] * c for m, c in credits.items() if c is not None)
    used = ", ".join(m for m, c in credits.items() if c is not None)
    return {
        "outcome_score_10": round(weighted / total_w * 10, 2),
        "outcome_metrics_used": used,
    }


def score_portfolio(
    metrics: pd.DataFrame,
    criteria: dict,
    rubric: dict,
    financials: pd.DataFrame | None = None,
    scores: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Full scoring pass: Outcome for every audited project, Process where scores exist."""
    fin_idx = financials.set_index("project_id") if financials is not None else None

    out_rows = []
    for _, m in metrics.iterrows():
        pid = m["project_id"]
        fin_row = None
        if fin_idx is not None and pid in fin_idx.index:
            fin_row = fin_idx.loc[pid]
        out_rows.append({"project_id": pid, **outcome_score(m, criteria, rubric, fin_row)})
    result = pd.DataFrame(out_rows)

    if scores is not None and not scores.empty:
        proc = process_quality_score(scores, rubric)
        result = result.merge(proc, on="project_id", how="left")
    else:
        result["process_score_10"] = None
        result["process_band"] = "Not Scored"

    def quadrant(r):
        o, p = r.get("outcome_score_10"), r.get("process_score_10")
        if pd.isna(o) or pd.isna(p):
            return ""
        good_o, good_p = o >= 7.0, p >= 7.0
        if good_o and good_p:
            return "Model project"
        if good_o and not good_p:
            return "Good result, risky process"
        if not good_o and good_p:
            return "Good process, estimate problem"
        return "Systemic problem"

    result["quadrant"] = result.apply(quadrant, axis=1)
    return result
