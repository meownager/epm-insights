-- epm-insights budget audit checks
-- This script creates first-pass budget and billing position metrics for approved projects.

CREATE OR REPLACE VIEW budget_audit_checks AS
SELECT
    a.project_number,
    a.project_title,
    a.client,
    a.project_manager,
    a.price_type,
    a.class_unit,
    a.status,
    CAST(a.total_value AS DOUBLE) AS approved_total_value,
    CAST(f.total_value AS DOUBLE) AS financial_total_value,
    CAST(a.balance_remaining AS DOUBLE) AS approved_balance_remaining,
    CAST(f.balance_remaining AS DOUBLE) AS financial_balance_remaining,
    CAST(a.billed_pct AS DOUBLE) AS billed_pct,
    CAST(f.co_count AS INTEGER) AS change_order_count,
    CAST(f.total_value AS DOUBLE) - CAST(a.total_value AS DOUBLE) AS value_difference,
    CASE
        WHEN CAST(a.total_value AS DOUBLE) = 0 THEN NULL
        ELSE ROUND((CAST(a.balance_remaining AS DOUBLE) / CAST(a.total_value AS DOUBLE)) * 100, 2)
    END AS balance_remaining_pct,
    CASE
        WHEN CAST(a.total_value AS DOUBLE) = 0 THEN NULL
        ELSE ROUND(((CAST(f.total_value AS DOUBLE) - CAST(a.total_value AS DOUBLE)) / CAST(a.total_value AS DOUBLE)) * 100, 2)
    END AS value_variance_pct,
    CASE
        WHEN CAST(a.billed_pct AS DOUBLE) >= 80 THEN 'Strong billing position'
        WHEN CAST(a.billed_pct AS DOUBLE) >= 50 THEN 'Moderate billing position'
        ELSE 'Low billing position'
    END AS billing_position,
    CASE
        WHEN CAST(a.total_value AS DOUBLE) = 0 THEN 'Review required'
        WHEN (CAST(a.balance_remaining AS DOUBLE) / CAST(a.total_value AS DOUBLE)) <= 0.15 THEN 'Low remaining balance'
        WHEN (CAST(a.balance_remaining AS DOUBLE) / CAST(a.total_value AS DOUBLE)) <= 0.35 THEN 'Moderate remaining balance'
        ELSE 'Healthy remaining balance'
    END AS balance_position,
    CASE
        WHEN CAST(f.co_count AS INTEGER) >= 3 THEN 'High change order activity'
        WHEN CAST(f.co_count AS INTEGER) >= 1 THEN 'Some change order activity'
        ELSE 'No change order activity'
    END AS change_order_position
FROM approved_projects a
LEFT JOIN financials f
    ON a.project_number = f.project_number;

-- Review project budget audit position
SELECT
    project_number,
    project_title,
    client,
    approved_total_value,
    financial_total_value,
    value_variance_pct,
    balance_remaining_pct,
    billed_pct,
    billing_position,
    balance_position,
    change_order_position
FROM budget_audit_checks
ORDER BY project_number;
