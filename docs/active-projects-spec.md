# Active Projects Audit: v1 Spec

**Status:** Draft for review · **Owner:** Syeda M. · **Date:** 2026-10-15

## Problem

EPMs need to know, while a project is still running, whether its budget will last until the planned end date. The current spreadsheet tool answers with a single runout date, and that date has been misleadingly late for two reasons:

1. **Pending change orders count as budget.** Money the client has not approved yet makes the budget look larger.
2. **Travel is forecast from the last 14 days only.** Travel spend comes in bursts around site trips. A window with no trip forecasts $0 of travel; a window with a trip forecasts that trip every week.

The existing `burn_timeline.py` cannot fill the gap: it paces spend across a project's actual start and end dates, so it only works after a project closes.

## Goal

For every active project, answer: **"Will the approved budget or the approved hours run out before the planned end date, and if so, when?"** Both are tracked side by side: dollars used and left, hours used and left, and the effective rate the hours are being charged at.

## Non-goals for v1

- Computing dollars from hours × each person's rate and OT/travel multipliers (the rate engine, v2). v1 uses the dollars the finance system already charged, and shows the effective rate
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
| `billing_type` | `fixed_fee` \| `t_and_e` \| `hybrid` | `t_and_e` = time and expense, also called T&M (time and materials) |
| `planned_start` | date | |
| `planned_end` | date | Blank allowed; status becomes `Needs input` |
| `parent_project_id` | text, optional | Set when a change order arrives as its own project/PO |
| `roll_up` | `yes` \| `no`, default `no` | `yes`: merged into the parent. `no`: tracked on its own, listed under the parent |

### Change orders that arrive as a new project/PO

Some change orders come as a separate project or PO instead of a line on the original estimate. It depends on the change, so the EPM decides per project:

- **Not linked (default):** a normal standalone project.
- **Linked, `roll_up: yes`:** the child's budget and spend are added to the parent. The family gets one runout date, measured against the latest `planned_end` in the family.
- **Linked, `roll_up: no`:** the child keeps its own status and runout date, and the portfolio table shows it indented under its parent.

### Transactions (from the finance export, via the adapter)

| Column | Type | Notes |
|---|---|---|
| `project_id` | text | |
| `date` | date | |
| `kind` | `budget` \| `change_order` \| `time` \| `expense` | Bills count as `expense`; invoices and payments are ignored (billing, not burn) |
| `amount` | number | Credit memos and reversals are negative |
| `approved` | true \| false | For `budget` and `change_order` rows only |
| `hours` | number, optional | Budgeted labor hours on `budget` and `change_order` rows (from the estimate's labor lines) |

### Time entries (from the time-tracking export, via the adapter)

The existing `convert_ies.parse_timesheet` already reads this export.

| Column | Type | Notes |
|---|---|---|
| `project_id` | text | Matched from the job code |
| `date` | date | |
| `person` | text | |
| `hours` | number | |
| `approval` | `approved` \| `unapproved` \| `rejected` | |
| `billable` | true \| false | |

Rules for time entries:

- **Unapproved hours count.** Waiting for approval would delay the warning, and rejected or corrected entries only make the forecast slightly pessimistic, which is the safe direction. The table shows how many counted hours are unapproved.
- **Rejected hours never count.**
- **Summary rows are dropped.** The export ends with a grand-total row; the adapter must remove it explicitly, not by accident.
- **Hours budget counts all project hours** (billable and non-billable), because both consume the planned effort. To confirm with the business.

## Upload checks

EPMs upload raw exports, so the app checks each upload and says what it found before showing any numbers. A check either **blocks** (the upload cannot be used) or **warns** (results shown, with the warning beside them).

| Check | Result |
|---|---|
| Required columns missing (date, job code, hours) | Block: "This doesn't look like a timesheet export" |
| No `approval` column | Warn: "Approval status unknown; all hours counted" |
| No unapproved entries at all | Warn: "No unapproved hours found. If your export filtered to approved only, re-export with all entries for the latest picture" |
| Summary or grand-total rows | Removed automatically, and reported ("1 total row removed") |
| Export ends more than 7 days before today | Warn: "Timesheet ends on <date>; recent hours are missing" |
| A project in `active_projects.csv` has no time entries or no transactions | Warn on that project's row |

After every upload the app shows a one-line summary, for example: "1,240 entries: 1,228 approved, 12 unapproved (counted), 0 rejected (excluded), 1 total row removed."

## Calculations

All values are as of `as_of_date` (default: the latest transaction date). Settings come from the criteria register, never from code.

| Output | Formula |
|---|---|
| `approved_budget` | sum of approved `budget` + approved `change_order` amounts (an approved CO already inside the estimate is not added twice) |
| `pending_co` | sum of unapproved `change_order` amounts, plus any unapproved `budget` lines, so nothing unapproved silently disappears |
| `spent_to_date` | sum of `time` + `expense` amounts up to `as_of_date` |
| `remaining` | `approved_budget - spent_to_date` |
| `planned_duration` | `planned_end - planned_start`, in days |
| `window_days` | `window_pct × planned_duration` rounded to whole days, kept between `window_min_days` and `window_max_days` (start: 25%, 3, 28). Short projects get a short window |
| `time_burn_wk` | `time` spent in the last `window_days` ÷ (`window_days` ÷ 7) |
| `expense_burn_wk` | `expense` spent project-to-date ÷ weeks since `planned_start` (minimum 1). Averaging the whole project smooths travel bursts |
| `weekly_burn` | `time_burn_wk + expense_burn_wk` |
| `runout_date` | `as_of_date + floor(remaining ÷ weekly_burn × 7)` days. Rounded down so the warning comes earlier, not later |
| `days_early` | `planned_end - runout_date`. Positive means the money runs out before the planned end |
| `spend_at_planned_end` | `spent_to_date + weekly_burn × weeks until planned_end` |
| `variance_at_planned_end` | `approved_budget - spend_at_planned_end` |
| `runout_if_pending_approved` | Same as `runout_date`, using `remaining + pending_co`. Shown beside the main date, never instead of it |
| `burn_index` | `% budget used ÷ % planned time elapsed`. Informational: above 1.0 means spending faster than time is passing |

### Hours (same rules, measured in hours)

| Output | Formula |
|---|---|
| `approved_hours` | budgeted hours on approved `budget` + approved `change_order` rows |
| `hours_used` | sum of time-entry `hours` up to `as_of_date` |
| `hours_remaining` | `approved_hours - hours_used` |
| `hours_burn_wk` | hours in the last `window_days` ÷ (`window_days` ÷ 7) |
| `hours_runout_date` | `as_of_date + floor(hours_remaining ÷ hours_burn_wk × 7)` days |
| `hours_days_early` | `planned_end - hours_runout_date` |
| `effective_rate` | `time` dollars in the window ÷ hours in the window. A rising rate means more OT, premium or senior hours, so dollars will run out before hours |

## Health status

Thresholds live in a new `active_projects` section of `config/audit_criteria.yaml`. The starting values below are placeholders to calibrate in v3.

| Status | Rule |
|---|---|
| Red | `remaining ≤ 0` (over budget), or `days_early > red_line_days` |
| Yellow | `0 < days_early ≤ red_line_days` |
| Green | `runout_date` on or after `planned_end` |
| Needs input | Missing `approved_budget` or `planned_end` |

The same rules apply separately to dollars and to hours. **The project's status is the worse of the two**, and the table says which one drove it (`budget` or `hours`). If `approved_hours` is missing, status uses dollars only and flags "hours not measured".

`red_line_days` = `red_pct × planned_duration`, at least `red_min_days` (start: 10%, 1 day). A fixed number of days would never turn a 1-week project Red, and would be too strict for a year-long one.

| Planned duration | `window_days` | Red when money runs out more than |
|---|---|---|
| 20 weeks | 28 (the cap) | 14 days early |
| 4 weeks | 7 | 2.8 days early |
| 1 week | 3 (the floor) | 1 day early |

**First-crossing alert:** each run stores the status per project in the portfolio store, so the dashboard shows the date a project first turned Yellow or Red (same idea as `first_crossing_dates` in `burn_timeline.py`).

## Edge cases

- `weekly_burn = 0`: `runout_date` shows "No recent spend"; status uses `remaining` only.
- Less history than `window_days`: divide by the days actually elapsed.
- Spend after `as_of_date` is ignored, so reruns on old exports are reproducible.
- `planned_end` already passed while the project is active: status Red, reason "past planned end".

## Outputs

1. **Portfolio table**, one row per active project, worst first: status and its driver, dollars used and `remaining`, hours used and `hours_remaining`, `weekly_burn`, `hours_burn_wk`, `effective_rate`, `runout_date`, `hours_runout_date`, `runout_if_pending_approved`, `planned_end`.
2. **Project charts** (dollars and hours): cumulative actual, the forecast line to its runout date, the approved line, the pending-CO budget as a dashed line, and the planned end marker.
3. **Run record** (existing mechanism): run ID, criteria version, input fingerprints.

## Test cases (known answers)

Cases 1 to 6 share: `approved_budget` 100,000; `spent_to_date` 40,000; `planned_start` 2025-12-21; `as_of_date` 2026-03-01 (10 weeks elapsed); time spent in the last 28 days 20,000; expenses project-to-date 8,000, none in the last 28 days. Every `planned_end` below gives a duration long enough that `window_days` hits the 28-day cap.

So `time_burn_wk` = 5,000, `expense_burn_wk` = 800, `weekly_burn` = 5,800, `remaining` = 60,000, `runout_date` = 2026-05-12 (72 days).

| Case | `planned_end` | Other input | Expected |
|---|---|---|---|
| 1. Runs out early | 2026-06-30 | | `days_early` 49, `red_line_days` 19.1, Red, `variance_at_planned_end` -40,257.14 |
| 2. On track | 2026-05-01 | | `days_early` -11, Green, `variance_at_planned_end` 9,457.14 |
| 3. Slightly early | 2026-05-20 | | `days_early` 8, `red_line_days` 15, Yellow |
| 4. Pending CO | 2026-06-30 | `pending_co` 20,000 | `runout_date` still 2026-05-12 and Red; `runout_if_pending_approved` 2026-06-05 |
| 5. Over budget | 2026-06-30 | `spent_to_date` 105,000 | `remaining` -5,000, Red, reason "over budget" |
| 6. Travel burst | as case 1 | | `expense_burn_wk` is 800, not 0: a 14-day window with no trip would have forecast $0 of travel |

Cases 7 and 8 change the shared inputs:

| Case | Inputs | Expected |
|---|---|---|
| 7. Short project | `planned_start` 2026-03-02, `planned_end` 2026-03-30 (28 days), `approved_budget` 20,000, `as_of_date` 2026-03-16, `spent_to_date` 12,000, time in the last 7 days 5,000, expenses project-to-date 1,000 | `window_days` 7, `weekly_burn` 5,500, `runout_date` 2026-03-26, `days_early` 4, `red_line_days` 2.8, Red. A fixed 14-day Red line would have said Yellow |
| 8. CO project rolled up | Case 1's parent, plus a child CO project: `approved_budget` 10,000, no spend, `parent_project_id` = parent, `roll_up` yes | Family `approved_budget` 110,000, `remaining` 70,000, `runout_date` 2026-05-24, `days_early` 37, Red |

Cases 9 and 10 add hours to the shared inputs: `approved_hours` 500, `hours_used` 200.

| Case | `planned_end` | Hours in the last 28 days | Expected |
|---|---|---|---|
| 9. Hours run out first | 2026-06-30 | 120 | `hours_burn_wk` 30, `hours_runout_date` 2026-05-10 (2 days before the dollars), `hours_days_early` 51, Red; `effective_rate` 166.67 |
| 10. Hours drive the status | 2026-05-01 | 160 | `hours_burn_wk` 40, `hours_runout_date` 2026-04-22, `hours_days_early` 9, `red_line_days` 13.1. Hours Yellow, dollars Green (case 2), so the project is **Yellow, driven by hours**; `effective_rate` 125 |

## Definition of done

- One command produces the portfolio table and run record from sample data.
- All test cases above pass, plus a **parity test**: configured to mimic the spreadsheet (14-day window for both time and expenses, pending COs counted as budget), v1 reproduces the spreadsheet's runout date to the day for the same export.
- An Active Projects tab in the dashboard shows the table and chart.
- Real data stays in `data/real/` and never reaches GitHub.

## Open questions

1. Are 25% (window) and 10% (Red line) good starting percentages? Calibrate against closed projects in v3.
2. Do accepted change orders always appear inside the IES estimate, or sometimes only as separate rows?
3. Should non-billable hours on a project count against its hours budget? v1 assumes yes.
4. Which domain risks apply here: unposted costs (unapproved timesheets, vendor POs), expense posting lag, large material bills, money spent vs. work done, T&E not-to-exceed caps?
