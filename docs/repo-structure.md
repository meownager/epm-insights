# Repository Structure Plan

This structure keeps the project organized as the audit engine, quality framework, reporting workflow, dashboard, and insights layer grow.

```text
epm-insights/
  README.md
  docs/
    project-overview.md
    prd.md
    system-architecture.md
    project-plan.md
    audit-engine-foundation.md
    completed-project-health.md
    data-dictionary.md
    repo-structure.md
    quality-framework/
  config/
    audit_criteria.yaml
  data/
    sample/
  sql/
  scripts/
  src/
    epm_insights/
      data/
      audit/
      reports/
      app/
      insights/
  tests/
  outputs/
```

## Folder Purpose

| Folder | Purpose |
|---|---|
| docs | Overview, PRD, architecture, plan, and technical notes |
| docs/quality-framework | Audit charter, roles, process steps, review cycle, findings log, external audit alignment map |
| config | Versioned Audit Criteria Register — the only place thresholds live |
| data/sample | Synthetic data only |
| sql | SQL queries used for audit analysis |
| scripts | Thin command-line entry points |
| src/epm_insights | Reusable audit engine, reporting, dashboard, and insights code |
| tests | Known-answer tests for audit logic |
| outputs | Generated reports and run records — local only, never committed |

## Data Privacy Rule

Only synthetic or public data should be committed to the repository. Real company data stays local, outside version control, in git-ignored folders. Reports and run records generated from real data also stay local.
