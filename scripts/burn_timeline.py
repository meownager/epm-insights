"""Burn timeline — classifies a project's cumulative spend/hours over time
against a straight-line pace to its proposed total, using the same
Green/Yellow/Red thresholds as the completed-project audit (read live from
the criteria register, never hardcoded).

This answers "when did we cross into Yellow/Red," not just "did we end up
Yellow/Red" — the same project can look fine for months and only tip over
near the end; this is what makes that visible.

Pace basis: since proposed (baseline) delivery dates don't exist in the
source data (see convert_ies.py's documented data gap), the pace line runs
across the project's own ACTUAL start→end window. This is clearly labeled
in the dashboard as an actual-duration pace, not a promised-schedule pace —
it answers "were we spending faster than a steady, even burn would predict,"
which is still a meaningful signal, just not a schedule audit.
"""

from __future__ import annotations

import pandas as pd


def compute_burn_series(
    ledger: pd.DataFrame,
    proposed_value: float,
    value_col: str,
    green_pct: float,
    yellow_pct: float,
) -> pd.DataFrame:
    """Add expected_pace / dev_pct / zone columns to a single project's ledger.

    ledger: rows with at least 'date' and value_col (e.g. 'cumulative_revenue'
    or 'cumulative_hours'), sorted or unsorted, for ONE project.
    proposed_value: the proposed budget or proposed hours to pace against.
    """
    df = ledger.sort_values("date").reset_index(drop=True).copy()
    if df.empty or not proposed_value or pd.isna(proposed_value) or proposed_value <= 0:
        df["expected_pace"] = pd.NA
        df["dev_pct"] = pd.NA
        df["zone"] = "Unavailable"
        return df

    df["date"] = pd.to_datetime(df["date"])
    start, end = df["date"].iloc[0], df["date"].iloc[-1]
    total_days = (end - start).days

    if total_days <= 0:
        # single-day or same-day project — pace is just "the full amount is due immediately"
        df["expected_pace"] = float(proposed_value)
    else:
        days_elapsed = (df["date"] - start).dt.days
        df["expected_pace"] = proposed_value * (days_elapsed / total_days)

    df["dev_pct"] = (df[value_col] - df["expected_pace"]) / proposed_value

    def _zone(dev):
        if pd.isna(dev):
            return "Unavailable"
        d = abs(dev)
        if d <= green_pct:
            return "Green"
        if d <= yellow_pct:
            return "Yellow"
        return "Red"

    df["zone"] = df["dev_pct"].apply(_zone)
    return df


def first_crossing_dates(burn_series: pd.DataFrame) -> dict[str, pd.Timestamp | None]:
    """Return the first date the series entered Yellow and the first date it
    entered Red (None if it never did). Once Red, a point can't count as a
    fresh Yellow crossing again.
    """
    result = {"first_yellow": None, "first_red": None}
    for _, row in burn_series.iterrows():
        if row["zone"] == "Yellow" and result["first_yellow"] is None:
            result["first_yellow"] = row["date"]
        if row["zone"] == "Red" and result["first_red"] is None:
            result["first_red"] = row["date"]
    return result
