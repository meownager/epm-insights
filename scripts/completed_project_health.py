#!/usr/bin/env python3
"""Completed Project Health Analysis Runner

Loads proposal and actual project CSV files, computes deviation metrics,
classifies project health, and writes outputs.

Status compatibility:
- Includes rows where status is 'completed' or 'closed' (case-insensitive).

Usage:
  python scripts/completed_project_health.py \
    --proposal data/sample/proposal_projects.csv \
    --actual data/sample/actual_projects.csv \
    --output-dir outputs
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Completed project health deviation analysis")
    parser.add_argument("--proposal", required=True, help="Path to proposal_projects.csv")
    parser.add_argument("--actual", required=True, help="Path to actual_projects.csv")
    parser.add_argument("--output-dir", default="outputs", help="Directory for report outputs")
    return parser.parse_args()


def _to_datetime(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def classify_health(row: pd.Series) -> str:
    budget_pct = abs(row.get("budget_dev_pct", 0.0) if pd.notna(row.get("budget_dev_pct")) else 0.0)
    hours_pct = abs(row.get("hours_dev_pct", 0.0) if pd.notna(row.get("hours_dev_pct")) else 0.0)
    schedule_days = row.get("schedule_dev_days", 0)
    schedule_days = 0 if pd.isna(schedule_days) else schedule_days

    if budget_pct <= 0.10 and hours_pct <= 0.10 and schedule_days <= 5:
        return "Green"
    if budget_pct <= 0.20 and hours_pct <= 0.20 and schedule_days <= 15:
        return "Yellow"
    return "Red"


def compute_metrics(proposal: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    merged = proposal.merge(actual, on="project_id", how="inner", suffixes=("_proposal", "_actual"))

    if "status" in merged.columns:
        status = merged["status"].fillna("").str.lower().str.strip()
        merged = merged[status.isin(["completed", "closed"])].copy()
    else:
        merged = merged.copy()

    merged = _to_datetime(
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

    merged["schedule_dev_days"] = (
        merged["actual_end_date"] - merged["proposed_end_date"]
    ).dt.days

    merged["proposed_duration_days"] = (
        merged["proposed_end_date"] - merged["proposed_start_date"]
    ).dt.days
    merged["actual_duration_days"] = (
        merged["actual_end_date"] - merged["actual_start_date"]
    ).dt.days

    merged["schedule_dev_pct"] = (
        (merged["actual_duration_days"] - merged["proposed_duration_days"])
        / merged["proposed_duration_days"].replace(0, pd.NA)
    )

    if "proposed_resource_count" in merged.columns and "actual_resource_count" in merged.columns:
        merged["resource_dev_abs"] = (
            merged["actual_resource_count"] - merged["proposed_resource_count"]
        )
        merged["resource_dev_pct"] = merged["resource_dev_abs"] / merged[
            "proposed_resource_count"
        ].replace(0, pd.NA)
    else:
        merged["resource_dev_abs"] = pd.NA
        merged["resource_dev_pct"] = pd.NA

    merged["health_status"] = merged.apply(classify_health, axis=1)

    return merged


def main() -> None:
    args = parse_args()

    proposal_path = Path(args.proposal)
    actual_path = Path(args.actual)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    proposal = pd.read_csv(proposal_path)
    actual = pd.read_csv(actual_path)

    metrics = compute_metrics(proposal, actual)

    detail_cols = [
        "project_id",
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
    ]

    detail = metrics[[c for c in detail_cols if c in metrics.columns]].copy()
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
