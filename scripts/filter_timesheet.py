"""Timesheet pre-filter — shrink a full company timesheet export down to only
the rows for specific projects, before it ever gets uploaded to the dashboard.

Why this exists: the company timesheet export can be large (multi-megabyte,
every employee, every project) and contains hours data for projects that
have nothing to do with the audit you're running. Filtering locally first
means the file that actually gets uploaded is small and provably scoped to
only the projects you're auditing — no unrelated project or employee data
ever leaves this step.

(Separately, the converter itself only ever extracts and writes hours for
the project codes present in the Estimate/Transactions files you provide —
unrelated projects' rows are read but never written to any output. This
script gives you that same guarantee one step earlier, before upload.)

Usage:
    python scripts/filter_timesheet.py \
        --timesheet data/real/timesheet_full.csv \
        --projects 25718-F,25602-T,23115-F \
        --output data/real/timesheet_filtered.csv

    # Or let it infer project codes from a folder of Estimate/Transactions files:
    python scripts/filter_timesheet.py \
        --timesheet data/real/timesheet_full.csv \
        --from-exports data/real/exports \
        --output data/real/timesheet_filtered.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from convert_ies import PROJECT_CODE_RE, find_pairs, parse_transactions


def project_codes_from_exports(exports_dir: Path) -> set[str]:
    """Read every Transactions file in a folder and collect the project codes found."""
    codes: set[str] = set()
    for num, files in find_pairs(exports_dir).items():
        if "transactions" not in files:
            continue
        try:
            tx = parse_transactions(files["transactions"])
        except Exception:
            continue
        if tx["project_code"]:
            codes.add(tx["project_code"])
    return codes


def filter_timesheet(timesheet_path: Path, project_codes: set[str]) -> pd.DataFrame:
    ts = pd.read_csv(timesheet_path)
    if "jobcode_2" not in ts.columns:
        raise ValueError(f"{timesheet_path.name}: expected a 'jobcode_2' column, not found")
    codes = ts["jobcode_2"].astype(str).str.extract(PROJECT_CODE_RE)
    ts_project_code = codes[0] + "-" + codes[1]
    keep = ts_project_code.isin(project_codes)
    return ts[keep].copy()


def main() -> None:
    ap = argparse.ArgumentParser(description="Filter a full timesheet export down to specific projects")
    ap.add_argument("--timesheet", required=True, help="Path to the full company timesheet CSV")
    ap.add_argument("--projects", help="Comma-separated project codes, e.g. 25718-F,25602-T")
    ap.add_argument("--from-exports", help="Folder of <num>_Estimate/<num>_Transactions files — "
                                            "project codes are read from these instead of --projects")
    ap.add_argument("--output", required=True, help="Path for the filtered timesheet CSV")
    args = ap.parse_args()

    if args.projects:
        codes = {c.strip() for c in args.projects.split(",") if c.strip()}
    elif args.from_exports:
        codes = project_codes_from_exports(Path(args.from_exports))
    else:
        raise SystemExit("Provide either --projects or --from-exports")

    if not codes:
        raise SystemExit("No project codes found — nothing to filter.")

    timesheet_path = Path(args.timesheet)
    original_size = timesheet_path.stat().st_size
    filtered = filter_timesheet(timesheet_path, codes)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(out_path, index=False)
    filtered_size = out_path.stat().st_size

    print(f"Projects: {', '.join(sorted(codes))}")
    print(f"Rows kept: {len(filtered)} of {sum(1 for _ in open(timesheet_path)) - 1}")
    print(f"File size: {original_size:,} bytes → {filtered_size:,} bytes "
          f"({filtered_size / original_size:.1%} of original)")
    print(f"Filtered timesheet written to: {out_path}")


if __name__ == "__main__":
    main()
