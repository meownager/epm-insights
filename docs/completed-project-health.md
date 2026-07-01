# Completed Project Health MVP

## Purpose

This MVP audits completed engineering projects by comparing the proposed baseline against the actual outcome.

The goal is not to punish a project with a rigid score. The goal is to give project managers and leadership a clear, repeatable view of where the project moved away from the plan and what should be reviewed during closeout.

## Immediate Scope

For each completed project, calculate deviation for:

- Budget
- Hours
- Duration or schedule
- Resource count, when available

This phase does not include active-project forecasting, sprint analysis, vendor scoring, AI recommendations, or dashboard visuals.

## Required Input Files

### proposal_projects.csv

Baseline or planned project values.

Required columns:

- `project_id`
- `project_name`
- `proposed_budget`
- `proposed_hours`
- `proposed_start_date`
- `proposed_end_date`

Optional columns:

- `proposed_resource_count`
- `project_manager`
- `client`
- `project_type`

### actual_projects.csv

Actual project outcome values.

Required columns:

- `project_id`
- `actual_budget`
- `actual_hours`
- `actual_start_date`
- `actual_end_date`
- `status`

Optional columns:

- `actual_resource_count`
- `closeout_notes`

Accepted status values:

- `completed`
- `closed`

Use `completed` as the preferred project language. `closed` is accepted only for compatibility with source systems that use that status label.

## Metrics

| Metric | Formula | Meaning |
|---|---|---|
| `budget_dev_abs` | `actual_budget - proposed_budget` | Dollar difference from proposed budget |
| `budget_dev_pct` | `(actual_budget - proposed_budget) / proposed_budget` | Budget variance percentage |
| `hours_dev_abs` | `actual_hours - proposed_hours` | Labor-hour difference from estimate |
| `hours_dev_pct` | `(actual_hours - proposed_hours) / proposed_hours` | Hours variance percentage |
| `schedule_dev_days` | `actual_end_date - proposed_end_date` | Days late or early against planned end date |
| `schedule_dev_pct` | `(actual_duration_days - proposed_duration_days) / proposed_duration_days` | Duration variance percentage |
| `resource_dev_abs` | `actual_resource_count - proposed_resource_count` | Resource-count difference, when available |
| `resource_dev_pct` | `(actual_resource_count - proposed_resource_count) / proposed_resource_count` | Resource-count variance percentage, when available |

## Advisory Health Rules

The first thresholds should be forgiving because this is a calibration version. The colors are review signals, not final judgments.

Default v1 thresholds:

| Health | Budget | Hours | Schedule Slip |
|---|---:|---:|---:|
| Green | within +/- 15% | within +/- 15% | <= 7 days late |
| Yellow | within +/- 30% | within +/- 30% | <= 21 days late |
| Red | beyond yellow range | beyond yellow range | > 21 days late |

Classification logic:

- Green means all required metrics are within the green range.
- Yellow means at least one required metric is outside green, but all required metrics are within yellow.
- Red means at least one required metric is outside yellow.

Resource count is included in the detail output when available, but it should not drive the first health color until enough real project history exists to calibrate useful thresholds.

## Outputs

The MVP should produce:

- Project-level health table
- Summary counts by Green, Yellow, and Red
- Simple findings explaining the largest deviations

## SQL Implementation

Use:

- `sql/completed_project_health.sql`

## Python Runner

Use:

- `scripts/completed_project_health.py`

Run:

```bash
python scripts/completed_project_health.py \
  --proposal data/sample/proposal_projects.csv \
  --actual data/sample/actual_projects.csv \
  --output-dir outputs
```

Outputs:

- `outputs/completed_project_health_detail.csv`
- `outputs/completed_project_health_summary.csv`

## Short Report Template

```markdown
# Completed Project Audit Report

## Project Summary

- Project:
- Project Manager:
- Client:
- Final Health:

## Proposed vs Actual

| Area | Proposed | Actual | Deviation |
|---|---:|---:|---:|
| Budget |  |  |  |
| Hours |  |  |  |
| Schedule |  |  |  |
| Resources |  |  |  |

## Key Findings

-

## Closeout Notes

-

## Recommended Follow-Up

-
```
