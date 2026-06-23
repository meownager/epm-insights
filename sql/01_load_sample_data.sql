-- epm-insights SQL load script
-- This script loads the synthetic sample CSV files into DuckDB views.

CREATE OR REPLACE VIEW pre_approved_projects AS
SELECT *
FROM read_csv_auto('data/sample/pre_approved.csv', header = true);

CREATE OR REPLACE VIEW approved_projects AS
SELECT *
FROM read_csv_auto('data/sample/approved.csv', header = true);

CREATE OR REPLACE VIEW financials AS
SELECT *
FROM read_csv_auto('data/sample/financials.csv', header = true);

CREATE OR REPLACE VIEW time_log AS
SELECT *
FROM read_csv_auto('data/sample/time_log.csv', header = true);

-- Quick row count check
SELECT 'pre_approved_projects' AS table_name, COUNT(*) AS row_count FROM pre_approved_projects
UNION ALL
SELECT 'approved_projects' AS table_name, COUNT(*) AS row_count FROM approved_projects
UNION ALL
SELECT 'financials' AS table_name, COUNT(*) AS row_count FROM financials
UNION ALL
SELECT 'time_log' AS table_name, COUNT(*) AS row_count FROM time_log;
