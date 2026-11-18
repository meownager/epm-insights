"""Local portfolio store — accumulates audited projects across dashboard sessions.

Each time a batch of projects is converted and audited, the results are
upserted into this store (by project_id — re-uploading a project replaces its
old entry rather than duplicating it). The dashboard loads the full store on
startup, so previously audited projects stay visible without re-uploading,
and offers a way to remove specific projects from it.

Location: data/real/portfolio_store/ (local only — covered by the existing
.gitignore data guardrails, never committed).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

STORE_FILES = {
    "metrics": "metrics.csv",
    "financials": "financials.csv",
    "ledger": "ledger.csv",
}


def _empty(name: str) -> pd.DataFrame:
    if name == "ledger":
        return pd.DataFrame(columns=["project_id", "date", "cumulative_revenue", "cumulative_hours"])
    return pd.DataFrame(columns=["project_id"])


def load_store(store_dir: Path) -> dict[str, pd.DataFrame]:
    """Load whatever is currently in the store. Missing files → empty frames."""
    store_dir = Path(store_dir)
    out = {}
    for key, filename in STORE_FILES.items():
        path = store_dir / filename
        out[key] = pd.read_csv(path) if path.exists() else _empty(key)
    return out

### this needs to be changed accroding to the discussion on 10/06
def _upsert_by_project_id(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if new is None or new.empty:
        return existing
    if existing.empty:
        return new.copy()
    incoming_ids = set(new["project_id"].unique())
    kept = existing[~existing["project_id"].isin(incoming_ids)]
    return pd.concat([kept, new], ignore_index=True)


def upsert(
    store_dir: Path,
    metrics: pd.DataFrame,
    financials: pd.DataFrame | None = None,
    ledger: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Merge new audit results into the store, replacing any prior entry for
    the same project_id, and persist to disk. Returns the full updated store.
    """
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    current = load_store(store_dir)

    updated = {
        "metrics": _upsert_by_project_id(current["metrics"], metrics),
        "financials": _upsert_by_project_id(current["financials"], financials),
        "ledger": _upsert_by_project_id(current["ledger"], ledger),
    }

    for key, filename in STORE_FILES.items():
        updated[key].to_csv(store_dir / filename, index=False)

    return updated


# %% active-project status history %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

STATUS_HISTORY_FILE = "active_status_history.csv"
HISTORY_COLUMNS = ["project_id", "as_of_date", "status", "driver"]


def record_active_status(store_dir: Path, results: pd.DataFrame) -> pd.DataFrame:
    """Append this run's status per active project to the history file.

    One row per (project_id, as_of_date): rerunning the same export replaces
    that day's row instead of duplicating it. Returns the full history.
    """
    store_dir = Path(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / STATUS_HISTORY_FILE
    history = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=HISTORY_COLUMNS)

    new = results[HISTORY_COLUMNS].copy()
    new["as_of_date"] = pd.to_datetime(new["as_of_date"]).dt.strftime("%Y-%m-%d")
    keys = set(zip(new["project_id"], new["as_of_date"]))
    kept = history[[k not in keys for k in zip(history["project_id"], history["as_of_date"])]]
    history = pd.concat([kept, new], ignore_index=True).sort_values(["project_id", "as_of_date"])
    history.to_csv(path, index=False)
    return history.reset_index(drop=True)


def first_crossings(history: pd.DataFrame) -> pd.DataFrame:
    """Date each project FIRST turned Yellow (or worse) and first turned Red.

    Same idea as burn_timeline.first_crossing_dates, but over the stored
    weekly runs of active projects. Blank when it never happened.
    """
    rows = []
    for pid, grp in history.sort_values("as_of_date").groupby("project_id"):
        yellow = grp.loc[grp["status"].isin(["Yellow", "Red"]), "as_of_date"]
        red = grp.loc[grp["status"] == "Red", "as_of_date"]
        rows.append({"project_id": pid,
                     "first_yellow": yellow.iloc[0] if not yellow.empty else None,
                     "first_red": red.iloc[0] if not red.empty else None})
    return pd.DataFrame(rows, columns=["project_id", "first_yellow", "first_red"])


def delete_projects(store_dir: Path, project_ids: list[str]) -> dict[str, pd.DataFrame]:
    """Remove the given project_ids from every part of the store and persist."""
    store_dir = Path(store_dir)
    current = load_store(store_dir)
    to_remove = set(project_ids)

    updated = {}
    for key, df in current.items():
        updated[key] = df[~df["project_id"].isin(to_remove)] if not df.empty else df

    store_dir.mkdir(parents=True, exist_ok=True)
    for key, filename in STORE_FILES.items():
        updated[key].to_csv(store_dir / filename, index=False)

    return updated
