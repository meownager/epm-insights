-- Completed Project Health Analysis
-- Computes proposed-vs-actual deviation metrics for completed projects.
--
-- Expected DuckDB views or tables:
--   proposal_projects
--   actual_projects

WITH completed_projects AS (
  SELECT
    p.project_id,
    p.project_name,
    p.client,
    p.project_manager,
    p.project_type,
    CAST(p.proposed_budget AS DOUBLE) AS proposed_budget,
    CAST(a.actual_budget AS DOUBLE) AS actual_budget,
    CAST(p.proposed_hours AS DOUBLE) AS proposed_hours,
    CAST(a.actual_hours AS DOUBLE) AS actual_hours,
    DATE(p.proposed_start_date) AS proposed_start_date,
    DATE(p.proposed_end_date) AS proposed_end_date,
    DATE(a.actual_start_date) AS actual_start_date,
    DATE(a.actual_end_date) AS actual_end_date,
    CAST(p.proposed_resource_count AS DOUBLE) AS proposed_resource_count,
    CAST(a.actual_resource_count AS DOUBLE) AS actual_resource_count,
    a.status,
    a.closeout_notes
  FROM proposal_projects p
  INNER JOIN actual_projects a
    ON p.project_id = a.project_id
  WHERE LOWER(TRIM(COALESCE(a.status, ''))) IN ('completed', 'closed')
),
metrics AS (
  SELECT
    *,
    actual_budget - proposed_budget AS budget_dev_abs,
    CASE
      WHEN proposed_budget = 0 THEN NULL
      ELSE (actual_budget - proposed_budget) / proposed_budget
    END AS budget_dev_pct,
    actual_hours - proposed_hours AS hours_dev_abs,
    CASE
      WHEN proposed_hours = 0 THEN NULL
      ELSE (actual_hours - proposed_hours) / proposed_hours
    END AS hours_dev_pct,
    actual_end_date - proposed_end_date AS schedule_dev_days,
    proposed_end_date - proposed_start_date AS proposed_duration_days,
    actual_end_date - actual_start_date AS actual_duration_days,
    CASE
      WHEN (proposed_end_date - proposed_start_date) = 0 THEN NULL
      ELSE ((actual_end_date - actual_start_date) - (proposed_end_date - proposed_start_date))
        / NULLIF((proposed_end_date - proposed_start_date), 0)
    END AS schedule_dev_pct,
    actual_resource_count - proposed_resource_count AS resource_dev_abs,
    CASE
      WHEN proposed_resource_count = 0 THEN NULL
      ELSE (actual_resource_count - proposed_resource_count) / proposed_resource_count
    END AS resource_dev_pct
  FROM completed_projects
),
scored AS (
  SELECT
    *,
    CASE
      WHEN
        ABS(COALESCE(budget_dev_pct, 0)) <= 0.15
        AND ABS(COALESCE(hours_dev_pct, 0)) <= 0.15
        AND COALESCE(schedule_dev_days, 0) <= 7
      THEN 'Green'
      WHEN
        ABS(COALESCE(budget_dev_pct, 0)) <= 0.30
        AND ABS(COALESCE(hours_dev_pct, 0)) <= 0.30
        AND COALESCE(schedule_dev_days, 0) <= 21
      THEN 'Yellow'
      ELSE 'Red'
    END AS health_status
  FROM metrics
)
SELECT
  project_id,
  project_name,
  client,
  project_manager,
  project_type,
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
  health_status,
  closeout_notes
FROM scored
ORDER BY project_id;
