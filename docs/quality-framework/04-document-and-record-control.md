# Document and Record Control

## Controlled Documents

These documents are part of the quality framework and are version-controlled in the repository. Changes to any of them should be committed with a descriptive message explaining what changed and why.

| Document | Location | Owner |
|---|---|---|
| Audit Charter | `docs/quality-framework/01-audit-charter.md` | Syeda M. |
| Roles and Responsibilities | `docs/quality-framework/02-roles-and-responsibilities.md` | Syeda M. |
| Criteria Register Management | `docs/quality-framework/03-criteria-register-management.md` | Syeda M. |
| Document and Record Control (this file) | `docs/quality-framework/04-document-and-record-control.md` | Syeda M. |
| Defined Process Steps | `docs/quality-framework/05-defined-process-steps.md` | Syeda M. |
| Calibration and Review Cycle | `docs/quality-framework/06-calibration-and-review-cycle.md` | Syeda M. |
| Findings and Corrective Action Log | `docs/quality-framework/07-findings-and-corrective-action-log.md` | Syeda M. |
| External Audit Alignment Map | `docs/quality-framework/08-external-audit-alignment-map.md` | Syeda M. |
| Audit Criteria Register | `config/audit_criteria.yaml` | Syeda M. |
| Data Dictionary | `docs/data-dictionary.md` | Syeda M. |
| System Architecture | `docs/system-architecture.md` | Syeda M. |
| PRD | `docs/prd.md` | Syeda M. |
| Project Plan | `docs/project-plan.md` | Syeda M. |

## Run Records

Every audit run produces a run record. Run records are the audit trail — they prove what inputs were used, which criteria version was applied, and when the run occurred.

**Location:** `outputs/runs/` (local only, never committed)

**Format:** JSON file named `run_<run_id>_<timestamp>.json`

**Contents of each run record:**

| Field | Description |
|---|---|
| `run_id` | Unique identifier for this run (UUID) |
| `timestamp` | ISO 8601 datetime of the run |
| `criteria_version` | Version string from the Audit Criteria Register |
| `criteria_file` | Path to the criteria file used |
| `proposal_file` | Path to the proposal CSV |
| `actual_file` | Path to the actual CSV |
| `proposal_fingerprint` | SHA-256 hash of the proposal file |
| `actual_fingerprint` | SHA-256 hash of the actual file |
| `project_count` | Number of projects audited |
| `health_summary` | Count of Green / Yellow / Red results |

## Data Privacy

Only synthetic or public data is committed to the repository. Real company data stays local in git-ignored folders. Run records generated from real data also stay local and are never committed.

Real data folder (git-ignored): `data/real/` — create this locally; it will not be tracked.

## Document Owner

Syeda M. (smonowar@purdue.edu)
