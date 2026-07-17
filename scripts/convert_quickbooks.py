"""QuickBooks export converter — turns raw per-project exports into audit inputs.

EPM workflow:
    1. Export each project's Estimate and Transactions from QuickBooks
       (naming: <num>_Estimate.xls / <num>_Transactions.xls — .csv also accepted)
    2. Drop the pairs into one folder (e.g. data/real/exports/)
    3. Optionally add the company-wide QuickBooks Time export (timesheet*.csv)
    4. Run:  python scripts/convert_quickbooks.py --input data/real/exports --output data/real/audit_inputs

Outputs:
    proposal_projects.csv   — baseline per project leg (audit engine input)
    actual_projects.csv     — actuals per project leg (audit engine input)
    project_financials.csv  — extended metrics: margin, COs, WIP, invoice aging
    conversion_log.csv      — per project: what was found, data completeness

All processing is local. Real data never leaves the machine.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_CODE_RE = re.compile(r"(\d{5})-([FT])\b")
CO_RE = re.compile(r"\bC\.?O\.?\s*#?\s*\d*\b|\bchange order\b", re.IGNORECASE)
OVERHEAD_JOBCODES = {
    "Admin - In Office", "CRM Development", "IT", "Quoting", "Skid Build",
    "Training", "R&D - Internal Projects",
}

LABOR_PREFIXES = ("team blue:", "contracted labor")


# ── file reading ─────────────────────────────────────────────────────────────

def read_table(path: Path) -> pd.DataFrame:
    """Read a QuickBooks export regardless of .xls or .csv extension."""
    if path.suffix.lower() in (".xls", ".xlsx"):
        return pd.read_excel(path, sheet_name=0, header=None)
    return pd.read_csv(path, header=None)


# ── estimate parsing ─────────────────────────────────────────────────────────

def parse_estimate(path: Path) -> dict:
    """Extract baseline data from an Estimate export."""
    raw = read_table(path)
    header_row = None
    for i in range(min(3, len(raw))):
        if str(raw.iloc[i, 0]).strip().upper() == "SERVICE DATE":
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"{path.name}: no SERVICE DATE header found — not an estimate export?")

    cols = [str(c) for c in raw.iloc[header_row]]
    df = raw.iloc[header_row + 1:].reset_index(drop=True)
    df.columns = cols

    def col(fragment: str):
        for c in df.columns:
            if fragment.upper() in str(c).upper():
                return c
        return None

    c_svc, c_desc = col("PRODUCT/SERVICE"), col("DESCRIPTION")
    c_qty, c_ucost, c_tcost = col("QUANTITY"), col("UNIT COST"), col("TOTAL COST")
    c_rate, c_client = col("CLIENT <BR/>RATE") or col("CLIENT RATE"), col("CLIENT <BR/>TOTAL") or col("CLIENT TOTAL")
    c_inv, c_rem, c_class = col("INVOICED"), col("REMAINING"), col("CLASS")

    out = {
        "labor_hours": 0.0, "labor_cost": 0.0, "labor_client": 0.0,
        "materials_cost": 0.0, "materials_client": 0.0,
        "contracted_cost": 0.0, "contracted_client": 0.0,
        "expense_budget_client": 0.0,
        "co_count": 0, "co_hours": 0.0, "co_dollars": 0.0,
        "client_total": 0.0, "invoiced_per_estimate": 0.0, "remaining_per_estimate": 0.0,
        "fixed_fee_terms": "", "scope_header": "", "business_class": "",
        "rates": set(),
    }

    for _, r in df.iterrows():
        svc = str(r.get(c_svc, "") or "").strip()
        desc = str(r.get(c_desc, "") or "").strip()
        qty = pd.to_numeric(r.get(c_qty), errors="coerce")
        ucost = pd.to_numeric(r.get(c_ucost), errors="coerce")
        tcost = pd.to_numeric(r.get(c_tcost), errors="coerce")
        rate = pd.to_numeric(r.get(c_rate), errors="coerce")
        client = pd.to_numeric(r.get(c_client), errors="coerce")
        inv = pd.to_numeric(r.get(c_inv), errors="coerce")
        rem = pd.to_numeric(r.get(c_rem), errors="coerce")
        klass = str(r.get(c_class, "") or "").strip()

        if klass and klass.lower() != "nan":
            out["business_class"] = out["business_class"] or klass

        low_desc = desc.lower()
        if "fixed fee" in low_desc and ("terms" in low_desc or "price" in low_desc):
            out["fixed_fee_terms"] = desc
            continue
        if not svc or svc.lower() == "nan":
            if desc and desc.lower() != "nan" and not out["scope_header"]:
                out["scope_header"] = desc[:200]
            continue

        is_co = bool(CO_RE.search(desc))
        client_val = client if pd.notna(client) else 0.0
        out["client_total"] += client_val
        out["invoiced_per_estimate"] += inv if pd.notna(inv) else 0.0
        out["remaining_per_estimate"] += rem if pd.notna(rem) else 0.0

        svc_low = svc.lower()
        if svc_low.startswith("team blue:"):
            hours = qty if pd.notna(qty) else 0.0
            out["labor_hours"] += hours
            out["labor_cost"] += tcost if pd.notna(tcost) else 0.0
            out["labor_client"] += client_val
            if pd.notna(rate) and rate > 1:
                out["rates"].add(round(float(rate), 2))
            if is_co:
                out["co_count"] += 1
                out["co_hours"] += hours
                out["co_dollars"] += client_val
        elif svc_low.startswith("contracted labor"):
            out["contracted_cost"] += tcost if pd.notna(tcost) else 0.0
            out["contracted_client"] += client_val
            if is_co:
                out["co_count"] += 1
                out["co_dollars"] += client_val
        elif "material" in svc_low:
            out["materials_cost"] += tcost if pd.notna(tcost) else 0.0
            out["materials_client"] += client_val
        elif "expense" in svc_low or "travel expense" in svc_low:
            out["expense_budget_client"] += client_val
            if is_co:
                out["co_count"] += 1
                out["co_dollars"] += client_val
        else:
            # unknown service line — count toward client total only (already done)
            pass

    out["rates"] = sorted(out["rates"])
    return out


# ── transactions parsing ─────────────────────────────────────────────────────

def parse_transactions(path: Path) -> dict:
    """Extract actuals from a Transactions export."""
    raw = read_table(path)
    header_row = None
    for i in range(min(4, len(raw))):
        if str(raw.iloc[i, 0]).strip().lower() == "date":
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"{path.name}: no Date header row found — not a transactions export?")

    df = raw.iloc[header_row + 1:].reset_index(drop=True)
    df.columns = ["date", "type", "no", "from_to", "memo", "amount", "status"][: len(df.columns)]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["type"] = df["type"].astype(str).str.strip()
    df["status"] = df["status"].astype(str).str.strip().str.lower()

    # project code appears on Invoice/Time Charge/Estimate rows
    codes = df["from_to"].astype(str).str.extract(PROJECT_CODE_RE)
    code_rows = codes.dropna()
    project_code = None
    if not code_rows.empty:
        num, suffix = code_rows.iloc[0]
        project_code = f"{num}-{suffix}"

    inv = df[df["type"] == "Invoice"]
    cm = df[df["type"] == "Credit Memo"]
    tc = df[df["type"] == "Time Charge"]
    bills = df[df["type"] == "Bill"]
    exp = df[df["type"] == "Expense"]
    po = df[df["type"] == "Purchase Order"]
    est_rows = df[df["type"] == "Estimate"]

    return {
        "project_code": project_code,
        "estimate_date": est_rows["date"].min() if not est_rows.empty else pd.NaT,
        "revenue_invoiced": float(inv["amount"].sum() + cm["amount"].sum()),
        "invoice_count": int(len(inv)),
        "credit_memo_count": int(len(cm)),
        "credit_memo_total": float(cm["amount"].sum()),
        "first_invoice_date": inv["date"].min() if not inv.empty else pd.NaT,
        "last_invoice_date": inv["date"].max() if not inv.empty else pd.NaT,
        "overdue_invoice_count": int((inv["status"] == "overdue").sum()),
        "overdue_invoice_total": float(inv.loc[inv["status"] == "overdue", "amount"].sum()),
        "time_charge_total": float(tc["amount"].sum()),
        "time_charge_open_total": float(tc.loc[tc["status"] == "open", "amount"].sum()),
        "bills_total": float(bills["amount"].sum()),
        "expenses_total": float(exp["amount"].sum()),
        "po_total": float(po["amount"].sum()),
        "first_activity_date": df["date"].min(),
        "last_activity_date": df["date"].max(),
    }


# ── timesheet parsing ────────────────────────────────────────────────────────

def parse_timesheet(path: Path) -> pd.DataFrame:
    """Return hours per project leg from a QuickBooks Time export."""
    ts = pd.read_csv(path)
    if "jobcode_2" not in ts.columns or "hours" not in ts.columns:
        raise ValueError(f"{path.name}: expected QuickBooks Time columns (jobcode_2, hours)")
    codes = ts["jobcode_2"].astype(str).str.extract(PROJECT_CODE_RE)
    ts["project_code"] = codes[0] + "-" + codes[1]
    proj = ts.dropna(subset=["project_code"])
    agg = proj.groupby("project_code").agg(
        logged_hours=("hours", "sum"),
        people=("username", "nunique"),
        first_logged=("local_date", "min"),
        last_logged=("local_date", "max"),
    ).reset_index()
    return agg


# ── conversion ───────────────────────────────────────────────────────────────

def find_pairs(input_dir: Path) -> dict[str, dict[str, Path]]:
    """Group files by project number prefix: {num: {'estimate': path, 'transactions': path}}."""
    pairs: dict[str, dict[str, Path]] = {}
    for f in sorted(input_dir.iterdir()):
        if not f.is_file():
            continue
        m = re.match(r".*?(\d{5}).*?(estimate|transactions)", f.name, re.IGNORECASE)
        if not m:
            continue
        num, kind = m.group(1), m.group(2).lower()
        pairs.setdefault(num, {})[kind] = f
    return pairs


def convert(input_dir: Path, output_dir: Path, timesheet_path: Path | None = None) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    pairs = find_pairs(input_dir)
    if not pairs:
        raise SystemExit(f"No <num>_Estimate / <num>_Transactions files found in {input_dir}")

    ts_agg = None
    if timesheet_path and timesheet_path.exists():
        ts_agg = parse_timesheet(timesheet_path)

    proposals, actuals, financials, log = [], [], [], []

    for num, files in pairs.items():
        entry = {"project_number": num, "estimate_file": "", "transactions_file": "",
                 "status": "", "notes": []}
        est = tx = None
        if "estimate" in files:
            entry["estimate_file"] = files["estimate"].name
            try:
                est = parse_estimate(files["estimate"])
            except Exception as e:
                entry["notes"].append(f"estimate parse failed: {e}")
        else:
            entry["notes"].append("no estimate file")
        if "transactions" in files:
            entry["transactions_file"] = files["transactions"].name
            try:
                tx = parse_transactions(files["transactions"])
            except Exception as e:
                entry["notes"].append(f"transactions parse failed: {e}")
        else:
            entry["notes"].append("no transactions file")

        if est is None or tx is None:
            entry["status"] = "SKIPPED"
            log.append(entry)
            continue

        code = tx["project_code"] or f"{num}-?"
        billing_type = "fixed_fee" if code.endswith("-F") else "t_and_e" if code.endswith("-T") else ""

        # hours actuals: timesheet first, invoice-derived fallback for T&E
        logged_hours = None
        first_logged = None
        hours_source = "unavailable"
        if ts_agg is not None:
            row = ts_agg[ts_agg["project_code"] == code]
            if not row.empty:
                logged_hours = float(row["logged_hours"].iloc[0])
                first_logged = pd.to_datetime(row["first_logged"].iloc[0], errors="coerce")
                hours_source = "logged"
        derived_hours = None
        if est["rates"] and len(est["rates"]) == 1 and tx["time_charge_total"] > 0:
            derived_hours = round(tx["time_charge_total"] / est["rates"][0], 2)
            if hours_source == "unavailable":
                hours_source = "derived_from_time_charges"
        actual_hours = logged_hours if logged_hours is not None else derived_hours

        planned_cost = est["labor_cost"] + est["materials_cost"] + est["contracted_cost"]
        planned_margin_pct = (
            (est["client_total"] - planned_cost) / est["client_total"]
            if est["client_total"] else None
        )
        # actual cost: external (bills+expenses) + internal labor when logged hours exist
        internal_cost = None
        actual_margin_pct = None
        margin_reliability = ""
        unit_cost = est["labor_cost"] / est["labor_hours"] if est["labor_hours"] else None
        if logged_hours is not None and unit_cost:
            internal_cost = logged_hours * unit_cost
            total_cost = internal_cost + tx["bills_total"] + tx["expenses_total"]
            if tx["revenue_invoiced"]:
                actual_margin_pct = (tx["revenue_invoiced"] - total_cost) / tx["revenue_invoiced"]
                # if billing started well before hour logging did, part of the labor
                # cost is invisible and the margin is overstated — flag it
                if (
                    pd.notna(tx["first_activity_date"]) and first_logged is not None
                    and pd.notna(first_logged)
                    and tx["first_activity_date"] < first_logged - pd.Timedelta(days=14)
                ):
                    margin_reliability = "partial_hours_overstated"
                else:
                    margin_reliability = "full"

        completed = tx["overdue_invoice_count"] == 0 and est["remaining_per_estimate"] <= 0.005 * max(est["client_total"], 1)
        status = "completed" if completed else "active"

        proposals.append({
            "project_id": code,
            "project_name": "",  # EPM fills in or comes from jobcode list
            "proposed_budget": round(est["client_total"], 2),
            "proposed_hours": est["labor_hours"],
            "proposed_start_date": "",   # not in exports — EPM enters from proposal
            "proposed_end_date": "",     # not in exports — EPM enters from proposal
            "proposed_resource_count": "",
            "project_manager": "",
            "client": "",
            "project_type": est["business_class"],
            "billing_type": billing_type,
        })
        actuals.append({
            "project_id": code,
            "actual_budget": round(tx["revenue_invoiced"], 2),
            "actual_hours": actual_hours if actual_hours is not None else "",
            "actual_start_date": tx["first_activity_date"].date().isoformat() if pd.notna(tx["first_activity_date"]) else "",
            "actual_end_date": tx["last_invoice_date"].date().isoformat() if pd.notna(tx["last_invoice_date"]) else "",
            "status": status,
            "actual_resource_count": "",
            "closeout_notes": "",
        })
        financials.append({
            "project_id": code,
            "billing_type": billing_type,
            "business_class": est["business_class"],
            "estimate_total": round(est["client_total"], 2),
            "revenue_invoiced": round(tx["revenue_invoiced"], 2),
            "planned_cost": round(planned_cost, 2),
            "planned_margin_pct": round(planned_margin_pct, 4) if planned_margin_pct is not None else "",
            "actual_margin_pct": round(actual_margin_pct, 4) if actual_margin_pct is not None else "",
            "margin_reliability": margin_reliability,
            "internal_labor_cost": round(internal_cost, 2) if internal_cost is not None else "",
            "external_cost_bills": round(tx["bills_total"], 2),
            "external_cost_expenses": round(tx["expenses_total"], 2),
            "expense_budget": round(est["expense_budget_client"], 2),
            "po_committed": round(tx["po_total"], 2),
            "co_count": est["co_count"],
            "co_hours": est["co_hours"],
            "co_dollars": round(est["co_dollars"], 2),
            "unbilled_wip": round(tx["time_charge_open_total"], 2),
            "credit_memo_count": tx["credit_memo_count"],
            "credit_memo_total": round(tx["credit_memo_total"], 2),
            "overdue_invoices": tx["overdue_invoice_count"],
            "overdue_total": round(tx["overdue_invoice_total"], 2),
            "invoice_count": tx["invoice_count"],
            "first_invoice": tx["first_invoice_date"].date().isoformat() if pd.notna(tx["first_invoice_date"]) else "",
            "last_invoice": tx["last_invoice_date"].date().isoformat() if pd.notna(tx["last_invoice_date"]) else "",
            "hours_source": hours_source,
            "logged_hours": logged_hours if logged_hours is not None else "",
            "derived_hours": derived_hours if derived_hours is not None else "",
            "proposed_hours": est["labor_hours"],
        })
        entry["status"] = "OK"
        entry["notes"].append(f"{code} {billing_type} hours={hours_source}")
        log.append(entry)

    prop_df = pd.DataFrame(proposals)
    act_df = pd.DataFrame(actuals)
    fin_df = pd.DataFrame(financials)
    log_df = pd.DataFrame([{**e, "notes": "; ".join(e["notes"])} for e in log])

    prop_df.to_csv(output_dir / "proposal_projects.csv", index=False)
    act_df.to_csv(output_dir / "actual_projects.csv", index=False)
    fin_df.to_csv(output_dir / "project_financials.csv", index=False)
    log_df.to_csv(output_dir / "conversion_log.csv", index=False)
    return log_df


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert QuickBooks exports to audit inputs")
    ap.add_argument("--input", required=True, help="Folder containing <num>_Estimate + <num>_Transactions files")
    ap.add_argument("--output", required=True, help="Folder for generated audit input CSVs")
    ap.add_argument("--timesheet", help="Optional QuickBooks Time export CSV (company-wide)")
    args = ap.parse_args()

    log = convert(
        Path(args.input),
        Path(args.output),
        Path(args.timesheet) if args.timesheet else None,
    )
    print(log.to_string(index=False))
    ok = (log["status"] == "OK").sum()
    print(f"\nConverted {ok} of {len(log)} projects → {args.output}")
    print("NOTE: proposed start/end dates, project names, PM and client fields are left")
    print("blank for EPM entry — they are not present in QuickBooks exports.")


if __name__ == "__main__":
    main()
