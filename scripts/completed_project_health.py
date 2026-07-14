#!/usr/bin/env python3
"""Completed Project Health Analysis Runner.

Loads proposed baseline and actual outcome CSV files, computes deviation
metrics, classifies advisory health, and writes CSV outputs.
Thresholds are read from config/audit_criteria.yaml (the Audit Criteria Register).
Health classification uses billing-type-specific thresholds (fixed_fee vs t_and_e).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml


REQUIRED_PROPOSAL_COLUMNS = {
    "project_id",
    "proposed_budget",
    "proposed_hours",
    "proposed_start_date",
    "proposed_end_date",
    "billing_type",
}

REQUIRED_ACTUAL_COLUMNS = {
    "project_id",
    "actual_budget",
    "actual_hours",
    "actual_start_date",
    "actual_end_date",
    "status",
}

DEFAULT_CRITERIA_PATH = Path(__file__).parent.parent / "config" / "audit_criteria.yaml"


def load_criteria(criteria_path: Path) -> dict:
    with open(criteria_path, "r") as f:
        return yaml.safe_load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Completed project health deviation analysis")
    parser.add_argument("--proposal", required=True, help="Path to proposal_projects.csv")
    parser.add_argument("--actual", required=True, help="Path to actual_projects.csv")
    parser.add_argument("--output-dir", default="outputs", help="Directory for report outputs")
    parser.add_argument(
        "--criteria",
        default=str(DEFAULT_CRITERIA_PATH),
        help="Path to audit_criteria.yaml (Audit Criteria Register)",
    )
    return parser.parse_args()


def validate_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def to_datetime(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def get_billing_thresholds(billing_type: str, criteria: dict) -> dict:
    cp = criteria["completed_projects"]
    bt_key = (billing_type or "").lower().strip()
    if bt_key not in cp:
        bt_key = "fixed_fee"  # conservative default
    bt = cp[bt_key]
    return {
        "green_pct": bt["budget"]["green_max"],
        "yellow_pct": bt["budget"]["yellow_max"],
        "green_hours_pct": bt["hours"]["green_max"],
        "yellow_hours_pct": bt["hours"]["yellow_max"],
        "green_days": bt["schedule"]["green_max_days"],
        "yellow_days": bt["schedule"]["yellow_max_days"],
    }


def classify_health(
    row: pd.Series,
    green_pct: float,
    yellow_pct: float,
    green_days: int,
    yellow_days: int,
    green_hours_pct: float | None = None,
    yellow_hours_pct: float | None = None,
) -> str:
    if green_hours_pct is None:
        green_hours_pct = green_pct
    if yellow_hours_pct is None:
        yellow_hours_pct = yellow_pct

    budget_pct = abs(row["budget_dev_pct"]) if pd.notna(row["budget_dev_pct"]) else 0.0
    hours_pct = abs(row["hours_dev_pct"]) if pd.notna(row["hours_dev_pct"]) else 0.0
    schedule_days = row["schedule_dev_days"] if pd.notna(row["schedule_dev_days"]) else 0

    if budget_pct <= green_pct and hours_pct <= green_hours_pct and schedule_days <= green_days:
        return "Green"
    if budget_pct <= yellow_pct and hours_pct <= yellow_hours_pct and schedule_days <= yellow_days:
        return "Yellow"
    return "Red"


def _classify_row(row: pd.Series, criteria: dict) -> str:
    billing_type = row.get("billing_type", "fixed_fee") or "fixed_fee"
    thresholds = get_billing_thresholds(billing_type, criteria)
    return classify_health(row, **thresholds)


def build_finding(row: pd.Series) -> str:
    findings: list[str] = []

    if pd.notna(row["budget_dev_pct"]):
        findings.append(f"budget deviation {row['budget_dev_pct']:.1%}")
    if pd.notna(row["hours_dev_pct"]):
        findings.append(f"hours deviation {row['hours_dev_pct']:.1%}")
    if pd.notna(row["schedule_dev_days"]):
        findings.append(f"schedule deviation {int(row['schedule_dev_days'])} days")

    if not findings:
        return "Review required because core deviation metrics could not be calculated."

    return "; ".join(findings)


def compute_metrics(
    proposal: pd.DataFrame,
    actual: pd.DataFrame,
    criteria: dict,
    eligible_statuses: set[str] | None = None,
) -> pd.DataFrame:
    if eligible_statuses is None:
        eligible_statuses = {"completed", "closed"}

    validate_columns(proposal, REQUIRED_PROPOSAL_COLUMNS, "proposal file")
    validate_columns(actual, REQUIRED_ACTUAL_COLUMNS, "actual file")

    merged = proposal.merge(actual, on="project_id", how="inner", suffixes=("_proposal", "_actual"))
    status = merged["status"].fillna("").str.lower().str.strip()
    merged = merged[status.isin(eligible_statuses)].copy()

    merged = to_datetime(
        merged,
        [
            "proposed_start_date",
            "proposed_end_date",
            "actual_start_date",
            "actual_end_date",
        ],
    )

    merged["budget_dev_abs"] = merged["actual_budget"] - merged["proposed_budget"]
    merged["budget_dev_pct"] = merged["budget_dev_abs"] / merged["proposed_budget"].replace(0, pd.NA)

    merged["hours_dev_abs"] = merged["actual_hours"] - merged["proposed_hours"]
    merged["hours_dev_pct"] = merged["hours_dev_abs"] / merged["proposed_hours"].replace(0, pd.NA)

    merged["schedule_dev_days"] = (merged["actual_end_date"] - merged["proposed_end_date"]).dt.days
    merged["proposed_duration_days"] = (
        merged["proposed_end_date"] - merged["proposed_start_date"]
    ).dt.days
    merged["actual_duration_days"] = (merged["actual_end_date"] - merged["actual_start_date"]).dt.days
    merged["schedule_dev_pct"] = (
        (merged["actual_duration_days"] - merged["proposed_duration_days"])
        / merged["proposed_duration_days"].replace(0, pd.NA)
    )

    if "proposed_resource_count" in merged.columns and "actual_resource_count" in merged.columns:
        merged["resource_dev_abs"] = (
            merged["actual_resource_count"] - merged["proposed_resource_count"]
        )
        merged["resource_dev_pct"] = (
            merged["resource_dev_abs"] / merged["proposed_resource_count"].replace(0, pd.NA)
        )
    else:
        merged["resource_dev_abs"] = pd.NA
        merged["resource_dev_pct"] = pd.NA

    if merged.empty:
        merged["health_status"] = pd.Series(dtype=str)
        merged["audit_finding"] = pd.Series(dtype=str)
    else:
        merged["health_status"] = merged.apply(_classify_row, axis=1, criteria=criteria)
        merged["audit_finding"] = merged.apply(build_finding, axis=1)

    return merged


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    criteria = load_criteria(Path(args.criteria))
    cp = criteria["completed_projects"]
    eligible_statuses = set(cp.get("eligible_statuses", ["completed", "closed"]))

    criteria_version = criteria.get("version", "unknown")
    print(f"Audit Criteria Register v{criteria_version} loaded from: {args.criteria}")

    proposal = pd.read_csv(args.proposal)
    actual = pd.read_csv(args.actual)

    metrics = compute_metrics(
        proposal=proposal,
        actual=actual,
        criteria=criteria,
        eligible_statuses=eligible_statuses,
    )

    detail_cols = [
        "project_id",
        "project_name",
        "client",
        "project_manager",
        "project_type",
        "billing_type",
        "proposed_budget",
        "actual_budget",
        "budget_dev_abs",
        "budget_dev_pct",
        "proposed_hours",
        "actual_hours",
        "hours_dev_abs",
        "hours_dev_pct",
        "proposed_start_date",
        "proposed_end_date",
        "actual_start_date",
        "actual_end_date",
        "schedule_dev_days",
        "proposed_duration_days",
        "actual_duration_days",
        "schedule_dev_pct",
        "proposed_resource_count",
        "actual_resource_count",
        "resource_dev_abs",
        "resource_dev_pct",
        "health_status",
        "audit_finding",
        "closeout_notes",
    ]
    detail = metrics[[col for col in detail_cols if col in metrics.columns]].copy()

    detail_out = output_dir / "completed_project_health_detail.csv"
    detail.to_csv(detail_out, index=False)

    summary = (
        detail.groupby("health_status", dropna=False)
        .size()
        .rename("project_count")
        .reset_index()
        .sort_values("health_status")
    )
    summary_out = output_dir / "completed_project_health_summary.csv"
    summary.to_csv(summary_out, index=False)

    print("Completed Project Health Analysis complete.")
    print(f"Detail report: {detail_out}")
    print(f"Summary report: {summary_out}")


if __name__ == "__main__":
    main()
