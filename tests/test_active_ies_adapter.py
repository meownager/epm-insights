"""Tests for the Active Projects adapter, upload checks, status history and CLI.

Upload-check cases follow the "Upload checks" table in docs/active-projects-spec.md.
All inputs are synthetic and built in tmp_path.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from active_ies_adapter import (
    UploadBlocked, coverage_warnings, load_ies_folder, time_entries_from_frame, transactions_from_ies,
)
from portfolio_store import first_crossings, record_active_status
from run_active_audit import run

ROOT = Path(__file__).parent.parent
TODAY = "2026-10-26"


# %% IES transactions %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def _ies_csv(tmp_path, rows, name="sales.csv"):
    lines = ["Status: All statuses Date: All",
             "Date,Type,No.,From / To,Memo,Amount,Status"]
    lines += [",".join(str(v) for v in r) for r in rows]
    path = tmp_path / name
    path.write_text("\n".join(lines))
    return path


IES_ROWS = [
    ("10/23/2026", "Purchase Order", "1", "Vendor A", "", 8000, "open"),
    ("09/24/2026", "Change Order", "2", "Client 12345-F", "", 7000, "open"),
    ("09/01/2026", "Change Order", "3", "Client 12345-F", "", 900, "rejected"),
    ("08/26/2026", "Invoice", "4", "Client 12345-F", "", 50000, "paid"),
    ("08/17/2026", "Change Order", "5", "Client 12345-F", "", 5000, "accepted"),
    ("08/10/2026", "Bill", "6", "Vendor B", "", 9000, "open"),
    ("08/10/2026", "Bill", "6", "Vendor B", "", 9000, "paid"),
    ("08/05/2026", "Time Charge", "", "Client 12345-F", "", 1200, "applied"),
    ("07/27/2026", "Estimate", "7", "Client 12345-F", "", 100000, "accepted"),
]


def test_ies_rows_map_to_standard_kinds(tmp_path):
    tx, report = transactions_from_ies(_ies_csv(tmp_path, IES_ROWS))
    assert set(tx["project_id"]) == {"12345-F"}  # read from the From / To column
    by_kind = tx.groupby("kind")["amount"].sum()
    assert by_kind["budget"] == 100000
    assert by_kind["time"] == 1200
    assert by_kind["expense"] == 9000          # duplicate open bill dropped
    assert by_kind["commitment"] == 8000       # open PO kept visible, not counted
    assert 50000 not in tx["amount"].values  # the invoice: billing, not burn
    assert any("duplicate" in w for w in report.warnings)


def test_change_order_approval_follows_ies_status(tmp_path):
    tx, report = transactions_from_ies(_ies_csv(tmp_path, IES_ROWS))
    co = tx[tx["kind"] == "change_order"].set_index("amount")["approved"]
    assert co[5000]                               # accepted
    assert not co[7000]                           # open -> pending
    assert 900 not in co.index                    # rejected never counts
    assert "1 rejected" in report.summary


def test_not_an_ies_sheet_blocks(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("a,b\n1,2\n")
    with pytest.raises(UploadBlocked, match="IES transactions"):
        transactions_from_ies(path)


def test_adapter_output_runs_through_engine(tmp_path):
    tx, _ = transactions_from_ies(_ies_csv(tmp_path, IES_ROWS))
    projects = pd.DataFrame([{"project_id": "12345-F", "billing_type": "fixed_fee",
                              "planned_start": "2026-07-27", "planned_end": "2027-01-29"}])
    criteria = yaml.safe_load((ROOT / "config" / "audit_criteria.yaml").read_text())
    r = run(projects, tx, None, criteria, as_of="2026-10-23").iloc[0]
    assert r["approved_budget"] == 105000   # estimate + accepted CO
    assert r["pending_co"] == 7000
    assert r["spent_to_date"] == 10200      # time + deduplicated bill; PO not counted
    assert r["warning"] == "no time entries"


# %% timesheet upload checks %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def _timesheet(**overrides):
    rows = [
        {"username": "a", "local_date": "2026-10-20", "jobcode_2": "12345-F - Plant", "hours": 8,
         "billable": "Yes", "approved_status": "approved", "notes": "Total rework of panel"},
        {"username": "b", "local_date": "2026-10-21", "jobcode_2": "12345-F - Plant", "hours": 4,
         "billable": "No", "approved_status": "unapproved", "notes": ""},
        {"username": "c", "local_date": "2026-10-22", "jobcode_2": "12345-F - Plant", "hours": 2,
         "billable": "Yes", "approved_status": "rejected", "notes": ""},
        {"username": "a", "local_date": "2026-10-22", "jobcode_2": "Admin - In Office", "hours": 1,
         "billable": "No", "approved_status": "approved", "notes": ""},
    ]
    df = pd.DataFrame(rows)
    for k, v in overrides.items():
        df[k] = v
    return df


def test_one_line_summary():
    te, report = time_entries_from_frame(_timesheet(), today=TODAY)
    assert report.summary == ("3 entries: 1 approved, 1 unapproved (counted), 1 rejected (excluded), "
                              "0 total rows removed, 1 overhead entries skipped.")
    assert report.warnings == []
    assert te["billable"].tolist() == [True, False, True]


def test_note_starting_with_total_is_not_a_total_row():
    te, _ = time_entries_from_frame(_timesheet(), today=TODAY)
    assert 8 in te["hours"].values


def test_missing_required_columns_block():
    with pytest.raises(UploadBlocked, match="doesn't look like a timesheet"):
        time_entries_from_frame(_timesheet().drop(columns="jobcode_2"), today=TODAY)


def test_no_approval_column_warns_and_counts_everything():
    te, report = time_entries_from_frame(_timesheet().drop(columns="approved_status"), today=TODAY)
    assert (te["approval"] == "approved").all()
    assert "Approval status unknown; all hours counted" in report.warnings


def test_no_unapproved_hours_warns():
    _, report = time_entries_from_frame(_timesheet(approved_status="approved"), today=TODAY)
    assert any(w.startswith("No unapproved hours found") for w in report.warnings)


def test_grand_total_row_removed_and_reported():
    ts = pd.concat([_timesheet(), pd.DataFrame([{"username": "Grand Total", "hours": 15}])])
    te, report = time_entries_from_frame(ts, today=TODAY)
    assert te["hours"].sum() == 14
    assert "1 total row removed" in report.summary


def test_stale_export_warns():
    _, report = time_entries_from_frame(_timesheet(), today="2026-11-16")
    assert "Timesheet ends on 2026-10-22; recent hours are missing" in report.warnings


def test_project_without_inputs_warns_on_its_row():
    projects = pd.DataFrame({"project_id": ["A", "B", "C"]})
    tx = pd.DataFrame({"project_id": ["A", "B"]})
    te = pd.DataFrame({"project_id": ["A"]})
    assert coverage_warnings(projects, tx, te) == {
        "B": "no time entries", "C": "no transactions and no time entries"}


def test_load_ies_folder_combines_duplicate_timesheets(tmp_path):
    for pid in ("12345-F", "67890-T"):
        folder = tmp_path / pid
        folder.mkdir()
        _ies_csv(folder, [("07/27/2026", "Estimate", "1", f"Client {pid}", "", 1000, "accepted")])
        _timesheet().to_csv(folder / "timesheet_report.csv", index=False)  # same export twice
    tx, te, reports = load_ies_folder(tmp_path, today=TODAY)
    assert set(tx["project_id"]) == {"12345-F", "67890-T"}
    assert len(te) == 3  # not 6
    assert len(reports) == 3


# %% status history %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def _results(as_of, statuses):
    return pd.DataFrame([{"project_id": p, "as_of_date": as_of, "status": s, "driver": "budget"}
                         for p, s in statuses.items()])


def test_first_crossing_dates_and_rerun_does_not_duplicate(tmp_path):
    record_active_status(tmp_path, _results("2026-10-02", {"A": "Green", "B": "Yellow"}))
    record_active_status(tmp_path, _results("2026-10-09", {"A": "Yellow", "B": "Red"}))
    record_active_status(tmp_path, _results("2026-10-16", {"A": "Red", "B": "Yellow"}))
    history = record_active_status(tmp_path, _results("2026-10-16", {"A": "Red", "B": "Yellow"}))
    assert len(history) == 6
    fc = first_crossings(history).set_index("project_id")
    assert fc.loc["A", "first_yellow"] == "2026-10-09"
    assert fc.loc["A", "first_red"] == "2026-10-16"
    assert fc.loc["B", "first_yellow"] == "2026-10-02"  # Yellow first, then Red, then back
    assert fc.loc["B", "first_red"] == "2026-10-09"


# %% one command on sample data %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def test_sample_data_covers_every_status():
    criteria = yaml.safe_load((ROOT / "config" / "audit_criteria.yaml").read_text())
    s = ROOT / "data" / "sample"
    r = run(pd.read_csv(s / "active_projects.csv"), pd.read_csv(s / "active_transactions.csv"),
            pd.read_csv(s / "active_time_entries.csv"), criteria)
    assert set(r["status"]) == {"Green", "Yellow", "Red", "Needs input"}
    assert r.set_index("project_id").loc["90003-F", "rolled_up"] == "90004-F"
    assert r["status"].iloc[0] == "Needs input"  # worst first
