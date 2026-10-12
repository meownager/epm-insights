"""Known-answer tests for the local portfolio store (upsert/delete persistence)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from portfolio_store import delete_projects, load_store, upsert


def _metrics(*project_ids):
    return pd.DataFrame([{"project_id": p, "health_status": "Green"} for p in project_ids])


def test_load_store_empty_dir_returns_empty_frames(tmp_path):
    store = load_store(tmp_path / "does_not_exist")
    assert store["metrics"].empty
    assert store["financials"].empty
    assert list(store["ledger"].columns) == ["project_id", "date", "cumulative_revenue", "cumulative_hours"]


def test_upsert_adds_new_projects(tmp_path):
    store = upsert(tmp_path, _metrics("P001", "P002"))
    assert set(store["metrics"]["project_id"]) == {"P001", "P002"}


def test_upsert_persists_to_disk(tmp_path):
    upsert(tmp_path, _metrics("P001"))
    reloaded = load_store(tmp_path)
    assert list(reloaded["metrics"]["project_id"]) == ["P001"]


def test_upsert_replaces_same_project_id(tmp_path):
    upsert(tmp_path, pd.DataFrame([{"project_id": "P001", "health_status": "Red"}]))
    store = upsert(tmp_path, pd.DataFrame([{"project_id": "P001", "health_status": "Green"}]))
    rows = store["metrics"][store["metrics"]["project_id"] == "P001"]
    assert len(rows) == 1
    assert rows["health_status"].iloc[0] == "Green"


def test_upsert_keeps_other_projects_when_replacing_one(tmp_path):
    upsert(tmp_path, _metrics("P001", "P002"))
    store = upsert(tmp_path, _metrics("P001"))
    assert set(store["metrics"]["project_id"]) == {"P001", "P002"}
    assert len(store["metrics"]) == 2


def test_upsert_across_all_three_stores_together(tmp_path):
    metrics = _metrics("P001")
    financials = pd.DataFrame([{"project_id": "P001", "estimate_total": 1000}])
    ledger = pd.DataFrame([{"project_id": "P001", "date": "2026-01-01",
                            "cumulative_revenue": 500, "cumulative_hours": 10}])
    store = upsert(tmp_path, metrics, financials, ledger)
    assert store["financials"]["estimate_total"].iloc[0] == 1000
    assert store["ledger"]["cumulative_revenue"].iloc[0] == 500


def test_delete_removes_only_specified_project(tmp_path):
    upsert(tmp_path, _metrics("P001", "P002", "P003"))
    store = delete_projects(tmp_path, ["P002"])
    assert set(store["metrics"]["project_id"]) == {"P001", "P003"}


def test_delete_persists_to_disk(tmp_path):
    upsert(tmp_path, _metrics("P001", "P002"))
    delete_projects(tmp_path, ["P001"])
    reloaded = load_store(tmp_path)
    assert list(reloaded["metrics"]["project_id"]) == ["P002"]


def test_delete_from_all_three_stores(tmp_path):
    upsert(
        tmp_path,
        _metrics("P001", "P002"),
        pd.DataFrame([{"project_id": "P001", "estimate_total": 1}, {"project_id": "P002", "estimate_total": 2}]),
        pd.DataFrame([{"project_id": "P001", "date": "2026-01-01", "cumulative_revenue": 1, "cumulative_hours": 1}]),
    )
    store = delete_projects(tmp_path, ["P001"])
    assert "P001" not in set(store["metrics"]["project_id"])
    assert "P001" not in set(store["financials"]["project_id"])
    assert "P001" not in set(store["ledger"]["project_id"])
    assert "P002" in set(store["metrics"]["project_id"])


def test_delete_nonexistent_project_is_a_no_op(tmp_path):
    upsert(tmp_path, _metrics("P001"))
    store = delete_projects(tmp_path, ["DOES_NOT_EXIST"])
    assert set(store["metrics"]["project_id"]) == {"P001"}
