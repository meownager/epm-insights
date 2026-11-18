"""IES adapter for the Active Projects audit.

Turns the raw exports an EPM downloads into the standard schema that
active_project_health.py reads (docs/active-projects-spec.md, "Inputs"):

    IES sales / transactions sheet  ->  transactions  (budget, change_order, time, expense)
    QuickBooks Time timesheet       ->  time_entries  (date, person, hours, approval)

It also runs the spec's upload checks. A check either BLOCKS (the file cannot
be used: UploadBlocked is raised) or WARNS (results still shown, warning beside
them). Every upload returns a one-line summary of what was found.

Company specifics (IES row types, timesheet column names) live only here, so
the engine stays generic. All processing is local.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from convert_ies import PROJECT_CODE_RE, parse_estimate, read_table

STALE_AFTER_DAYS = 7
TOTAL_ROW_RE = re.compile(r"^\s*(grand\s+)?totals?\b", re.IGNORECASE)

# IES row type -> standard `kind`. Types not listed (Invoice, Credit Memo,
# Payment) are billing, not burn, and are ignored.
KIND_BY_TYPE = {
    "Estimate": "budget",
    "Change Order": "change_order",
    "Time Charge": "time",
    "Bill": "expense",
    "Expense": "expense",
    # Open POs are committed but not yet spent. Kept as their own kind so they
    # are visible, but the engine does not count them (decision pending).
    "Purchase Order": "commitment",
}
APPROVED_STATUSES = {"accepted", "approved", "closed", "converted"}
DROPPED_STATUSES = {"rejected", "declined", "void", "voided"}


class UploadBlocked(ValueError):
    """The upload cannot be used. The message says why, in plain words."""


@dataclass
class UploadReport:
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


# %% transactions %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def transactions_from_ies(path: Path, project_id: str | None = None,
                          estimate_path: Path | None = None) -> tuple[pd.DataFrame, UploadReport]:
    """Read one project's IES sales/transactions sheet into standard rows.

    estimate_path (optional): the project's IES Estimate sheet. When given, its
    labor-line hours become the budgeted hours on the `budget` row; without it,
    hours are "not measured" for this project.
    """
    path = Path(path)
    raw = read_table(path)
    header = next((i for i in range(min(4, len(raw)))
                   if str(raw.iloc[i, 0]).strip().lower() == "date"), None)
    if header is None:
        raise UploadBlocked(f"{path.name}: this doesn't look like an IES transactions export (no Date header)")

    df = raw.iloc[header + 1:].reset_index(drop=True)
    df.columns = ["date", "type", "no", "from_to", "memo", "amount", "status"][: len(df.columns)]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["type"] = df["type"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df = df.dropna(subset=["date"])  # drops footer / total lines with no date

    if project_id is None:
        codes = df["from_to"].astype(str).str.extract(PROJECT_CODE_RE).dropna()
        project_id = f"{codes.iloc[0, 0]}-{codes.iloc[0, 1]}" if not codes.empty else path.parent.name

    report = UploadReport()
    df = _drop_duplicate_bills(df, report)

    df["kind"] = df["type"].map(KIND_BY_TYPE)
    df = df.dropna(subset=["kind"])
    dropped = df["status"].isin(DROPPED_STATUSES) & df["kind"].isin(["budget", "change_order"])
    df = df[~dropped]
    df["approved"] = df["status"].isin(APPROVED_STATUSES)
    df["hours"] = 0.0
    df["project_id"] = project_id

    if estimate_path is not None:
        est = parse_estimate(Path(estimate_path))
        first_budget = df.index[(df["kind"] == "budget") & df["approved"]]
        if len(first_budget):
            df.loc[first_budget[0], "hours"] = est["labor_hours"]
    else:
        report.warnings.append(f"{project_id}: no Estimate sheet, so budgeted hours are not measured")

    counts = df["kind"].value_counts()
    report.summary = (f"{project_id}: {len(df)} rows used: "
                      + ", ".join(f"{counts.get(k, 0)} {k}" for k in
                                  ("budget", "change_order", "time", "expense", "commitment"))
                      + (f"; {int(dropped.sum())} rejected budget/CO rows excluded" if dropped.any() else ""))
    cols = ["project_id", "date", "kind", "amount", "approved", "hours", "status"]
    return df[cols].reset_index(drop=True), report


def _drop_duplicate_bills(df: pd.DataFrame, report: UploadReport) -> pd.DataFrame:
    """IES can list one bill twice (open, then paid) with the same date and
    amount. Drop the open copy when a paid twin exists (same rule as convert_ies)."""
    bills = df[df["type"] == "Bill"]
    key = bills["date"].astype(str) + "|" + bills["amount"].round(4).astype(str)
    drop = []
    for _, grp in bills.groupby(key):
        if {"open", "paid"} <= set(grp["status"]):
            drop += grp.index[grp["status"] == "open"].tolist()
    if drop:
        report.warnings.append(f"{len(drop)} duplicate open bill(s) dropped (paid copy kept)")
    return df.drop(index=drop)


# %% timesheet %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def time_entries_from_timesheet(path: Path, today=None) -> tuple[pd.DataFrame, UploadReport]:
    """Read a QuickBooks Time export into standard time entries, with upload checks."""
    path = Path(path)
    ts = pd.read_csv(path)
    return time_entries_from_frame(ts, today=today, name=path.name)


def time_entries_from_frame(ts: pd.DataFrame, today=None, name: str = "timesheet") -> tuple[pd.DataFrame, UploadReport]:
    report = UploadReport()
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.today().normalize()

    # BLOCK: required columns missing
    missing = {"local_date", "jobcode_2", "hours"} - set(ts.columns)
    if missing:
        raise UploadBlocked(f"{name}: this doesn't look like a timesheet export "
                            f"(missing {', '.join(sorted(missing))})")

    # summary / grand-total rows: removed on purpose, and reported
    # only identity columns are checked, so a note like "Total rework..." is not dropped
    id_cols = [c for c in ("username", "fname", "lname", "jobcode_1", "jobcode_2", "local_date") if c in ts]
    text = ts[id_cols].astype(str).fillna("")
    is_total = text.apply(lambda col: col.str.match(TOTAL_ROW_RE)).any(axis=1)
    is_total |= pd.to_datetime(ts["local_date"], errors="coerce").isna()
    total_rows = int(is_total.sum())
    ts = ts[~is_total].copy()

    codes = ts["jobcode_2"].astype(str).str.extract(PROJECT_CODE_RE)
    ts["project_id"] = codes[0] + "-" + codes[1]
    overhead = int(ts["project_id"].isna().sum())
    ts = ts.dropna(subset=["project_id"])

    out = pd.DataFrame({
        "project_id": ts["project_id"],
        "date": pd.to_datetime(ts["local_date"]),
        "person": ts.get("username", pd.Series("", index=ts.index)),
        "hours": pd.to_numeric(ts["hours"], errors="coerce").fillna(0.0),
        "billable": ts.get("billable", pd.Series("", index=ts.index)).astype(str).str.lower().eq("yes"),
    })

    # WARN: approval status unknown, or nothing unapproved (filtered export?)
    if "approved_status" in ts.columns:
        out["approval"] = ts["approved_status"].astype(str).str.strip().str.lower()
        if not (out["approval"] == "unapproved").any():
            report.warnings.append("No unapproved hours found. If your export filtered to approved only, "
                                   "re-export with all entries for the latest picture")
    else:
        out["approval"] = "approved"
        report.warnings.append("Approval status unknown; all hours counted")

    # WARN: export is stale
    if not out.empty and out["date"].max() < today - pd.Timedelta(days=STALE_AFTER_DAYS):
        report.warnings.append(f"Timesheet ends on {out['date'].max():%Y-%m-%d}; recent hours are missing")

    n = out["approval"].value_counts()
    report.summary = (f"{len(out):,} entries: {n.get('approved', 0):,} approved, "
                      f"{n.get('unapproved', 0):,} unapproved (counted), "
                      f"{n.get('rejected', 0):,} rejected (excluded), "
                      f"{total_rows} total row{'s' if total_rows != 1 else ''} removed"
                      + (f", {overhead} overhead entries skipped" if overhead else "") + ".")
    return out.reset_index(drop=True), report


# %% portfolio-level checks %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def coverage_warnings(projects: pd.DataFrame, transactions: pd.DataFrame,
                      time_entries: pd.DataFrame | None) -> dict[str, str]:
    """WARN on a project's row when it has no transactions or no time entries."""
    have_tx = set(transactions["project_id"]) if not transactions.empty else set()
    have_te = set(time_entries["project_id"]) if time_entries is not None and not time_entries.empty else set()
    out = {}
    for pid in projects["project_id"]:
        gaps = [label for label, have in (("transactions", have_tx), ("time entries", have_te)) if pid not in have]
        if gaps:
            out[pid] = "no " + " and no ".join(gaps)
    return out


def load_ies_folder(root: Path, today=None) -> tuple[pd.DataFrame, pd.DataFrame | None, list[UploadReport]]:
    """Read a folder of per-project subfolders, e.g. data/real/26173-F/.

    Each subfolder holds the project's sales/transactions sheet (*sales* or
    *transactions*, .xls or .csv), optionally its *estimate* sheet, and any
    timesheet*.csv. Timesheets are combined and exact duplicate rows removed,
    since the same company-wide export may sit in several folders.
    """
    root = Path(root)
    tx_parts, ts_parts, reports = [], [], []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and PROJECT_CODE_RE.search(p.name)):
        files = [f for f in folder.iterdir() if f.is_file()]
        sales = next((f for f in files if re.search(r"sales|transactions", f.name, re.I)), None)
        estimate = next((f for f in files if re.search(r"estimate", f.name, re.I)), None)
        if sales is not None:
            tx, rep = transactions_from_ies(sales, folder.name, estimate)
            tx_parts.append(tx)
            reports.append(rep)
        ts_parts += [pd.read_csv(f) for f in files if re.match(r"timesheet.*\.csv$", f.name, re.I)]

    transactions = pd.concat(tx_parts, ignore_index=True) if tx_parts else pd.DataFrame(
        columns=["project_id", "date", "kind", "amount", "approved", "hours"])
    time_entries = None
    if ts_parts:
        time_entries, rep = time_entries_from_frame(pd.concat(ts_parts).drop_duplicates(), today=today)
        reports.append(rep)
    return transactions, time_entries, reports
