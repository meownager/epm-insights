"""Active Projects: will the budget or hours last to the planned end date?

Second page of the dashboard (Streamlit lists files in pages/ in the sidebar).
Run the whole app with:  streamlit run dashboard.py

Logic lives in scripts/ (adapter, engine, store); this page only loads inputs,
shows upload checks, and draws the table and charts. Spec: docs/active-projects-spec.md
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from active_ies_adapter import UploadBlocked, time_entries_from_timesheet, transactions_from_ies
from completed_project_health import load_criteria
from portfolio_store import first_crossings, record_active_status
from run_active_audit import run

SAMPLE = ROOT / "data" / "sample"
STORE_DIR = ROOT / "data" / "real" / "portfolio_store"
STATUS_COLORS = {"Red": "#EF4444", "Yellow": "#F59E0B", "Green": "#22C55E", "Needs input": "#6B7588"}

st.set_page_config(page_title="EPM Insights: active projects", page_icon=":material/timer:", layout="wide")
st.title("Active projects")
st.caption("Will the approved budget or hours run out before the planned end date, and if so, when?")

criteria = load_criteria(ROOT / "config" / "audit_criteria.yaml")


# %% inputs %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

with st.sidebar:
    source = st.segmented_control("Data", ["Sample", "Upload exports"], default="Sample")
    if source == "Upload exports":
        up_projects = st.file_uploader("active_projects.csv (planned dates)", type="csv")
        up_sales = st.file_uploader("IES sales / transactions sheets, one per project",
                                    type=["xls", "xlsx", "csv"], accept_multiple_files=True)
        up_timesheet = st.file_uploader("Timesheet export", type="csv")
        save_history = st.checkbox("Record this run for first-crossing alerts", value=True,
                                   help=f"Saved locally to {STORE_DIR.relative_to(ROOT)}")

if source == "Sample":
    projects = pd.read_csv(SAMPLE / "active_projects.csv", dtype={"planned_end": str, "parent_project_id": str})
    transactions = pd.read_csv(SAMPLE / "active_transactions.csv")
    time_entries = pd.read_csv(SAMPLE / "active_time_entries.csv")
    save_history = False
else:
    if not (up_projects and up_sales):
        st.info("Upload active_projects.csv and at least one IES sales sheet to start. "
                "The timesheet is optional; without it, hours are not measured.")
        st.stop()
    projects = pd.read_csv(up_projects, dtype={"planned_end": str, "parent_project_id": str})
    parts, reports = [], []
    with tempfile.TemporaryDirectory() as tmp:
        # uploads are written to a temp folder only so the adapter can read them by path
        for f in up_sales:
            path = Path(tmp) / f.name
            path.write_bytes(f.getvalue())
            try:
                tx, rep = transactions_from_ies(path)
                parts.append(tx)
                reports.append(rep)
            except UploadBlocked as e:
                st.error(str(e), icon=":material/block:")
        time_entries = None
        if up_timesheet:
            path = Path(tmp) / up_timesheet.name
            path.write_bytes(up_timesheet.getvalue())
            try:
                time_entries, rep = time_entries_from_timesheet(path)
                reports.append(rep)
            except UploadBlocked as e:
                st.error(str(e), icon=":material/block:")
    if not parts:
        st.stop()
    transactions = pd.concat(parts, ignore_index=True)
    with st.container(border=True):
        st.markdown("**Upload checks**")
        for rep in reports:
            st.write(rep.summary)
            for w in rep.warnings:
                st.warning(w, icon=":material/warning:")

results = run(projects, transactions, time_entries, criteria)
if save_history:
    results = results.merge(first_crossings(record_active_status(STORE_DIR, results)),
                            on="project_id", how="left")


# %% summary + table %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

as_of = pd.Timestamp(results["as_of_date"].iloc[0])
counts = results["status"].value_counts()
with st.container(horizontal=True):
    for status in ["Red", "Yellow", "Green", "Needs input"]:
        st.metric(status, int(counts.get(status, 0)), border=True)
st.caption(f"As of {as_of:%Y-%m-%d} · criteria v{criteria.get('version', '?')} · worst first")

cols = ["project_id", "status", "driver", "reason", "warning", "remaining", "hours_remaining",
        "weekly_burn", "hours_burn_wk", "effective_rate", "runout_date", "hours_runout_date",
        "runout_if_pending_approved", "planned_end", "unapproved_hours", "rolled_up"]
cols += [c for c in ("first_yellow", "first_red") if c in results]
table = results[cols]

st.dataframe(
    table.style.map(lambda s: f"color: {STATUS_COLORS.get(s, 'inherit')}; font-weight: 600", subset=["status"]),
    hide_index=True,
    column_config={
        "project_id": "Project",
        "remaining": st.column_config.NumberColumn("$ left", format="dollar"),
        "hours_remaining": st.column_config.NumberColumn("Hours left", format="%.0f"),
        "weekly_burn": st.column_config.NumberColumn("$ / week", format="dollar"),
        "hours_burn_wk": st.column_config.NumberColumn("Hours / week", format="%.1f"),
        "effective_rate": st.column_config.NumberColumn("$ / hour", format="dollar"),
        "runout_date": st.column_config.DateColumn("$ run out"),
        "hours_runout_date": st.column_config.DateColumn("Hours run out"),
        "runout_if_pending_approved": st.column_config.DateColumn("$ run out if pending COs approved"),
        "planned_end": st.column_config.DateColumn("Planned end"),
        "unapproved_hours": st.column_config.NumberColumn("Unapproved hrs (counted)", format="%.1f"),
        "rolled_up": "Rolled-up COs",
    },
)
st.download_button("Download table (CSV)", results.to_csv(index=False), "active_portfolio.csv",
                   icon=":material/download:")


# %% project chart %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

st.subheader("Project forecast")
pick = st.selectbox("Project", results["project_id"])
row = results.set_index("project_id").loc[pick]
members = [pick] + [m.strip() for m in str(row["rolled_up"]).split(",") if m.strip()]


def _forecast_chart(actual: pd.Series, approved, pending, burn_wk, runout, unit: str) -> go.Figure:
    """Cumulative actual, forecast to runout, approved line, pending-CO line, planned end."""
    fig = go.Figure()
    fig.add_scatter(x=actual.index, y=actual.values, name="Actual", line=dict(color="#2962FF", width=3))
    used = actual.iloc[-1] if len(actual) else 0.0
    if burn_wk and burn_wk > 0:
        end = runout if pd.notna(runout) else row["planned_end"]
        weeks = max((pd.Timestamp(end) - as_of).days, 0) / 7
        fig.add_scatter(x=[as_of, end], y=[used, used + burn_wk * weeks], name="Forecast",
                        line=dict(color="#2962FF", dash="dot"))
    fig.add_hline(y=approved, line_color="#166534", annotation_text=f"Approved {unit}")
    if pending and pending > 0:
        fig.add_hline(y=approved + pending, line_dash="dash", line_color="#6B7588",
                      annotation_text="If pending COs approved")
    if pd.notna(row["planned_end"]):
        fig.add_vline(x=pd.Timestamp(row["planned_end"]), line_color="#EF4444", line_dash="dash")
        fig.add_annotation(x=pd.Timestamp(row["planned_end"]), y=0.02, yref="paper", text="Planned end",
                           showarrow=False, xanchor="right", yanchor="bottom")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h"))
    return fig


if row["status"] == "Needs input":
    st.info(f"{pick}: {row['reason']}. Add the missing values to active_projects.csv.")
else:
    tx = transactions[transactions["project_id"].isin(members)].copy()
    tx["date"] = pd.to_datetime(tx["date"])
    spend = tx[tx["kind"].isin(["time", "expense"]) & (tx["date"] <= as_of)]
    spent = spend.groupby("date")["amount"].sum().sort_index().cumsum()
    dollars, hours = st.tabs(["Dollars", "Hours"])
    with dollars:
        st.plotly_chart(_forecast_chart(spent, row["approved_budget"], row["pending_co"],
                                        row["weekly_burn"], row["runout_date"], "$"))
    with hours:
        if pd.isna(row["hours_used"]) or time_entries is None:
            st.info("Hours not measured: no approved hours budget or no timesheet.")
        else:
            te = time_entries[time_entries["project_id"].isin(members)].copy()
            te["date"] = pd.to_datetime(te["date"])
            if "approval" in te:
                te = te[te["approval"] != "rejected"]
            used = te[te["date"] <= as_of].groupby("date")["hours"].sum().sort_index().cumsum()
            st.plotly_chart(_forecast_chart(used, row["approved_hours"], 0,
                                            row["hours_burn_wk"], row["hours_runout_date"], "hours"))
