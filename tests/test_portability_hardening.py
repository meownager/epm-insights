from __future__ import annotations

import builtins
from pathlib import Path

import pandas as pd
import pytest

from completed_project_health import (
    collect_runtime_diagnostics,
    compute_metrics,
    load_criteria,
    sha256_file,
)
from insights import build_notes_index


CRITERIA = {
    "version": "2.0.0",
    "completed_projects": {
        "eligible_statuses": ["completed", "closed"],
        "fixed_fee": {
            "budget": {"green_max": 0.15, "yellow_max": 0.30},
            "hours": {"green_max": 0.15, "yellow_max": 0.30},
            "schedule": {"green_max_days": 7, "yellow_max_days": 21},
        },
        "t_and_e": {
            "budget": {"green_max": 0.25, "yellow_max": 0.40},
            "hours": {"green_max": 0.15, "yellow_max": 0.30},
            "schedule": {"green_max_days": 7, "yellow_max_days": 21},
        },
    },
}


def _empty_proposal_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "project_id",
        "proposed_budget",
        "proposed_hours",
        "proposed_start_date",
        "proposed_end_date",
        "billing_type",
    ])


def _empty_actual_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "project_id",
        "actual_budget",
        "actual_hours",
        "actual_start_date",
        "actual_end_date",
        "status",
    ])


def test_compute_metrics_handles_empty_inputs():
    result = compute_metrics(_empty_proposal_df(), _empty_actual_df(), CRITERIA)
    assert result.empty
    assert "health_status" in result.columns
    assert "audit_finding" in result.columns


def test_load_criteria_raises_for_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_criteria(missing)


def test_load_criteria_raises_for_invalid_yaml(tmp_path: Path):
    bad = tmp_path / "criteria.yaml"
    bad.write_text("version: [broken", encoding="utf-8")
    with pytest.raises(Exception):
        load_criteria(bad)


def test_sha256_file_handles_unicode_paths(tmp_path: Path):
    path = tmp_path / "überblick.txt"
    path.write_text("portable checksum", encoding="utf-8")
    digest = sha256_file(path)
    assert len(digest) == 64


def test_build_notes_index_gracefully_handles_missing_sklearn(monkeypatch):
    df = pd.DataFrame({"project_id": ["P1"], "closeout_notes": ["vendor delay"]})
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("sklearn"):
            raise ImportError("simulated missing sklearn")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert build_notes_index(df) is None


def test_runtime_diagnostics_flags_mismatches():
    messages = collect_runtime_diagnostics(
        min_python=(99, 0),
        supported_platforms={"ImaginaryOS"},
        dependencies=["definitely-missing-dep-xyz"],
    )
    joined = "\n".join(messages)
    assert "ERROR: Python" in joined
    assert "WARNING: Platform" in joined
    assert "ERROR: Missing dependency" in joined
