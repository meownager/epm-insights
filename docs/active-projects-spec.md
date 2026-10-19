# Active Projects Audit: v1 Spec

**Status:** Draft for review · **Owner:** Syeda M. · **Date:** 2026-10-15

## Problem

EPMs need to know, while a project is still running, whether its budget will last until the planned end date. The current spreadsheet tool answers with a single runout date, and that date has been misleadingly late for two reasons:

1. **Pending change orders count as budget.** Money the client has not approved yet makes the budget look larger.
2. **Travel is forecast from the last 14 days only.** Travel spend comes in bursts around site trips. A window with no trip forecasts $0 of travel; a window with a trip forecasts that trip every week.

The existing `burn_timeline.py` cannot fill the gap: it paces spend across a project's actual start and end dates, so it only works after a project closes.

## Goal

For every active project, answer: **"Will the approved budget run out before the planned end date, and if so, when?"**

## Non-goals for v1

- Hours burn from the time-tracking system (v2)
- Forecasting planned trips entered by the EPM (v2)
- Different burn logic per billing type (v2; v1 records billing type and uses one formula)
- Machine-learning forecasts (v3, after backtesting on closed projects)

## Users and decisions

| User | Decision v1 supports |
|---|---|
| EPM | Issue a change order, adjust staffing, or warn the client |
| Leadership | Which active projects need attention this week |

## Inputs

The engine reads a standard schema. Company-specific exports are converted by adapters (the IES adapter reuses `convert_ies.parse_transactions`).

### `active_projects.csv` (entered once per project by the EPM)

Planned dates are not in the finance export (see the known data gap in `convert_ies.py`), so the EPM provides them.

| Column | Type | Notes |
|---|---|---|
| `project_id` | text | Same ID as the finance export, e.g. `12345-T` |
| `billing_type` | `fixed_fee` \| `t_and_e` \| `hybrid` | |
| `planned_start` | date | |
| `planned_end` | date | Blank allowed; status becomes `Needs input` |

### Transactions (from the finance export, via the adapter)

| Column | Type | Notes |
|---|---|---|
| `project_id` | text | |
| `date` | date | |
| `kind` | `budget` \| `change_order` \| `time` \| `expense` | Bills count as `expense`; invoices and payments are ignored (billing, not burn) |
| `amount` | number | Credit memos and reversals are negative |
| `approved` | true \| false | For `budget` and `change_order` rows only |

## Calculations

All values are as of `as_of_date` (default: the latest transaction date). Settings come from the criteria register, never from code.

| Output | Formula |
|---|---|
| `approved_budget` | sum of approved `budget` + approved `change_order` amounts (an approved CO already inside the estimate is not added twice) |
| `pending_co` | sum of unapproved `change_order` amounts |
| `spent_to_date` | sum of `time` + `expense` amounts up to `as_of_date` |
| `remaining` | `approved_budget - spent_to_date` |
| `time_burn_wk` | `time` spent in the last `window_weeks` weeks ÷ `window_weeks` |
| `expense_burn_wk` | `expense` spent project-to-date ÷ weeks since `planned_start` (minimum 1). Averaging the whole project smooths travel bursts |
| `weekly_burn` | `time_burn_wk + expense_burn_wk` |
| `runout_date` | `as_of_date + floor(remaining ÷ weekly_burn × 7)` days. Rounded down so the warning comes earlier, not later |
| `days_early` | `planned_end - runout_date`. Positive means the money runs out before the planned end |
| `spend_at_planned_end` | `spent_to_date + weekly_burn × weeks until planned_end` |
| `variance_at_planned_end` | `approved_budget - spend_at_planned_end` |
| `runout_if_pending_approved` | Same as `runout_date`, using `remaining + pending_co`. Shown beside the main date, never instead of it |
| `burn_index` | `% budget used ÷ % planned time elapsed`. Informational: above 1.0 means spending faster than time is passing |

## Health status

Thresholds live in a new `active_projects` section of `config/audit_criteria.yaml`. The starting values below are placeholders to calibrate in v3.

| Status | Rule |
|---|---|
| Red | `remaining ≤ 0` (over budget), or `days_early > red_days_early` (start: 14) |
| Yellow | `0 < days_early ≤ red_days_early` |
| Green | `runout_date` on or after `planned_end` |
| Needs input | Missing `approved_budget` or `planned_end` |

**First-crossing alert:** each run stores the status per project in the portfolio store, so the dashboard shows the date a project first turned Yellow or Red (same idea as `first_crossing_dates` in `burn_timeline.py`).

## Edge cases

- `weekly_burn = 0`: `runout_date` shows "No recent spend"; status uses `remaining` only.
- Fewer than `window_weeks` of history: divide by the weeks actually elapsed.
- Spend after `as_of_date` is ignored, so reruns on old exports are reproducible.
- `planned_end` already passed while the project is active: status Red, reason "past planned end".

## Outputs

1. **Portfolio table**, one row per active project, sorted by `days_early` (worst first): status, `remaining`, `weekly_burn`, `runout_date`, `runout_if_pending_approved`, `planned_end`, `days_early`.
2. **Project chart**: cumulative actual spend, the forecast line to `runout_date`, the approved-budget line, the pending-CO budget as a dashed line, and the planned end marker.
3. **Run record** (existing mechanism): run ID, criteria version, input fingerprints.

## Test cases (known answers)

All share: `approved_budget` 100,000; `spent_to_date` 40,000; `planned_start` 2025-12-21; `as_of_date` 2026-03-01 (10 weeks elapsed); `window_weeks` 4; time spent in the window 20,000; expenses project-to-date 8,000, none in the last 4 weeks.

So `time_burn_wk` = 5,000, `expense_burn_wk` = 800, `weekly_burn` = 5,800, `remaining` = 60,000, `runout_date` = 2026-05-12 (72 days).

| Case | `planned_end` | Other input | Expected |
|---|---|---|---|
| 1. Runs out early | 2026-06-30 | | `days_early` 49, Red, `variance_at_planned_end` -40,257.14 |
| 2. On track | 2026-05-01 | | `days_early` -11, Green, `variance_at_planned_end` 9,457.14 |
| 3. Slightly early | 2026-05-20 | | `days_early` 8, Yellow |
| 4. Pending CO | 2026-06-30 | `pending_co` 20,000 | `runout_date` still 2026-05-12 and Red; `runout_if_pending_approved` 2026-06-05 |
| 5. Over budget | 2026-06-30 | `spent_to_date` 105,000 | `remaining` -5,000, Red, reason "over budget" |
| 6. Travel burst | as case 1 | | `expense_burn_wk` is 800, not 0: a 14-day window with no trip would have forecast $0 of travel |

## Definition of done

- One command produces the portfolio table and run record from sample data.
- All test cases above pass, plus a **parity test**: configured to mimic the spreadsheet (14-day window for both time and expenses, pending COs counted as budget), v1 reproduces the spreadsheet's runout date to the day for the same export.
- An Active Projects tab in the dashboard shows the table and chart.
- Real data stays in `data/real/` and never reaches GitHub.

## Open questions

1. Is 4 weeks the right default `window_weeks` for time spend?
2. Is 14 days early the right Red line?
3. Do accepted change orders always appear inside the IES estimate, or sometimes only as separate rows?
