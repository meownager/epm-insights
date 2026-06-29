-- Completed Project Health Analysis
-- Computes deviation from proposed values for completed projects.
--
-- Expected tables (or loaded CSV views) and key fields:
--   proposal_projects(project_id, proposed_budget, proposed_hours, proposed_start_date, proposed_end_date, proposed_resource_count)
--   actual_projects(project_id, actual_budget, actual_hours, actual_start_date, actual_end_date, actual_resource_count, status)
--
-- Status compatibility:
-- - Includes projects where status is either COMPLETED or CLOSED (case-insensitive).

WITH base AS (
  SELECT
    p.project_id,
    p.proposed_budget,
    p.proposed_hours,
    DATE(p.proposed_start_date) AS proposed_start_date,
    DATE(p.proposed_end_date) AS proposed_end_date,
    p.proposed_resource_count,
    a.actual_budget,
    a.actual_hours,
    DATE(a.actual_start_date) AS actual_start_date,
    DATE(a.actual_end_date) AS actual_end_date,
    a.actual_resource_count,
    a.status
  FROM proposal_projects p
  INNER JOIN actual_projects a
    ON p.project_id = a.project_id
  WHERE LOWER(COALESCE(a.status, '')) IN ('completed', 'closed')
),
metrics AS (
  SELECT
    project_id,

    proposed_budget,
    actual_budget,
    (actual_budget - proposed_budget) AS budget_dev_abs,
    CASE
      WHEN proposed_budget = 0 THEN NULL
      ELSE (actual_budget - proposed_budget) / proposed_budget
    END AS budget_dev_pct,

    proposed_hours,
    actual_hours,
    (actual_hours - proposed_hours) AS hours_dev_abs,
    CASE
      WHEN proposed_hours = 0 THEN NULL
      ELSE (actual_hours - proposed_hours) / proposed_hours
    END AS hours_dev_pct,

    proposed_start_date,
    proposed_end_date,
    actual_start_date,
    actual_end_date,

    (actual_end_date - proposed_end_date) AS schedule_dev_days,

    (proposed_end_date - proposed_start_date) AS proposed_duration_days,
    (actual_end_date - actual_start_date) AS actual_duration_days,
    CASE
      WHEN (proposed_end_date - proposed_start_date) = 0 THEN NULL
      ELSE ((actual_end_date - actual_start_date) - (proposed_end_date - proposed_start_date))
        / NULLIF((proposed_end_date - proposed_start_date), 0)
    END AS schedule_dev_pct,

    proposed_resource_count,
    actual_resource_count,
    (actual_resource_count - proposed_resource_count) AS resource_dev_abs,
    CASE
      WHEN proposed_resource_count = 0 THEN NULL
      ELSE (actual_resource_count - proposed_resource_count) / proposed_resource_count
    END AS resource_dev_pct
  FROM base
),
scored AS (
  SELECT
    *,
    CASE
      WHEN
        ABS(COALESCE(budget_dev_pct, 0)) <= 0.10
        AND ABS(COALESCE(hours_dev_pct, 0)) <= 0.10
        AND COALESCE(schedule_dev_days, 0) <= 5
      THEN 'Green'
      WHEN
        ABS(COALESCE(budget_dev_pct, 0)) <= 0.20
        AND ABS(COALESCE(hours_dev_pct, 0)) <= 0.20
        AND COALESCE(schedule_dev_days, 0) <= 15
      THEN 'Yellow'
      ELSE 'Red'
    END AS health_status
  FROM metrics
)
SELECT
  project_id,
  proposed_budget,
  actual_budget,
  budget_dev_abs,
  budget_dev_pct,
  proposed_hours,
  actual_hours,
  hours_dev_abs,
  hours_dev_pct,
  proposed_start_date,
  proposed_end_date,
  actual_start_date,
  actual_end_date,
  schedule_dev_days,
  proposed_duration_days,
  actual_duration_days,
  schedule_dev_pct,
  proposed_resource_count,
  actual_resource_count,
  resource_dev_abs,
  resource_dev_pct,
  health_status
FROM scored
ORDER BY project_id;
