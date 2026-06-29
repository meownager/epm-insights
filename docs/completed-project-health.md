# Completed Project Health Analysis (Deviation from Proposed Values)

This document defines the primary-scope analysis for **completed projects**.

Status compatibility:
- Includes projects with `status` set to either `completed` or `closed`.

## Objective

Measure deviation between proposed and actual values, then classify project health using transparent threshold rules.

## Input data (minimum)

### `proposal_projects.csv`
Required columns:
- `project_id`
- `proposed_budget`
- `proposed_hours`
- `proposed_start_date`
- `proposed_end_date`
- `proposed_resource_count` *(optional but recommended)*

### `actual_projects.csv`
Required columns:
- `project_id`
- `actual_budget`
- `actual_hours`
- `actual_start_date`
- `actual_end_date`
- `status` *(accepted values: `completed` or `closed`)*
- `actual_resource_count` *(optional but recommended)*

## Metrics

- `budget_dev_abs = actual_budget - proposed_budget`
- `budget_dev_pct = (actual_budget - proposed_budget) / proposed_budget`
- `hours_dev_abs = actual_hours - proposed_hours`
- `hours_dev_pct = (actual_hours - proposed_hours) / proposed_hours`
- `schedule_dev_days = actual_end_date - proposed_end_date`
- `proposed_duration_days = proposed_end_date - proposed_start_date`
- `actual_duration_days = actual_end_date - actual_start_date`
- `schedule_dev_pct = (actual_duration_days - proposed_duration_days) / proposed_duration_days`
- `resource_dev_abs = actual_resource_count - proposed_resource_count` *(if available)*
- `resource_dev_pct = (actual_resource_count - proposed_resource_count) / proposed_resource_count` *(if available)*

## Health rules (v1)

- **Green**: `|budget_dev_pct| <= 10%` AND `|hours_dev_pct| <= 10%` AND `schedule_dev_days <= 5`
- **Yellow**: `|budget_dev_pct| <= 20%` AND `|hours_dev_pct| <= 20%` AND `schedule_dev_days <= 15`
- **Red**: everything else

## SQL implementation

Use:
- `sql/completed_project_health.sql`

## Python runner

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
