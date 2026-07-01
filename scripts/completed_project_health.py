#!/usr/bin/env python3
"""Completed Project Health Analysis Runner.

Loads proposed baseline and actual outcome CSV files, computes deviation
metrics, classifies advisory health, and writes CSV outputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REQUIRED_PROPOSAL_COLUMNS = {
    "project_id",
    "proposed_budget",
    "proposed_hours",
    "proposed_start_date",
    "proposed_end_date",
}

REQUIRED_ACTUAL_COLUMNS = {
    "project_id",
    "actual_budget",
    "actual_hours",
    "actual_start_date",
    "actual_end_date",
    "status",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Completed project health deviation analysis")
    parser.add_argument("--proposal", required=True, help="Path to proposal_projects.csv")
    parser.add_argument("--actual", required=True, help="Path to actual_projects.csv")
    parser.add_argument("--output-dir", default="outputs", help="Directory for report outputs")
    parser.add_argument("--green-pct", type=float, default=0.15, help="Green variance threshold")
    parser.add_argument("--yellow-pct", type=float, default=0.30, help="Yellow variance threshold")
    parser.add_argument("--green-days", type=int, default=7, help="Green schedule slip threshold")
    parser.add_argument("--yellow-days", type=int, default=21, help="Yellow schedule slip threshold")
    return parser.parse_args()


def validate_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def to_datetime(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def classify_health(
    row: pd.Series,
    green_pct: float,
    yellow_pct: float,
    green_days: int,
    yellow_days: int,
) -> str:
    budget_pct = abs(row["budget_dev_pct"]) if pd.notna(row["budget_dev_pct"]) else 0.0
    hours_pct = abs(row["hours_dev_pct"]) if pd.notna(row["hours_dev_pct"]) else 0.0
    schedule_days = row["schedule_dev_days"] if pd.notna(row["schedule_dev_days"]) else 0

    if budget_pct <= green_pct and hours_pct <= green_pct and schedule_days <= green_days:
        return "Green"
    if budget_pct <= yellow_pct and hours_pct <= yellow_pct and schedule_days <= yellow_days:
        return "Yellow"
    return "Red"


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
    green_pct: float,
    yellow_pct: float,
    green_days: int,
    yellow_days: int,
) -> pd.DataFrame:
    validate_columns(proposal, REQUIRED_PROPOSAL_COLUMNS, "proposal file")
    validate_columns(actual, REQUIRED_ACTUAL_COLUMNS, "actual file")

    merged = proposal.merge(actual, on="project_id", how="inner", suffixes=("_proposal", "_actual"))
    status = merged["status"].fillna("").str.lower().str.strip()
    merged = merged[status.isin(["completed", "closed"])].copy()

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

    merged["health_status"] = merged.apply(
        classify_health,
        axis=1,
        green_pct=green_pct,
        yellow_pct=yellow_pct,
        green_days=green_days,
        yellow_days=yellow_days,
    )
    merged["audit_finding"] = merged.apply(build_finding, axis=1)

    return merged


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    proposal = pd.read_csv(args.proposal)
    actual = pd.read_csv(args.actual)

    metrics = compute_metrics(
        proposal=proposal,
        actual=actual,
        green_pct=args.green_pct,
        yellow_pct=args.yellow_pct,
        green_days=args.green_days,
        yellow_days=args.yellow_days,
    )

    detail_cols = [
        "project_id",
        "project_name",
        "client",
        "project_manager",
        "project_type",
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
