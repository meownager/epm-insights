"""Known-answer tests for the QuickBooks converter — synthetic fixtures only.

These fixtures mimic the structure of real QuickBooks exports (estimate +
transactions) with entirely fictional numbers. No real company data.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from convert_quickbooks import (
    convert,
    find_pairs,
    parse_estimate,
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


def test_convert_skips_missing_pair(tmp_path, tmp_path_factory):
    write_estimate(tmp_path / "90003_Estimate.csv", [
        ["", "Team Blue:Engineer", "Orphan", 10, 100.00, 1000.00, 150.00, 1500.00, 0.00, 1500.00, "", "Service"],
    ])
    out = tmp_path_factory.mktemp("out")
    log = convert(tmp_path, out)
    assert (log["status"] == "SKIPPED").all()
