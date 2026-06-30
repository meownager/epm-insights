# Sample Data

This folder is reserved for synthetic sample data used by epm-insights.

Only synthetic or public-safe files should be stored here. Real company data should stay outside the repository.

Expected sample files:

- `proposal_projects.csv`
- `actual_projects.csv`
- `financials.csv`
- `time_log.csv`

These files will support audit engine testing, SQL query development, dashboard examples, and report output validation.

## Closed Project MVP Files

The closed-project MVP uses:

- `proposal_projects.csv` for planned baseline values
- `actual_projects.csv` for final closed or completed outcomes

The other sample files are still useful for future detailed checks, but the first closed-project health calculation should run from the proposal and actual project files.
