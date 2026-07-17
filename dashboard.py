#!/usr/bin/env python3
"""EPM Insights — Completed Project Health Dashboard.

Run with:
    streamlit run dashboard.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from burn_timeline import compute_burn_series, first_crossing_dates
from completed_project_health import compute_metrics, get_billing_thresholds, load_criteria, write_run_record
from convert_ies import convert as convert_ies_exports
from generate_html_report import build_report
from insights import analyse_patterns, build_notes_index, search_notes
from portfolio_store import delete_projects as store_delete
from portfolio_store import load_store, upsert as store_upsert
from quality_scoring import load_rubric, score_portfolio

# ── constants ───────────────────────────────────────────────────────────────

DEFAULT_PROPOSAL = str(Path(__file__).parent / "data/sample/proposal_projects.csv")
DEFAULT_ACTUAL   = str(Path(__file__).parent / "data/sample/actual_projects.csv")
DEFAULT_CRITERIA = str(Path(__file__).parent / "config/audit_criteria.yaml")
PORTFOLIO_STORE_DIR = Path(__file__).parent / "data/real/portfolio_store"

HEALTH_ORDER  = ["Red", "Yellow", "Green"]
HEALTH_COLORS = {"Red": "#EF4444", "Yellow": "#F59E0B", "Green": "#22C55E"}
HEALTH_BG     = {"Red": "#FEE2E2", "Yellow": "#FEF3C7", "Green": "#DCFCE7"}
HEALTH_TEXT   = {"Red": "#991B1B", "Yellow": "#78350F", "Green": "#166534"}


def _run_ies_conversion(estimate_transaction_files, timesheet_file, work_dir: Path) -> dict:
    """Save uploaded IES files to disk and run the converter. Returns dict of DataFrames."""
    in_dir = work_dir / "ies_uploads"
    out_dir = work_dir / "ies_converted"
    in_dir.mkdir(parents=True, exist_ok=True)

    for f in estimate_transaction_files:
        (in_dir / f.name).write_bytes(f.getvalue())

    timesheet_path = None
    if timesheet_file is not None:
        timesheet_path = in_dir / timesheet_file.name
        timesheet_path.write_bytes(timesheet_file.getvalue())

    log = convert_ies_exports(in_dir, out_dir, timesheet_path)
    return {
        "log": log,
        "proposal": pd.read_csv(out_dir / "proposal_projects.csv"),
        "actual": pd.read_csv(out_dir / "actual_projects.csv"),
        "financials": pd.read_csv(out_dir / "project_financials.csv"),
        "ledger": pd.read_csv(out_dir / "project_ledger.csv"),
    }

def _load_full_portfolio() -> None:
    """Pull everything currently in the local portfolio store into session
    state, so previously audited projects stay visible without re-uploading.
    """
    store = load_store(PORTFOLIO_STORE_DIR)
    if store["metrics"].empty:
        return
    criteria = load_criteria(Path(DEFAULT_CRITERIA))
    st.session_state.metrics = store["metrics"]
    st.session_state.criteria = criteria
    st.session_state.ies_financials = store["financials"] if not store["financials"].empty else None
    st.session_state.ies_ledger = store["ledger"] if not store["ledger"].empty else None
    st.session_state.no_schedule_baseline = True
    st.session_state.meta = {
        "run_id": "portfolio", "timestamp": "", "criteria_version": criteria.get("version", "—"),
        "proposal_fingerprint": "—", "actual_fingerprint": "—",
    }
    st.session_state.scorecard = None
    if st.session_state.ies_financials is not None:
        try:
            rubric = load_rubric()
            st.session_state.scorecard = score_portfolio(
                store["metrics"], criteria, rubric, financials=st.session_state.ies_financials, scores=None,
            )
        except Exception:
            pass
    pms = sorted(store["metrics"]["project_manager"].dropna().unique().tolist())
    st.session_state["pm_options"] = pms


# ── page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="EPM Insights — Project Health",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #F4F6FA; }
  [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E2E5EA; }
  h1 { font-size: 1.35rem !important; font-weight: 700 !important; letter-spacing: -0.3px !important; }
  .metric-card {
    background: #fff; border: 1px solid #E2E5EA; border-radius: 8px;
    padding: 16px 20px; border-top: 3px solid transparent;
  }
  .metric-card.red    { border-top-color: #EF4444; }
  .metric-card.yellow { border-top-color: #F59E0B; }
  .metric-card.green  { border-top-color: #22C55E; }
  .metric-card.total  { border-top-color: #2962FF; }
  .metric-count { font-size: 2rem; font-weight: 700; line-height: 1; }
  .metric-label { font-size: 0.78rem; font-weight: 600; color: #6B7588; margin-top: 4px; }
  .meta-strip {
    background: #fff; border: 1px solid #E2E5EA; border-radius: 8px;
    padding: 10px 16px; font-size: 0.78rem; color: #6B7588;
    display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 16px;
  }
  .stDataFrame { border-radius: 8px; overflow: hidden; }
  div[data-testid="stMetric"] label { font-size: 0.75rem !important; }
</style>
""", unsafe_allow_html=True)


# ── sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### EPM Insights")
    st.markdown("Completed project health audit")
    st.divider()

    st.markdown("**1. Upload project data**")
    st.caption(
        "Select every IES Estimate + Transactions file for the projects "
        "you want to audit, plus the timesheet export. No manual data entry."
    )
    uploaded_ies_files = st.file_uploader(
        "IES Estimate + Transactions files",
        type=["xls", "xlsx", "csv"],
        accept_multiple_files=True,
        help="Select all <projectnumber>_Estimate and <projectnumber>_Transactions "
             "files at once (Ctrl/Cmd-click to multi-select).",
    )
    uploaded_timesheet = st.file_uploader(
        "Timesheet export (company-wide, optional)",
        type=["csv"],
        help="Powers actual hours and actual dates for T&E projects, and margin "
             "analysis for fixed-fee projects. Skip it and the audit still runs "
             "on invoice data alone.",
    )
    convert_clicked = st.button(
        "🔄  Convert & Run Audit", type="primary", use_container_width=True,
        disabled=not uploaded_ies_files,
    )

    _store_preview = load_store(PORTFOLIO_STORE_DIR)
    if not _store_preview["metrics"].empty:
        with st.expander(f"Manage saved portfolio ({len(_store_preview['metrics'])} projects)"):
            st.caption("Projects stay here across sessions until removed.")
            to_remove = st.multiselect(
                "Remove project(s)",
                sorted(_store_preview["metrics"]["project_id"].unique().tolist()),
            )
            if st.button("🗑️  Remove selected", disabled=not to_remove, use_container_width=True):
                store_delete(PORTFOLIO_STORE_DIR, to_remove)
                _load_full_portfolio()
                st.rerun()

    with st.expander("Advanced: use already-converted CSVs instead"):
        proposal_path = st.text_input("Proposal CSV", value=DEFAULT_PROPOSAL)
        actual_path   = st.text_input("Actual CSV",   value=DEFAULT_ACTUAL)
        criteria_path = st.text_input("Criteria YAML", value=DEFAULT_CRITERIA)
        financials_path = st.text_input(
            "Financials CSV (optional)", value="",
            help="data/real/audit_inputs/project_financials.csv",
        )
        scores_path = st.text_input(
            "Quality scores CSV (optional)", value="",
            help="Columns: project_id, category, score, comments",
        )
        run_clicked = st.button("▶  Run Audit from CSVs", use_container_width=True)

    st.divider()
    st.markdown("**Filters**")
    filter_health  = st.multiselect("Health Status", HEALTH_ORDER, default=HEALTH_ORDER)
    filter_billing = st.multiselect("Billing Type",  ["fixed_fee", "t_and_e"],
                                    default=["fixed_fee", "t_and_e"])
    filter_pm      = st.multiselect(
        "Project Manager", st.session_state.get("pm_options", []), key="pm_filter",
    )

    st.divider()
    st.caption("All processing is local.\nNo data leaves your machine.")


# ── session state ────────────────────────────────────────────────────────────

if "metrics" not in st.session_state:
    st.session_state.metrics   = None
    st.session_state.meta      = {}
    st.session_state.criteria  = {}
    st.session_state.scorecard = None
    st.session_state.ies_financials = None
    st.session_state.ies_ledger = None
    st.session_state.no_schedule_baseline = False
    _load_full_portfolio()


# ── convert uploaded IES files + run audit ──────────────────────────────────

if convert_clicked:
    with st.spinner("Converting IES files and running audit…"):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            try:
                converted = _run_ies_conversion(uploaded_ies_files, uploaded_timesheet, work_dir)
            except Exception as e:
                st.error(f"Conversion failed: {e}")
                converted = None

            if converted is not None:
                skipped = converted["log"][converted["log"]["status"] == "SKIPPED"]
                if not skipped.empty:
                    st.warning(
                        f"{len(skipped)} project(s) skipped — missing an Estimate or "
                        f"Transactions file: {', '.join(skipped['project_number'].astype(str))}"
                    )

                criteria = load_criteria(Path(DEFAULT_CRITERIA))
                cp = criteria["completed_projects"]
                eligible = set(cp.get("eligible_statuses", ["completed", "closed"]))
                proposal, actual, financials = (
                    converted["proposal"], converted["actual"], converted["financials"],
                )

                if proposal.empty:
                    st.error("No projects converted successfully — check the uploaded files.")
                else:
                    metrics = compute_metrics(proposal, actual, criteria, eligible)
                    ledger = converted["ledger"]

                    proposal_tmp = work_dir / "proposal_projects.csv"
                    actual_tmp = work_dir / "actual_projects.csv"
                    proposal.to_csv(proposal_tmp, index=False)
                    actual.to_csv(actual_tmp, index=False)
                    run_out = write_run_record(
                        output_dir=work_dir,
                        criteria=criteria,
                        criteria_path=Path(DEFAULT_CRITERIA),
                        proposal_path=proposal_tmp,
                        actual_path=actual_tmp,
                        metrics=metrics,
                    )
                    meta = json.loads(run_out.read_text())

                    # persist this batch into the local portfolio store, replacing
                    # any prior entry for the same project_id, then reload the
                    # FULL accumulated portfolio (not just this batch) so
                    # previously audited projects stay visible.
                    store_upsert(PORTFOLIO_STORE_DIR, metrics, financials, ledger)
                    _load_full_portfolio()
                    st.session_state.meta = meta
                    st.success(f"{len(metrics)} project(s) added to your portfolio.")
                    st.rerun()


# ── run audit (advanced: pre-converted CSVs) ────────────────────────────────

if run_clicked:
    errors = []
    if not Path(proposal_path).exists():
        errors.append(f"Proposal file not found: `{proposal_path}`")
    if not Path(actual_path).exists():
        errors.append(f"Actual file not found: `{actual_path}`")
    if not Path(criteria_path).exists():
        errors.append(f"Criteria file not found: `{criteria_path}`")

    if errors:
        for e in errors:
            st.error(e)
    else:
        with st.spinner("Running audit…"):
            criteria = load_criteria(Path(criteria_path))
            proposal = pd.read_csv(proposal_path)
            actual   = pd.read_csv(actual_path)
            cp       = criteria["completed_projects"]
            eligible = set(cp.get("eligible_statuses", ["completed", "closed"]))
            metrics  = compute_metrics(proposal, actual, criteria, eligible)

            with tempfile.TemporaryDirectory() as tmp:
                run_out = write_run_record(
                    output_dir=Path(tmp),
                    criteria=criteria,
                    criteria_path=Path(criteria_path),
                    proposal_path=Path(proposal_path),
                    actual_path=Path(actual_path),
                    metrics=metrics,
                )
                meta = json.loads(run_out.read_text())

        st.session_state.metrics  = metrics
        st.session_state.meta     = meta
        st.session_state.criteria = criteria
        st.session_state.ies_financials = None
        st.session_state.ies_ledger = None
        st.session_state.no_schedule_baseline = False

        # optional quality/financial scoring layer
        st.session_state.scorecard = None
        try:
            fin_df = pd.read_csv(financials_path) if financials_path.strip() and Path(financials_path).exists() else None
            sc_df = pd.read_csv(scores_path) if scores_path.strip() and Path(scores_path).exists() else None
            if fin_df is not None or sc_df is not None:
                rubric = load_rubric()
                st.session_state.scorecard = score_portfolio(
                    metrics, criteria, rubric, financials=fin_df, scores=sc_df,
                )
        except Exception as e:
            st.warning(f"Quality/financial scoring skipped: {e}")

        # refresh PM filter options
        pms = sorted(metrics["project_manager"].dropna().unique().tolist())
        st.session_state["pm_options"] = pms
        st.rerun()


# ── empty state ──────────────────────────────────────────────────────────────

if st.session_state.metrics is None:
    st.markdown("# Completed Project Health")
    st.markdown(
        "Enter file paths in the sidebar and click **Run Audit** to generate results."
    )
    st.info(
        "Default paths point to the synthetic sample data included in the repository. "
        "To audit real projects, point the inputs at your local data files — "
        "they will never be committed or transmitted.",
        icon="ℹ️",
    )
    st.stop()


# ── apply filters ────────────────────────────────────────────────────────────

df = st.session_state.metrics.copy()
meta     = st.session_state.meta
criteria = st.session_state.criteria

# populate PM filter on first load
pm_options = sorted(df["project_manager"].dropna().unique().tolist())
selected_pms = st.session_state.get("pm_filter") or pm_options

df = df[
    df["health_status"].isin(filter_health) &
    df["billing_type"].isin(filter_billing) &
    df["project_manager"].isin(selected_pms if selected_pms else pm_options)
]


# ── header ───────────────────────────────────────────────────────────────────

col_title, col_dl = st.columns([4, 1])
with col_title:
    st.markdown("# Completed Project Health")

with col_dl:
    html_bytes = build_report(st.session_state.metrics, meta).encode("utf-8")
    st.download_button(
        "⬇ Download Report",
        data=html_bytes,
        file_name="audit_report.html",
        mime="text/html",
        use_container_width=True,
    )

# meta strip
run_id   = meta.get("run_id", "—")[:8]
ts       = meta.get("timestamp", "—")[:19].replace("T", " ")
ver      = meta.get("criteria_version", "—")
prop_fp  = meta.get("proposal_fingerprint", "—")[:12]
act_fp   = meta.get("actual_fingerprint",  "—")[:12]

st.markdown(
    f'<div class="meta-strip">'
    f'<span>Run <strong>{run_id}…</strong></span>'
    f'<span>{ts} UTC</span>'
    f'<span>Criteria <strong>v{ver}</strong></span>'
    f'<span>Proposal SHA-256 <strong>{prop_fp}…</strong></span>'
    f'<span>Actual SHA-256 <strong>{act_fp}…</strong></span>'
    f'</div>',
    unsafe_allow_html=True,
)

if st.session_state.get("no_schedule_baseline"):
    st.info(
        "**Schedule not measured for these projects.** IES exports contain actual "
        "work and billing dates, but no committed/proposed delivery date — so schedule "
        "deviation cannot be computed. Health status below reflects budget and hours "
        "only for projects converted this way. Client, PM, and project name were also "
        "not found in the IES data and are shown blank.",
        icon="ℹ️",
    )


# ── summary cards ────────────────────────────────────────────────────────────

all_df   = st.session_state.metrics  # unfiltered for summary
n_red    = int((all_df["health_status"] == "Red").sum())
n_yellow = int((all_df["health_status"] == "Yellow").sum())
n_green  = int((all_df["health_status"] == "Green").sum())
n_total  = len(all_df)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        f'<div class="metric-card red">'
        f'<div class="metric-count" style="color:#991B1B">{n_red}</div>'
        f'<div class="metric-label">Red — Needs Attention</div></div>',
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f'<div class="metric-card yellow">'
        f'<div class="metric-count" style="color:#78350F">{n_yellow}</div>'
        f'<div class="metric-label">Yellow — Monitor</div></div>',
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f'<div class="metric-card green">'
        f'<div class="metric-count" style="color:#166534">{n_green}</div>'
        f'<div class="metric-label">Green — On Track</div></div>',
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        f'<div class="metric-card total">'
        f'<div class="metric-count" style="color:#1D4ED8">{n_total}</div>'
        f'<div class="metric-label">Total Projects Audited</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)


# ── tabs ─────────────────────────────────────────────────────────────────────

tab_overview, tab_timeline, tab_table, tab_insights = st.tabs(
    ["Overview", "Timeline", "Project Detail", "Insights"]
)


# ── overview tab ─────────────────────────────────────────────────────────────

with tab_overview:
    ch1, ch2 = st.columns([1, 2])

    with ch1:
        st.markdown("**Health Distribution**")
        counts = (
            all_df["health_status"]
            .value_counts()
            .reindex(HEALTH_ORDER)
            .fillna(0)
            .reset_index()
        )
        counts.columns = ["Health", "Count"]
        fig_donut = go.Figure(go.Pie(
            labels=counts["Health"],
            values=counts["Count"],
            hole=0.55,
            marker_colors=[HEALTH_COLORS[h] for h in counts["Health"]],
            textinfo="label+value",
            textfont_size=13,
            hovertemplate="%{label}: %{value} projects<extra></extra>",
        ))
        fig_donut.update_layout(
            showlegend=False,
            margin=dict(t=10, b=10, l=10, r=10),
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    with ch2:
        st.markdown("**Health by Project Manager**")
        pm_display = all_df.copy()
        pm_display["project_manager"] = (
            pm_display["project_manager"].fillna("").astype(str).str.strip()
            .replace("", "Unassigned")
        )
        pm_health = (
            pm_display.groupby(["project_manager", "health_status"])
            .size()
            .reset_index(name="count")
        )
        fig_bar = px.bar(
            pm_health,
            x="project_manager",
            y="count",
            color="health_status",
            color_discrete_map=HEALTH_COLORS,
            category_orders={"health_status": HEALTH_ORDER},
            labels={"project_manager": "Project Manager",
                    "count": "Projects", "health_status": "Health"},
            barmode="stack",
        )
        fig_bar.update_layout(
            margin=dict(t=10, b=10, l=0, r=0),
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis=dict(tickangle=-20),
        )
        fig_bar.update_traces(marker_line_width=0)
        st.plotly_chart(fig_bar, use_container_width=True)


# ── timeline tab ─────────────────────────────────────────────────────────────

with tab_timeline:
    ledger_all = st.session_state.get("ies_ledger")
    if ledger_all is None or ledger_all.empty:
        st.info(
            "Timeline data isn't available for these projects. It's produced "
            "automatically when you upload IES Estimate + Transactions files "
            "through the sidebar upload panel — the 'Advanced: CSVs' path "
            "doesn't carry dated transaction detail.",
            icon="ℹ️",
        )
    else:
        available_ids = sorted(set(all_df["project_id"]) & set(ledger_all["project_id"].unique()))
        if not available_ids:
            st.info("No timeline data for the currently loaded projects.", icon="ℹ️")
        else:
            selected_pid = st.selectbox("Project", available_ids)
            proj_row = all_df[all_df["project_id"] == selected_pid].iloc[0]
            proj_ledger = ledger_all[ledger_all["project_id"] == selected_pid]
            billing_type = proj_row.get("billing_type", "fixed_fee")
            thresholds = get_billing_thresholds(billing_type, criteria)

            st.caption(
                f"**{selected_pid}** · {str(billing_type).replace('_',' ').title()} · "
                f"Proposed ${proj_row.get('proposed_budget', 0):,.0f} / "
                f"{proj_row.get('proposed_hours', 0):,.0f} hrs"
            )

            if billing_type == "fixed_fee":
                st.warning(
                    "**Read this before the revenue chart:** fixed-fee projects are "
                    "often billed in large upfront milestones (e.g. 50% on order). "
                    "That makes the very start of the revenue line look 'ahead of "
                    "pace' — that's normal milestone billing, not an overrun. The "
                    "**hours burn chart below is the more reliable signal** for "
                    "fixed-fee overruns, since labor is consumed steadily rather "
                    "than billed in lump sums.",
                    icon="⚠️",
                )

            def _burn_chart(metric_col: str, proposed_value, green_pct: float,
                            yellow_pct: float, label: str, y_format: str):
                series = compute_burn_series(proj_ledger, proposed_value, metric_col, green_pct, yellow_pct)
                if series.empty or (series["zone"] == "Unavailable").all():
                    st.info(f"No {label.lower()} timeline data for this project.", icon="ℹ️")
                    return

                zone_seq = series["zone"].tolist()
                has_partial_coverage_gap = "Unavailable" in zone_seq and zone_seq[-1] != "Unavailable"
                if has_partial_coverage_gap:
                    st.warning(
                        f"**{label} tracking for this project started after the project itself did.** "
                        f"Points before tracking began are correctly excluded (shown as a gap), but "
                        f"the pace line still counts calendar time from the project's true start — so "
                        f"the period right after tracking begins can look artificially 'behind pace' "
                        f"even for a well-run project. Read the shape of the catch-up, not the color, "
                        f"for that stretch.",
                        icon="⚠️",
                    )

                crossings = first_crossing_dates(series)
                zone_colors = series["zone"].map(HEALTH_COLORS).fillna("#9CA3AF")

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=series["date"], y=series["expected_pace"],
                    mode="lines", name="Expected pace (straight-line)",
                    line=dict(color="#9CA3AF", dash="dash", width=1.5),
                    hovertemplate="Pace: %{y:,.0f}<extra></extra>",
                ))
                fig.add_trace(go.Scatter(
                    x=series["date"], y=series[metric_col],
                    mode="lines+markers", name="Actual (cumulative)",
                    line=dict(color="#2962FF", width=2),
                    marker=dict(color=zone_colors, size=8, line=dict(width=1, color="#fff")),
                    hovertext=series["zone"],
                    hovertemplate="Actual: %{y:,.0f}<br>Zone: %{hovertext}<extra></extra>",
                ))
                for label_txt, date_val, color in [
                    ("First Yellow", crossings["first_yellow"], "#F59E0B"),
                    ("First Red", crossings["first_red"], "#EF4444"),
                ]:
                    if date_val is not None:
                        fig.add_vline(
                            x=date_val, line_dash="dot", line_color=color,
                            annotation_text=f"{label_txt}: {date_val.date()}",
                            annotation_position="top", annotation_font_color=color,
                        )
                fig.update_layout(
                    height=340,
                    margin=dict(t=30, b=10, l=0, r=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="#FAFBFC",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                    yaxis=dict(tickformat=y_format, gridcolor="#E5E7EB"),
                    xaxis=dict(gridcolor="#E5E7EB"),
                )
                st.plotly_chart(fig, use_container_width=True)
                if crossings["first_red"]:
                    st.caption(f"🔴 First crossed into Red on **{crossings['first_red'].date()}**.")
                elif crossings["first_yellow"]:
                    st.caption(f"🟡 First crossed into Yellow on **{crossings['first_yellow'].date()}**, never reached Red.")
                else:
                    st.caption("🟢 Stayed within the Green band for its entire duration.")

            st.markdown("**Budget Burn — Cumulative Revenue vs. Pace**")
            _burn_chart(
                "cumulative_revenue", proj_row.get("proposed_budget"),
                thresholds["green_pct"], thresholds["yellow_pct"],
                "Budget", "$,.0f",
            )

            st.markdown("**Hours Burn — Cumulative Hours vs. Pace**")
            _burn_chart(
                "cumulative_hours", proj_row.get("proposed_hours"),
                thresholds["green_hours_pct"], thresholds["yellow_hours_pct"],
                "Hours", ",.0f",
            )

            st.caption(
                "Pace is a straight line from $0/0 hrs to the proposed total, spread "
                "across this project's own actual start→end dates (no promised "
                "delivery date exists in the source data — see the disclosure above). "
                "Green/Yellow/Red bands use this project's billing-type thresholds "
                "from the Audit Criteria Register."
            )


# ── project detail tab ───────────────────────────────────────────────────────

with tab_table:
    display_cols = {
        "project_id":            "ID",
        "project_name":          "Project",
        "client":                "Client",
        "project_manager":       "PM",
        "billing_type":          "Billing",
        "health_status":         "Health",
        "proposed_budget":       "Proposed $",
        "actual_budget":         "Actual $",
        "budget_dev_abs":        "Budget Δ $",
        "budget_dev_pct":        "Budget Δ %",
        "proposed_hours":        "Prop Hrs",
        "actual_hours":          "Act Hrs",
        "hours_dev_pct":         "Hours Δ %",
        "schedule_dev_days":     "Sched Δ days",
        "audit_finding":         "Audit Finding",
        "closeout_notes":        "Closeout Notes",
    }

    available = [c for c in display_cols if c in df.columns]
    display_df = df[available].rename(columns=display_cols).copy()

    for pct_col in ["Budget Δ %", "Hours Δ %"]:
        if pct_col in display_df.columns:
            display_df[pct_col] = display_df[pct_col].map(
                lambda v: f"{v:+.1%}" if pd.notna(v) else "—"
            )
    for d_col in ["Proposed $", "Actual $", "Budget Δ $"]:
        if d_col in display_df.columns:
            display_df[d_col] = display_df[d_col].map(
                lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
            )
    if "Billing" in display_df.columns:
        display_df["Billing"] = display_df["Billing"].str.replace("_", " ").str.title()
    if "Sched Δ days" in display_df.columns:
        display_df["Sched Δ days"] = display_df["Sched Δ days"].map(
            lambda v: f"{int(v):+d}" if pd.notna(v) else "—"
        )

    sort_order = {"Red": 0, "Yellow": 1, "Green": 2}
    display_df["_sort"] = display_df["Health"].map(sort_order).fillna(99)
    display_df = display_df.sort_values("_sort").drop(columns=["_sort"])

    def _row_style(row):
        h = row.get("Health", "")
        bg = {"Red": "#FEE2E288", "Yellow": "#FEF3C788", "Green": "#DCFCE788"}.get(h, "")
        return [f"background-color: {bg}"] * len(row)

    styled = display_df.style.apply(_row_style, axis=1)

    st.dataframe(
        styled,
        use_container_width=True,
        height=480,
        hide_index=True,
    )

    st.caption(
        f"Showing {len(df)} of {n_total} projects · "
        "Filters applied: health status, billing type, project manager"
    )


# ── insights tab ─────────────────────────────────────────────────────────────

with tab_insights:

    # ── Quality vs Outcome quadrant (when scoring data is loaded) ────────────
    scorecard = st.session_state.get("scorecard")
    if scorecard is not None and not scorecard.empty:
        st.markdown("**Project Scores — Outcome vs Process (0–10)**")
        show = scorecard[[c for c in [
            "project_id", "outcome_score_10", "outcome_metrics_used",
            "process_score_10", "process_band", "quadrant",
        ] if c in scorecard.columns]].rename(columns={
            "project_id": "ID",
            "outcome_score_10": "Outcome /10",
            "outcome_metrics_used": "Metrics Used",
            "process_score_10": "Process /10",
            "process_band": "Process Band",
            "quadrant": "Reading",
        })
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(
            "Outcome: computed from deviations and margin (reliable data only). "
            "Process: EPM rubric scores rolled up with category weights. "
            "The Reading column is where the two stories meet."
        )
        st.divider()

    # ── Tier 1: rule-based findings ──────────────────────────────────────────
    findings = analyse_patterns(st.session_state.metrics, criteria)

    SEVER_ICON = {
        "critical": "🔴",
        "warning":  "🟡",
        "info":     "🔵",
        "positive": "🟢",
    }
    SEVER_COLOR = {
        "critical": "#FEE2E2",
        "warning":  "#FEF3C7",
        "info":     "#EFF6FF",
        "positive": "#DCFCE7",
    }
    SEVER_BORDER = {
        "critical": "#EF4444",
        "warning":  "#F59E0B",
        "info":     "#3B82F6",
        "positive": "#22C55E",
    }

    st.markdown("**Automated Findings**")
    for f in findings:
        icon  = SEVER_ICON.get(f.severity, "🔵")
        bg    = SEVER_COLOR.get(f.severity, "#EFF6FF")
        border= SEVER_BORDER.get(f.severity, "#3B82F6")
        ids_html = ""
        if f.project_ids:
            chips = " ".join(
                f'<span style="font-size:11px;padding:1px 7px;border-radius:4px;'
                f'background:#E5E7EB;color:#374151;font-family:monospace">{pid}</span>'
                for pid in f.project_ids
            )
            ids_html = f'<div style="margin-top:6px">{chips}</div>'
        st.markdown(
            f'<div style="background:{bg};border-left:4px solid {border};'
            f'border-radius:0 6px 6px 0;padding:12px 16px;margin-bottom:10px">'
            f'<div style="font-weight:600;font-size:13px">{icon} {f.title}</div>'
            f'<div style="font-size:12px;color:#374151;margin-top:4px">{f.body}</div>'
            f'{ids_html}</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Tier 2: closeout notes search ────────────────────────────────────────
    st.markdown("**Search Closeout Notes**")
    st.caption("Find projects with similar issues by describing a situation.")

    notes_index = build_notes_index(st.session_state.metrics)
    if notes_index is None:
        st.info("scikit-learn not installed — notes search unavailable.", icon="ℹ️")
    else:
        query = st.text_input(
            "Describe a situation or issue",
            placeholder="e.g. vendor delay caused schedule slip",
            label_visibility="collapsed",
        )
        if query.strip():
            results = search_notes(query, notes_index, st.session_state.metrics, top_k=3)
            if not results:
                st.write("No matching projects found.")
            else:
                for res in results:
                    status = res["health_status"]
                    color, _ = (HEALTH_COLORS.get(status, "#6B7588"),
                                HEALTH_BG.get(status, "#F3F4F6"))
                    st.markdown(
                        f'<div style="border:1px solid #E2E5EA;border-radius:6px;'
                        f'padding:12px 16px;margin-bottom:8px;background:#fff">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center">'
                        f'<span style="font-weight:600">{res["project_name"]}</span>'
                        f'<span style="font-size:11px;color:#6B7588">{res["project_id"]} · '
                        f'<span style="color:{color};font-weight:600">{status}</span> · '
                        f'relevance {res["score"]:.2f}</span></div>'
                        f'<div style="font-size:12px;color:#6B7588;margin-top:6px">'
                        f'{res["closeout_notes"]}</div></div>',
                        unsafe_allow_html=True,
                    )

