"""Active project health: live burn rate for projects that are still running.

Answers, for every active project: "Will the approved budget or the approved
hours run out before the planned end date, and if so, when?"

Spec: docs/active-projects-spec.md. Settings come from the `active_projects`
section of config/audit_criteria.yaml (the Audit Criteria Register); no
threshold is hardcoded here.

Inputs use a standard schema (adapters convert company exports into it):
    projects      one row per project: project_id, billing_type, planned_start,
                  planned_end, and optionally parent_project_id, roll_up
    transactions  project_id, date, kind (budget | change_order | time | expense),
                  amount, approved, and optionally hours (budgeted hours on
                  budget / change_order rows)
    time_entries  project_id, date, hours, and optionally approval
                  (approved | unapproved | rejected); may be None

All processing is local. Real data never leaves the machine.
"""

from __future__ import annotations

import math
from datetime import timedelta

import pandas as pd

STATUS_RANK = {"Green": 0, "Yellow": 1, "Red": 2, "Needs input": 3}


# %% settings %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def load_settings(criteria: dict) -> dict:
    """Pull the active_projects section out of the loaded criteria register."""
    section = criteria.get("active_projects")
    if not section:
        raise ValueError("criteria register has no 'active_projects' section")
    return section


def window_days(planned_duration: int, settings: dict) -> int:
    """Recent-spend window: a share of planned duration, in whole days, clamped."""
    w = settings["window"]
    days = math.floor(w["pct"] * planned_duration + 0.5)
    return int(min(max(days, w["min_days"]), w["max_days"]))


def red_line_days(planned_duration: int, settings: dict) -> float:
    """How many days early (before planned_end) a runout must be to count as Red."""
    r = settings["red_line"]
    return max(r["min_days"], r["pct"] * planned_duration)


# %% core math %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def runout_date(as_of: pd.Timestamp, remaining: float, burn_per_week: float):
    """Date the remaining amount is used up at the current weekly burn.

    Rounded down to whole days so the warning comes earlier, not later.
    Returns None when there is nothing left or nothing is being burned.
    """
    if remaining <= 0 or burn_per_week <= 0:
        return None
    return as_of + timedelta(days=math.floor(remaining / burn_per_week * 7))


def classify(remaining: float, burn_per_week: float, runout, planned_end,
             as_of: pd.Timestamp, red_line: float) -> tuple[str, str]:
    """Green / Yellow / Red for one dimension (dollars or hours), with a reason."""
    if remaining <= 0:
        return "Red", "over budget"
    if planned_end < as_of:
        return "Red", "past planned end"
    if burn_per_week <= 0:
        return "Green", "no recent spend"
    days_early = (planned_end - runout).days
    if days_early > red_line:
        return "Red", f"runs out {days_early} days before planned end"
    if days_early > 0:
        return "Yellow", f"runs out {days_early} days before planned end"
    return "Green", "lasts to planned end"


def _between(df: pd.DataFrame, start_exclusive, end_inclusive) -> pd.DataFrame:
    return df[(df["date"] > start_exclusive) & (df["date"] <= end_inclusive)]


# %% one project %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def assess_project(project: dict, transactions: pd.DataFrame,
                   time_entries: pd.DataFrame | None, settings: dict,
                   as_of) -> dict:
    """All spec outputs for one project (or one rolled-up family).

    transactions and time_entries must already be filtered to this project.
    """
    as_of = pd.Timestamp(as_of)
    out = {"project_id": project["project_id"],
           "billing_type": project.get("billing_type", ""),
           "as_of_date": as_of}

    tx = transactions.copy()
    tx["date"] = pd.to_datetime(tx["date"])
    tx = tx[tx["date"] <= as_of]
    approved = tx["approved"].fillna(False).astype(bool)
    is_baseline = tx["kind"].isin(["budget", "change_order"])

    # budget and hours baseline: approved lines only; unapproved lines are "pending"
    out["approved_budget"] = float(tx.loc[is_baseline & approved, "amount"].sum())
    out["pending_co"] = float(tx.loc[is_baseline & ~approved, "amount"].sum())
    hours_col = tx["hours"] if "hours" in tx else pd.Series(0.0, index=tx.index)
    out["approved_hours"] = float(hours_col[is_baseline & approved].fillna(0).sum())

    planned_start = pd.to_datetime(project.get("planned_start"), errors="coerce")
    planned_end = pd.to_datetime(project.get("planned_end"), errors="coerce")
    out["planned_end"] = planned_end

    if out["approved_budget"] <= 0 or pd.isna(planned_end) or pd.isna(planned_start):
        out.update(status="Needs input", driver="budget",
                   reason="missing approved budget or planned dates")
        return out

    duration = (planned_end - planned_start).days
    win = window_days(duration, settings)
    red = red_line_days(duration, settings)
    elapsed = max((as_of - planned_start).days, 1)
    win_eff = min(win, elapsed)  # less history than the window: use what exists
    win_start = as_of - timedelta(days=win_eff)
    out.update(planned_duration=duration, window_days=win, red_line_days=red)

    # dollars
    time_tx = tx[tx["kind"] == "time"]
    exp_tx = tx[tx["kind"] == "expense"]
    time_in_window = float(_between(time_tx, win_start, as_of)["amount"].sum())
    out["spent_to_date"] = float(time_tx["amount"].sum() + exp_tx["amount"].sum())
    out["remaining"] = out["approved_budget"] - out["spent_to_date"]
    out["time_burn_wk"] = time_in_window / (win_eff / 7)
    # expenses averaged over the whole project: travel comes in bursts
    out["expense_burn_wk"] = float(exp_tx["amount"].sum()) / max(elapsed / 7, 1)
    out["weekly_burn"] = out["time_burn_wk"] + out["expense_burn_wk"]
    out["runout_date"] = runout_date(as_of, out["remaining"], out["weekly_burn"])
    out["days_early"] = (planned_end - out["runout_date"]).days if out["runout_date"] else None
    weeks_to_end = max((planned_end - as_of).days, 0) / 7
    out["spend_at_planned_end"] = out["spent_to_date"] + out["weekly_burn"] * weeks_to_end
    out["variance_at_planned_end"] = out["approved_budget"] - out["spend_at_planned_end"]
    out["runout_if_pending_approved"] = (
        runout_date(as_of, out["remaining"] + out["pending_co"], out["weekly_burn"])
        if out["pending_co"] > 0 else None)
    out["burn_index"] = (out["spent_to_date"] / out["approved_budget"]) / (elapsed / duration) \
        if duration > 0 else None
    budget_status, budget_reason = classify(
        out["remaining"], out["weekly_burn"], out["runout_date"], planned_end, as_of, red)

    # hours
    hours_status, hours_reason = "Not measured", "no approved hours"
    out.update(hours_used=None, hours_remaining=None, hours_burn_wk=None,
               hours_runout_date=None, hours_days_early=None,
               unapproved_hours=None, effective_rate=None)
    if time_entries is not None and not time_entries.empty and out["approved_hours"] > 0:
        te = time_entries.copy()
        te["date"] = pd.to_datetime(te["date"])
        te = te[te["date"] <= as_of]
        out["unapproved_hours"] = 0.0
        if "approval" in te:
            te = te[te["approval"] != "rejected"]  # rejected hours never count
            # unapproved hours DO count (earlier warning); report how many
            out["unapproved_hours"] = float(te.loc[te["approval"] == "unapproved", "hours"].sum())
        hours_in_window = float(_between(te, win_start, as_of)["hours"].sum())
        out["hours_used"] = float(te["hours"].sum())
        out["hours_remaining"] = out["approved_hours"] - out["hours_used"]
        out["hours_burn_wk"] = hours_in_window / (win_eff / 7)
        out["hours_runout_date"] = runout_date(as_of, out["hours_remaining"], out["hours_burn_wk"])
        out["hours_days_early"] = (planned_end - out["hours_runout_date"]).days \
            if out["hours_runout_date"] else None
        out["effective_rate"] = time_in_window / hours_in_window if hours_in_window > 0 else None
        hours_status, hours_reason = classify(
            out["hours_remaining"], out["hours_burn_wk"], out["hours_runout_date"],
            planned_end, as_of, red)

    out.update(budget_status=budget_status, hours_status=hours_status)

    # overall status = the worse of the two; on a tie, whichever runs out first
    hours_worse = STATUS_RANK.get(hours_status, -1) > STATUS_RANK[budget_status]
    tie = hours_status == budget_status and budget_status != "Green"
    hours_first = (out["hours_runout_date"] is not None and out["runout_date"] is not None
                   and out["hours_runout_date"] < out["runout_date"])
    if hours_worse or (tie and hours_first):
        out.update(status=hours_status, driver="hours", reason=hours_reason)
    else:
        out.update(status=budget_status, driver="budget", reason=budget_reason)
    if hours_status == "Not measured":
        out["reason"] += "; hours not measured"
    return out


# %% portfolio %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

def _families(projects: pd.DataFrame) -> dict[str, str]:
    """Map each project_id to the id it is assessed under (its parent if rolled up)."""
    owner = {}
    for _, p in projects.iterrows():
        pid = p["project_id"]
        parent = p.get("parent_project_id")
        rolls = str(p.get("roll_up", "no")).strip().lower() in ("yes", "true", "1")
        owner[pid] = parent if (rolls and isinstance(parent, str) and parent) else pid
    return owner


def assess_portfolio(projects: pd.DataFrame, transactions: pd.DataFrame,
                     time_entries: pd.DataFrame | None, settings: dict,
                     as_of=None) -> pd.DataFrame:
    """Assess every active project. Rolled-up CO projects merge into their parent.

    as_of defaults to the latest date in the inputs, the same date for every
    project, so the whole portfolio is judged as of one moment.
    """
    if as_of is None:
        dates = [pd.to_datetime(transactions["date"]).max()]
        if time_entries is not None and not time_entries.empty:
            dates.append(pd.to_datetime(time_entries["date"]).max())
        as_of = max(dates)

    owner = _families(projects)
    tx = transactions.assign(project_id=transactions["project_id"].map(owner).fillna(transactions["project_id"]))
    te = None
    if time_entries is not None:
        te = time_entries.assign(project_id=time_entries["project_id"].map(owner).fillna(time_entries["project_id"]))

    rows = []
    for family_id in dict.fromkeys(owner.values()):
        members = projects[projects["project_id"].map(owner) == family_id]
        head = projects[projects["project_id"] == family_id]
        info = (head.iloc[0] if not head.empty else members.iloc[0]).to_dict()
        # a family runs from its earliest planned start to its latest planned end
        info["planned_start"] = pd.to_datetime(members["planned_start"], errors="coerce").min()
        info["planned_end"] = pd.to_datetime(members["planned_end"], errors="coerce").max()
        result = assess_project(
            info, tx[tx["project_id"] == family_id],
            te[te["project_id"] == family_id] if te is not None else None,
            settings, as_of)
        result["parent_project_id"] = info.get("parent_project_id") if family_id == info["project_id"] else None
        result["rolled_up"] = ", ".join(m for m in members["project_id"] if m != family_id)
        rows.append(result)

    df = pd.DataFrame(rows)
    df["_rank"] = df["status"].map(STATUS_RANK)
    df = df.sort_values(["_rank", "days_early"], ascending=[False, False], na_position="last")
    return df.drop(columns="_rank").reset_index(drop=True)
