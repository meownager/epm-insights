# Repository Structure Plan

This structure keeps the project organized for both learning and application development.

```text
epm-insights/
  README.md
  docs/
    project-overview.md
    audit-engine-foundation.md
    repo-structure.md
    data-dictionary.md
    project-plan.md
  data/
    sample/
  sql/
    01_load_data.sql
    02_project_health_checks.sql
    03_audit_metrics.sql
  notebooks/
    01_data_exploration.ipynb
    02_metric_experiments.ipynb
    03_ml_experiments.ipynb
  src/
    epm_insights/
      audit/
      data/
      reports/
      app/
  tests/
```

## Folder Purpose

| Folder | Purpose |
|---|---|
| docs | Project thinking, audit framework, planning, and learning notes |
| data/sample | Synthetic data only |
| sql | SQL queries used for audit analysis |
| notebooks | Learning experiments and data exploration |
| src | Reusable application code |
| tests | Validation checks for audit logic |

## Data Privacy Rule

Only synthetic or public data should be committed to the repository. Real company data should stay local and outside version control.
