# Defined Process Steps

## Overview

This document defines each stage of the audit pipeline — inputs, outputs, pass criteria, and what happens on failure. Every run follows these steps in order.

---

## Step 1: Load Input Data

**Inputs:**
- Proposal CSV (`proposal_projects.csv` or equivalent)
- Actual CSV (`actual_projects.csv` or equivalent)

**Process:** Read both files into memory.

**Pass criteria:** Both files exist and are readable.

**On failure:** Run stops. Plain-language error message states which file is missing or unreadable.

---

## Step 2: Validate Columns

**Inputs:** Loaded DataFrames from Step 1.

**Required proposal columns:** `project_id`, `proposed_budget`, `proposed_hours`, `proposed_start_date`, `proposed_end_date`

**Required actual columns:** `project_id`, `actual_budget`, `actual_hours`, `actual_start_date`, `actual_end_date`, `status`

**Pass criteria:** All required columns are present in both files.

**On failure:** Run stops. Error message lists every missing column by name.

---

## Step 3: Load Audit Criteria Register

**Inputs:** `config/audit_criteria.yaml`

**Process:** Read the register and extract thresholds and eligible statuses. Print the criteria version to the console.

**Pass criteria:** File exists, is valid YAML, and contains all required threshold keys.

**On failure:** Run stops. Error message states which keys are missing.

---

## Step 4: Filter Eligible Projects

**Inputs:** Merged dataset from Steps 1–2, eligible statuses from Step 3.

**Process:** Keep only rows where `status` matches an eligible status (case-insensitive). For the completed-project slice, eligible statuses are `completed` and `closed`.

**Pass criteria:** At least one eligible project remains after filtering.

**On failure:** Run completes with a warning that zero projects were eligible.

---

## Step 5: Compute Deviation Metrics

**Inputs:** Filtered dataset from Step 4.

**Metrics computed:**

| Metric | Formula |
|---|---|
| `budget_dev_abs` | `actual_budget − proposed_budget` |
| `budget_dev_pct` | `budget_dev_abs / proposed_budget` |
| `hours_dev_abs` | `actual_hours − proposed_hours` |
| `hours_dev_pct` | `hours_dev_abs / proposed_hours` |
| `schedule_dev_days` | `actual_end_date − proposed_end_date` (calendar days) |
| `proposed_duration_days` | `proposed_end_date − proposed_start_date` |
| `actual_duration_days` | `actual_end_date − actual_start_date` |
| `schedule_dev_pct` | `(actual_duration − proposed_duration) / proposed_duration` |
| `resource_dev_abs` | `actual_resource_count − proposed_resource_count` |
| `resource_dev_pct` | `resource_dev_abs / proposed_resource_count` |

**Pass criteria:** Metrics computed without errors. Missing values recorded as `NaN` (not silently set to zero).

---

## Step 6: Classify Health

**Inputs:** Deviation metrics from Step 5, thresholds from Step 3.

**Logic (all three conditions must hold for Green; any one violation determines the classification):**

```
if |budget_dev_pct| ≤ green_max AND |hours_dev_pct| ≤ green_max AND schedule_dev_days ≤ green_max_days:
    → Green
elif |budget_dev_pct| ≤ yellow_max AND |hours_dev_pct| ≤ yellow_max AND schedule_dev_days ≤ yellow_max_days:
    → Yellow
else:
    → Red
```

NaN metric values are treated as zero deviation (benefit of the doubt).

**Pass criteria:** Every eligible project receives exactly one health classification.

---

## Step 7: Generate Structured Findings

**Inputs:** Classified dataset from Step 6.

**Process:** For each project, compose a plain-language finding string listing all three deviation values. If metrics could not be computed, the finding states that review is required.

**Pass criteria:** Every project has a non-empty `audit_finding` value.

---

## Step 8: Write Outputs

**Outputs:**
- `outputs/completed_project_health_detail.csv` — one row per project, all metrics and classifications
- `outputs/completed_project_health_summary.csv` — project count by health status

**Pass criteria:** Both files written successfully to the output directory.

---

## Step 9: Write Run Record

**Output:** `outputs/runs/run_<id>_<timestamp>.json`

**Contents:** Run ID, timestamp, criteria version, criteria file path, input file paths, input file SHA-256 fingerprints, project count, health summary.

**Pass criteria:** Run record written before the process exits.

**Note:** Run record writing is planned for Phase 2 completion. The current runner prints criteria version to the console as an interim traceability measure.

---

## Document Owner

Syeda M. (smonowar@purdue.edu)
