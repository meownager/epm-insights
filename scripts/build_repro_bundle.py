#!/usr/bin/env python3
"""Build a reproducibility bundle from sample data and pinned dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from completed_project_health import compute_metrics, load_criteria
ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PROPOSAL = ROOT / "data" / "sample" / "proposal_projects.csv"
SAMPLE_ACTUAL = ROOT / "data" / "sample" / "actual_projects.csv"
CRITERIA_PATH = ROOT / "config" / "audit_criteria.yaml"
REQS_PATH = ROOT / "requirements.txt"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_bundle(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir = output_dir / "sample_run"
    report_dir.mkdir(parents=True, exist_ok=True)

    criteria = load_criteria(CRITERIA_PATH)
    proposal = pd.read_csv(SAMPLE_PROPOSAL)
    actual = pd.read_csv(SAMPLE_ACTUAL)
    eligible = set(criteria["completed_projects"].get("eligible_statuses", ["completed", "closed"]))
    metrics = compute_metrics(proposal, actual, criteria, eligible)

    detail_out = report_dir / "completed_project_health_detail.csv"
    summary_out = report_dir / "completed_project_health_summary.csv"

    metrics.to_csv(detail_out, index=False)
    (
        metrics.groupby("health_status", dropna=False)
        .size()
        .rename("project_count")
        .reset_index()
        .sort_values("health_status")
        .to_csv(summary_out, index=False)
    )

    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    run_record = {
        "run_id": run_id,
        "timestamp": timestamp,
        "criteria_version": criteria.get("version", "unknown"),
        "criteria_file": str(CRITERIA_PATH.relative_to(ROOT)),
        "proposal_file": str(SAMPLE_PROPOSAL.relative_to(ROOT)),
        "actual_file": str(SAMPLE_ACTUAL.relative_to(ROOT)),
        "proposal_fingerprint": sha256_file(SAMPLE_PROPOSAL),
        "actual_fingerprint": sha256_file(SAMPLE_ACTUAL),
        "project_count": len(metrics),
        "health_summary": metrics["health_status"].value_counts().to_dict(),
    }
    runs_dir = report_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_record_path = runs_dir / "run_repro_sample.json"
    run_record_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "criteria_version": criteria.get("version", "unknown"),
        "requirements_file": str(REQS_PATH.relative_to(ROOT)),
        "requirements_sha256": sha256_file(REQS_PATH),
        "inputs": {
            "proposal": str(SAMPLE_PROPOSAL.relative_to(ROOT)),
            "actual": str(SAMPLE_ACTUAL.relative_to(ROOT)),
            "criteria": str(CRITERIA_PATH.relative_to(ROOT)),
        },
        "artifacts": {
            "detail_csv": str(detail_out.relative_to(output_dir)),
            "summary_csv": str(summary_out.relative_to(output_dir)),
            "run_record": str(run_record_path.relative_to(output_dir)),
        },
        "artifact_hashes": {
            "detail_csv_sha256": sha256_file(detail_out),
            "summary_csv_sha256": sha256_file(summary_out),
            "run_record_sha256": sha256_file(run_record_path),
        },
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    zip_base = output_dir / "epm-insights-repro-bundle"
    shutil.make_archive(str(zip_base), "zip", root_dir=output_dir)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build sample reproducibility bundle")
    parser.add_argument("--output-dir", default="outputs/repro", help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.output_dir)
    manifest = build_bundle(out)
    print("Reproducibility bundle created.")
    print(f"Output directory: {out.resolve()}")
    print(f"Criteria version: {manifest['criteria_version']}")
    print(f"Bundle zip: {(out / 'epm-insights-repro-bundle.zip').resolve()}")


if __name__ == "__main__":
    sys.exit(main())
