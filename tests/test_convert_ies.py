"""Known-answer tests for the IES financial data converter — synthetic fixtures only.

These fixtures mimic the structure of real IES exports (estimate +
transactions) with entirely fictional numbers. No real company data.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from convert_ies import (
    build_project_ledger,
    convert,
    find_pairs,
    parse_estimate,
    parse_timesheet,
    parse_transactions,
)


# ── synthetic fixture builders ───────────────────────────────────────────────

ESTIMATE_HEADER = [
    "SERVICE DATE", "PRODUCT/SERVICE", "DESCRIPTION", "QUANTITY",
    "UNIT COST <BR/>(HIDDEN)", "TOTAL COST <BR/>(HIDDEN)",
    "CLIENT <BR/>RATE", "CLIENT <BR/>TOTAL", "INVOICED", "REMAINING",
    "CONVERTED", "CLASS (HIDDEN)",
]


def write_estimate(path: Path, rows: list[list]) -> None:
    df = pd.DataFrame([ESTIMATE_HEADER] + rows)
    df.to_csv(path, index=False, header=False)


def write_transactions(path: Path, rows: list[list]) -> None:
    data = [["Status: All statuses", "", "", "", "", "", ""],
            ["Date", "Type", "No.", "From / To", "Memo", "Amount", "Status"]] + rows
    pd.DataFrame(data).to_csv(path, index=False, header=False)


def write_timesheet(path: Path, rows: list[dict]) -> None:
    cols = ["username", "jobcode_2", "hours", "local_date"]
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


@pytest.fixture
def fixed_fee_project(tmp_path):
    """Synthetic fixed-fee project 90001-F with one CO and a subcontractor bill."""
    write_estimate(tmp_path / "90001_Estimate.csv", [
        ["", "Team Blue:Engineer", "Line 10: Widget Automation", 100, 100.00, 10000.00, 200.00, 20000.00, 20000.00, 0.00, "", "Automation"],
        ["", "Team Blue:Engineer", "Additional Work CO #1", 10, 100.00, 1000.00, 200.00, 2000.00, 2000.00, 0.00, "", "Automation"],
        ["", "Project Materials", "Widget Hardware", 1, 5000.00, 5000.00, 6000.00, 6000.00, 6000.00, 0.00, "", "Automation"],
        ["", "", "Fixed Fee Terms:\n50% Upon Receipt of Order - $14,000\n50% Upon Completion - $14,000", "", "", "", 0.00, 0.00, 0.00, 0.00, "", ""],
    ])
    write_transactions(tmp_path / "90001_Transactions.csv", [
        ["06/01/2026", "Invoice", "200001", "90001-F - Widget Automation", "", 14000, "paid"],
        ["03/15/2026", "Bill", "B-1", "Synthetic Subs Inc", "", 3000, "paid"],
        ["02/01/2026", "Invoice", "200000", "90001-F - Widget Automation", "", 14000, "paid"],
        ["01/15/2026", "Estimate", "2026-001", "90001-F - Widget Automation", "", 28000, "applied"],
    ])
    return tmp_path


@pytest.fixture
def t_and_e_project(tmp_path):
    """Synthetic T&E project 90002-T with time charges (one open) and a credit memo."""
    write_estimate(tmp_path / "90002_Estimate.csv", [
        ["", "Team Blue:Engineer", "Line 1: Support Block", 200, 100.00, 20000.00, 150.00, 30000.00, 15000.00, 15000.00, "", "Service"],
    ])
    write_transactions(tmp_path / "90002_Transactions.csv", [
        ["05/01/2026", "Time Charge", "", "90002-T - Support Block", "", 1200, "open"],
        ["04/20/2026", "Invoice", "200100", "90002-T - Support Block", "", 13800, "paid"],
        ["04/15/2026", "Time Charge", "", "90002-T - Support Block", "", 600, "applied"],
        ["04/10/2026", "Time Charge", "", "90002-T - Support Block", "", 13200, "applied"],
        ["03/01/2026", "Credit Memo", "200099", "90002-T - Support Block", "", -300, "applied"],
        ["02/01/2026", "Estimate", "2026-002", "90002-T - Support Block", "", 30000, "accepted"],
    ])
    return tmp_path


# ── parse_estimate ───────────────────────────────────────────────────────────

def test_estimate_labor_hours(fixed_fee_project):
    est = parse_estimate(fixed_fee_project / "90001_Estimate.csv")
    assert est["labor_hours"] == 110  # 100 base + 10 CO


def test_estimate_client_total(fixed_fee_project):
    est = parse_estimate(fixed_fee_project / "90001_Estimate.csv")
    assert est["client_total"] == 28000  # 20000 + 2000 + 6000


def test_estimate_detects_co(fixed_fee_project):
    est = parse_estimate(fixed_fee_project / "90001_Estimate.csv")
    assert est["co_count"] == 1
    assert est["co_hours"] == 10
    assert est["co_dollars"] == 2000


def test_estimate_captures_terms(fixed_fee_project):
    est = parse_estimate(fixed_fee_project / "90001_Estimate.csv")
    assert "50% Upon Receipt" in est["fixed_fee_terms"]


def test_estimate_materials_split(fixed_fee_project):
    est = parse_estimate(fixed_fee_project / "90001_Estimate.csv")
    assert est["materials_cost"] == 5000
    assert est["materials_client"] == 6000


def test_estimate_single_rate(t_and_e_project):
    est = parse_estimate(t_and_e_project / "90002_Estimate.csv")
    assert est["rates"] == [150.0]


# ── parse_transactions ───────────────────────────────────────────────────────

def test_transactions_project_code(fixed_fee_project):
    tx = parse_transactions(fixed_fee_project / "90001_Transactions.csv")
    assert tx["project_code"] == "90001-F"


def test_transactions_revenue(fixed_fee_project):
    tx = parse_transactions(fixed_fee_project / "90001_Transactions.csv")
    assert tx["revenue_invoiced"] == 28000


def test_transactions_bills(fixed_fee_project):
    tx = parse_transactions(fixed_fee_project / "90001_Transactions.csv")
    assert tx["bills_total"] == 3000


def test_transactions_credit_memo_reduces_revenue(t_and_e_project):
    tx = parse_transactions(t_and_e_project / "90002_Transactions.csv")
    assert tx["revenue_invoiced"] == 13800 - 300


def test_transactions_open_wip(t_and_e_project):
    tx = parse_transactions(t_and_e_project / "90002_Transactions.csv")
    assert tx["time_charge_open_total"] == 1200


def test_transactions_time_charge_total(t_and_e_project):
    tx = parse_transactions(t_and_e_project / "90002_Transactions.csv")
    assert tx["time_charge_total"] == 15000


def test_ragged_csv_transactions_does_not_crash(tmp_path):
    """Regression: a literal raw CSV export (1-field status line, 7-field
    data rows) must not raise a pandas tokenizing error. The .xls path pads
    blank cells automatically; the .csv path must do the same manually."""
    raw = (
        "Status: All statuses Delivery Method: Any Date: All\n"
        "Date,Type,No.,From / To,Memo,Amount,Status\n"
        "06/01/2026,Invoice,200001,90005-F - Ragged Test,,5000,paid\n"
        "01/15/2026,Estimate,2026-005,90005-F - Ragged Test,,5000,applied\n"
    )
    path = tmp_path / "90005_Transactions.csv"
    path.write_text(raw)
    tx = parse_transactions(path)
    assert tx["project_code"] == "90005-F"
    assert tx["revenue_invoiced"] == 5000


# ── parse_timesheet ──────────────────────────────────────────────────────────

def test_parse_timesheet_aggregates_by_project(tmp_path):
    write_timesheet(tmp_path / "timesheet.csv", [
        {"username": "a@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 8, "local_date": "2026-01-20"},
        {"username": "a@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 6, "local_date": "2026-01-21"},
        {"username": "b@co.com", "jobcode_2": "90002-T - Support Block", "hours": 4, "local_date": "2026-04-10"},
    ])
    agg, daily = parse_timesheet(tmp_path / "timesheet.csv")
    row = agg[agg["project_code"] == "90001-F"].iloc[0]
    assert row["logged_hours"] == 14
    assert row["first_logged"] == "2026-01-20"
    assert row["last_logged"] == "2026-01-21"


def test_parse_timesheet_daily_rows(tmp_path):
    write_timesheet(tmp_path / "timesheet.csv", [
        {"username": "a@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 8, "local_date": "2026-01-20"},
        {"username": "b@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 3, "local_date": "2026-01-20"},
        {"username": "a@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 6, "local_date": "2026-01-21"},
    ])
    _, daily = parse_timesheet(tmp_path / "timesheet.csv")
    day1 = daily[(daily["project_code"] == "90001-F") & (daily["date"] == pd.Timestamp("2026-01-20"))]
    assert day1["hours"].iloc[0] == 11  # two people, same day, summed


# ── find_pairs / convert end-to-end ─────────────────────────────────────────

def test_find_pairs_groups_by_number(fixed_fee_project):
    pairs = find_pairs(fixed_fee_project)
    assert "90001" in pairs
    assert set(pairs["90001"].keys()) == {"estimate", "transactions"}


def test_convert_end_to_end(fixed_fee_project, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    log = convert(fixed_fee_project, out)
    assert (log["status"] == "OK").all()

    prop = pd.read_csv(out / "proposal_projects.csv")
    act = pd.read_csv(out / "actual_projects.csv")
    fin = pd.read_csv(out / "project_financials.csv")

    assert prop["project_id"].iloc[0] == "90001-F"
    assert prop["billing_type"].iloc[0] == "fixed_fee"
    assert prop["proposed_budget"].iloc[0] == 28000
    assert prop["proposed_hours"].iloc[0] == 110
    assert act["actual_budget"].iloc[0] == 28000
    assert act["status"].iloc[0] == "completed"
    assert fin["co_count"].iloc[0] == 1
    assert fin["external_cost_bills"].iloc[0] == 3000


def test_convert_no_timesheet_dates_from_invoices(fixed_fee_project, tmp_path_factory):
    """No timesheet supplied → actual dates automatically fall back to invoice dates."""
    out = tmp_path_factory.mktemp("out")
    convert(fixed_fee_project, out)
    act = pd.read_csv(out / "actual_projects.csv")
    fin = pd.read_csv(out / "project_financials.csv")
    assert act["actual_start_date"].iloc[0] == "2026-02-01"  # earliest invoice
    assert act["actual_end_date"].iloc[0] == "2026-06-01"    # latest invoice
    assert fin["date_source"].iloc[0] == "invoices"


def test_convert_prefers_timesheet_dates_over_invoices(fixed_fee_project, tmp_path_factory):
    """When a timesheet is supplied, logged work dates take priority over invoice dates."""
    write_timesheet(fixed_fee_project / "timesheet.csv", [
        {"username": "a@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 8, "local_date": "2025-11-03"},
        {"username": "a@co.com", "jobcode_2": "90001-F - Widget Automation", "hours": 8, "local_date": "2026-05-15"},
    ])
    out = tmp_path_factory.mktemp("out")
    convert(fixed_fee_project, out, timesheet_path=fixed_fee_project / "timesheet.csv")
    act = pd.read_csv(out / "actual_projects.csv")
    fin = pd.read_csv(out / "project_financials.csv")
    assert act["actual_start_date"].iloc[0] == "2025-11-03"
    assert act["actual_end_date"].iloc[0] == "2026-05-15"
    assert fin["date_source"].iloc[0] == "timesheet"


def test_convert_no_manual_fields_required(fixed_fee_project, tmp_path_factory):
    """Converter output is fully populated for actuals with zero manual entry required."""
    out = tmp_path_factory.mktemp("out")
    convert(fixed_fee_project, out)
    act = pd.read_csv(out / "actual_projects.csv")
    row = act.iloc[0]
    assert row["actual_budget"] > 0
    assert str(row["actual_start_date"]) != "nan" and row["actual_start_date"] != ""
    assert str(row["actual_end_date"]) != "nan" and row["actual_end_date"] != ""
    assert row["status"] in ("completed", "active")


def test_convert_proposed_dates_left_blank_not_fabricated(fixed_fee_project, tmp_path_factory):
    """Baseline schedule dates don't exist in IES data — must stay blank, never guessed."""
    out = tmp_path_factory.mktemp("out")
    convert(fixed_fee_project, out)
    prop = pd.read_csv(out / "proposal_projects.csv")
    fin = pd.read_csv(out / "project_financials.csv")
    assert pd.isna(prop["proposed_start_date"].iloc[0]) or prop["proposed_start_date"].iloc[0] == ""
    assert pd.isna(prop["proposed_end_date"].iloc[0]) or prop["proposed_end_date"].iloc[0] == ""
    assert fin["schedule_baseline_available"].iloc[0] == False


def test_convert_t_and_e_derived_hours(t_and_e_project, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    convert(t_and_e_project, out)
    fin = pd.read_csv(out / "project_financials.csv")
    # 15000 of time charges at single rate 150 → 100 derived hours
    assert fin["derived_hours"].iloc[0] == 100
    assert fin["hours_source"].iloc[0] == "derived_from_time_charges"
    assert fin["unbilled_wip"].iloc[0] == 1200


def test_convert_incomplete_estimate_marks_active(t_and_e_project, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    convert(t_and_e_project, out)
    act = pd.read_csv(out / "actual_projects.csv")
    # remaining 15000 of 30000 → still active, excluded from completed audit
    assert act["status"].iloc[0] == "active"


# ── build_project_ledger ─────────────────────────────────────────────────────

def test_ledger_cumulative_revenue():
    revenue_events = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
        "amount": [1000, 2000, 500],
    })
    ledger = build_project_ledger(revenue_events, None, "90001-F")
    assert list(ledger["cumulative_revenue"]) == [1000, 3000, 3500]


def test_ledger_merges_revenue_and_hours_on_date():
    revenue_events = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-02-01"]),
        "amount": [1000, 1000],
    })
    hours_daily = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-15"]),
        "hours": [20],
    })
    ledger = build_project_ledger(revenue_events, hours_daily, "90001-F")
    # revenue on 01-15 should forward-fill from the 01-01 invoice (1000)
    row = ledger[ledger["date"] == pd.Timestamp("2026-01-15")].iloc[0]
    assert row["cumulative_revenue"] == 1000
    assert row["cumulative_hours"] == 20


def test_ledger_hours_before_first_entry_is_nan_not_zero():
    """Regression: a project running Aug'24-Apr'26 whose timesheet coverage
    only starts Jul'25 must show NaN (no data) for the earlier stretch, not
    a false 0 — otherwise a real project with no hours logged yet reads as
    a massive fake underrun once paced against the full proposed hours."""
    revenue_events = pd.DataFrame({
        "date": pd.to_datetime(["2024-08-01", "2025-08-01", "2026-04-01"]),
        "amount": [50000, 50000, 50000],
    })
    hours_daily = pd.DataFrame({
        "date": pd.to_datetime(["2025-07-15", "2025-08-01"]),
        "hours": [50, 50],
    })
    ledger = build_project_ledger(revenue_events, hours_daily, "90001-F")
    before_tracking = ledger[ledger["date"] == pd.Timestamp("2024-08-01")]
    after_tracking = ledger[ledger["date"] == pd.Timestamp("2026-04-01")]
    assert pd.isna(before_tracking["cumulative_hours"].iloc[0])
    assert after_tracking["cumulative_hours"].iloc[0] == 100  # forward-filled from the last real entry


def test_ledger_no_hours_data_defaults_to_zero():
    revenue_events = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"]),
        "amount": [500],
    })
    ledger = build_project_ledger(revenue_events, None, "90001-F")
    assert (ledger["cumulative_hours"] == 0).all()


def test_ledger_empty_revenue_returns_empty():
    ledger = build_project_ledger(pd.DataFrame(columns=["date", "amount"]), None, "90001-F")
    assert ledger.empty


def test_convert_writes_ledger_file(fixed_fee_project, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    convert(fixed_fee_project, out)
    ledger = pd.read_csv(out / "project_ledger.csv")
    assert set(ledger.columns) == {"project_id", "date", "cumulative_revenue", "cumulative_hours"}
    proj_rows = ledger[ledger["project_id"] == "90001-F"]
    assert not proj_rows.empty
    assert proj_rows["cumulative_revenue"].max() == 28000  # matches final invoiced total


def test_convert_skips_missing_pair(tmp_path, tmp_path_factory):
    write_estimate(tmp_path / "90003_Estimate.csv", [
        ["", "Team Blue:Engineer", "Orphan", 10, 100.00, 1000.00, 150.00, 1500.00, 0.00, 1500.00, "", "Service"],
    ])
    out = tmp_path_factory.mktemp("out")
    log = convert(tmp_path, out)
    assert (log["status"] == "SKIPPED").all()
