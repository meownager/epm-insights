-- epm-insights project ID cleanup checks
-- This script standardizes project numbers before joining project, financial, and time data.

CREATE OR REPLACE VIEW normalized_time_log AS
SELECT
    entry_date,
    employee_name,
    CASE
        WHEN project_number IS NULL OR TRIM(project_number) = '' THEN NULL
        WHEN regexp_matches(project_number, '^EP[0-9]+$') THEN regexp_replace(project_number, '^EP', 'EP-')
        ELSE project_number
    END AS project_number,
    project_number AS original_project_number,
    project_title,
    hours,
    task_note
FROM time_log;

CREATE OR REPLACE VIEW project_id_quality_check AS
SELECT
    original_project_number,
    project_number AS normalized_project_number,
    COUNT(*) AS entry_count
FROM normalized_time_log
GROUP BY original_project_number, project_number
ORDER BY normalized_project_number, original_project_number;

CREATE OR REPLACE VIEW time_log_unmatched_projects AS
SELECT
    t.project_number,
    COUNT(*) AS entry_count,
    SUM(CAST(t.hours AS DOUBLE)) AS total_hours
FROM normalized_time_log t
LEFT JOIN approved_projects a
    ON t.project_number = a.project_number
WHERE t.project_number IS NULL
   OR a.project_number IS NULL
GROUP BY t.project_number
ORDER BY t.project_number;

-- Review normalized project numbers
SELECT *
FROM project_id_quality_check;

-- Review time entries that do not match approved projects
SELECT *
FROM time_log_unmatched_projects;
