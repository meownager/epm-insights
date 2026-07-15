# Criteria Register Management

## What the Register Is

The Audit Criteria Register is the single, authoritative source of all thresholds and parameters that drive audit results. It lives at `config/audit_criteria.yaml`. No threshold exists anywhere else — not in source code, not in scripts, not in documentation.

The audit engine reads the register at runtime on every run. The criteria version used is printed at run start and recorded in the run record.

## Current Register: v2.0.0

File: `config/audit_criteria.yaml`

Thresholds differ by billing type. Fixed fee projects carry budget risk on the company side (overruns hit margin); T&E projects bill actuals to the client (budget risk is lower). Hours and schedule thresholds are identical for both types.

### Fixed Fee (`billing_type: fixed_fee`)

| Parameter | Value | Meaning |
|---|---|---|
| `fixed_fee.budget.green_max` | 0.15 | Budget deviation ≤15% → Green |
| `fixed_fee.budget.yellow_max` | 0.30 | Budget deviation 16–30% → Yellow; >30% → Red |
| `fixed_fee.hours.green_max` | 0.15 | Hours deviation ≤15% → Green |
| `fixed_fee.hours.yellow_max` | 0.30 | Hours deviation 16–30% → Yellow; >30% → Red |
| `fixed_fee.schedule.green_max_days` | 7 | Schedule slip ≤7 days → Green |
| `fixed_fee.schedule.yellow_max_days` | 21 | Schedule slip 8–21 days → Yellow; >21 days → Red |

### Time & Expense (`billing_type: t_and_e`)

| Parameter | Value | Meaning |
|---|---|---|
| `t_and_e.budget.green_max` | 0.25 | Budget deviation ≤25% → Green |
| `t_and_e.budget.yellow_max` | 0.40 | Budget deviation 26–40% → Yellow; >40% → Red |
| `t_and_e.hours.green_max` | 0.15 | Hours deviation ≤15% → Green (same as fixed fee) |
| `t_and_e.hours.yellow_max` | 0.30 | Hours deviation 16–30% → Yellow; >30% → Red (same as fixed fee) |
| `t_and_e.schedule.green_max_days` | 7 | Schedule slip ≤7 days → Green (same as fixed fee) |
| `t_and_e.schedule.yellow_max_days` | 21 | Schedule slip 8–21 days → Yellow; >21 days → Red (same as fixed fee) |

### Eligible Statuses (both billing types)

| Parameter | Value | Meaning |
|---|---|---|
| `eligible_statuses` | completed, closed | Projects in these states are audited |

### Change History

| Version | Date | Reason |
|---|---|---|
| 1.0.0 | 2026-07-01 | Initial register — single threshold set for all projects |
| 2.0.0 | 2026-07-14 | Added billing-type-specific thresholds; fixed fee budget tightened to reflect margin risk; T&E budget loosened to reflect client-pays-actuals model; project IDs updated to NNNNN-F/T format |

## How to Change a Threshold

1. Open `config/audit_criteria.yaml`
2. Update the threshold value
3. Increment the `version` field (e.g., `1.0.0` → `1.1.0`)
4. Update `effective_date` to today's date
5. Update `change_reason` to explain why the threshold changed
6. Log the change in `07-findings-and-corrective-action-log.md`
7. Re-run the audit against synthetic data to confirm results are as expected
8. Commit the updated register

## Version Numbering

Format: `MAJOR.MINOR.PATCH`

- MAJOR: structural change (new metric added, classification logic changed)
- MINOR: threshold value adjusted based on calibration review
- PATCH: editorial corrections (typos, comment updates — no behavior change)

## Why This Matters

Every generated report states the criteria version that produced it. This means any report can be reproduced exactly by running the same input data against the same criteria version. Reports are not valid without a criteria version stamp.

## Document Owner

Syeda M. (smonowar@purdue.edu)
