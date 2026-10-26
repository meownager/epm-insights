# Findings and Corrective Action Log

## Purpose

This log records findings about the audit process itself — not findings about individual projects. When the audit system produces incorrect results, misses something, or has a threshold that needs adjustment, that is logged here with a follow-up action and resolution status.

Project-level audit findings are in the generated report outputs, not in this log.

## How to Add an Entry

Copy the template below, fill in all fields, and append it to the Active Findings table. When resolved, move the row to the Resolved Findings table and record the resolution date and action taken.

## Entry Template

```
| ID | Date | Description | Root Cause | Corrective Action | Owner | Status | Resolved |
```

## Active Findings

| ID | Date Raised | Description | Root Cause | Corrective Action | Owner | Status |
|---|---|---|---|---|---|---|
| F-002 | 2026-10-15 | Spreadsheet burn tool showed active-project runout dates later than reality | Pending change orders counted as budget; travel forecast from a fixed 14-day window, which misses or repeats lumpy trip spend | Active-projects audit v1 (`docs/active-projects-spec.md`): approved COs only, travel averaged project-to-date, window and Red line scaled to project duration, hours tracked beside dollars. Register v3.0.0 | Syeda M. | In progress |

## Resolved Findings

| ID | Date Raised | Description | Root Cause | Corrective Action Taken | Owner | Date Resolved |
|---|---|---|---|---|---|---|
| F-001 | 2026-07-13 | Run records not yet written to disk | Phase 2 implementation in progress | Criteria version printed to console as interim measure; full run record writing scheduled for Phase 2 completion | Syeda M. | Open |

## Finding ID Format

`F-NNN` where NNN is a zero-padded sequential number starting at 001.

## Document Owner

Syeda M. (smonowar@purdue.edu)
