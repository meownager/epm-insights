#!/usr/bin/env python3
"""Active Projects audit: one command, portfolio table + run record.

Sample data (standard schema, no real data needed):
    python scripts/run_active_audit.py

Real IES exports (one subfolder per project under data/real/, plus the
EPM-entered active_projects.csv with planned dates):
    python scripts/run_active_audit.py --ies-dir data/real --projects data/real/active_projects.csv --output outputs/real/active --store data/real/portfolio_store

Writes to --output:
    active_portfolio.csv     one row per active project, worst first
    runs/run_<id>_<ts>.json  run record: criteria version, input fingerprints, status counts
With --store, also appends each project's status to the portfolio store so the
dashboard can show the date a project first turned Yellow or Red.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from active_ies_adapter import coverage_warnings, load_ies_folder
from active_project_health import assess_portfolio, load_settings
from completed_project_health import load_criteria, sha256_file
from portfolio_store import first_crossings, record_active_status

ROOT = Path(__file__).parent.parent
SAMPLE = ROOT / "data" / "sample"


def run(projects: pd.DataFrame, transactions: pd.DataFrame, time_entries: pd.DataFrame | None,
        criteria: dict, as_of=None) -> pd.DataFrame:
    """Engine + per-project coverage warnings, as one table."""
    results = assess_portfolio(projects, transactions, time_entries, load_settings(criteria), as_of)
    gaps = coverage_warnings(projects, transactions, time_entries)
    results["warning"] = results["project_id"].map(gaps).fillna("")
    return results


def write_run_record(output_dir: Path, criteria: dict, criteria_path: Path,
                     input_paths: list[Path], results: pd.DataFrame) -> Path:
    """Same mechanism as the closed-projects audit: who/what/when, fingerprinted."""
    run_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc)
    record = {
        "run_id": run_id,
        "audit": "active_projects",
        "timestamp": ts.isoformat(),
        "criteria_version": criteria.get("version", "unknown"),
        "criteria_fingerprint": sha256_file(criteria_path),
        "as_of_date": str(pd.Timestamp(results["as_of_date"].iloc[0]).date()) if len(results) else None,
        "inputs": {str(p): sha256_file(p) for p in input_paths},
        "project_count": len(results),
        "status_summary": results["status"].value_counts().to_dict(),
    }
    runs = output_dir / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    out = runs / f"run_{run_id[:8]}_{ts:%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(record, indent=2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--projects", default=SAMPLE / "active_projects.csv", type=Path)
    ap.add_argument("--transactions", default=SAMPLE / "active_transactions.csv", type=Path)
    ap.add_argument("--time-entries", default=SAMPLE / "active_time_entries.csv", type=Path)
    ap.add_argument("--ies-dir", type=Path, help="folder of per-project IES exports (replaces --transactions/--time-entries)")
    ap.add_argument("--criteria", default=ROOT / "config" / "audit_criteria.yaml", type=Path)
    ap.add_argument("--as-of", help="YYYY-MM-DD; default is the latest date in the inputs")
    ap.add_argument("--output", default=ROOT / "outputs" / "sample" / "active", type=Path)
    ap.add_argument("--store", type=Path, help="portfolio store folder for first-crossing history")
    args = ap.parse_args()

    criteria = load_criteria(args.criteria)
    projects = pd.read_csv(args.projects, dtype={"planned_end": str, "parent_project_id": str})

    if args.ies_dir:
        transactions, time_entries, reports = load_ies_folder(args.ies_dir)
        inputs = [args.projects] + sorted(f for f in args.ies_dir.rglob("*") if f.is_file()
                                          and f.suffix.lower() in (".xls", ".xlsx", ".csv")
                                          and "portfolio_store" not in f.parts)
        for r in reports:
            print(r.summary)
            for w in r.warnings:
                print(f"  WARNING: {w}")
    else:
        transactions = pd.read_csv(args.transactions)
        time_entries = pd.read_csv(args.time_entries) if args.time_entries.exists() else None
        inputs = [args.projects, args.transactions] + ([args.time_entries] if time_entries is not None else [])

    results = run(projects, transactions, time_entries, criteria, args.as_of)

    args.output.mkdir(parents=True, exist_ok=True)
    if args.store:
        history = record_active_status(args.store, results)
        results = results.merge(first_crossings(history), on="project_id", how="left")
    table = args.output / "active_portfolio.csv"
    results.to_csv(table, index=False)
    record = write_run_record(args.output, criteria, args.criteria, inputs, results)

    show = ["project_id", "status", "driver", "reason", "remaining", "runout_date", "planned_end"]
    print()
    print(results[show].to_string(index=False))
    print(f"\nPortfolio table: {table}")
    print(f"Run record:      {record}")


if __name__ == "__main__":
    main()
