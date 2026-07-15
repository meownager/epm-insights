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
from completed_project_health import compute_metrics, load_criteria, write_run_record
from generate_html_report import build_report
from insights import (
    analyse_patterns, build_notes_index, search_notes,
    check_ollama, generate_narrative,
)

# ── constants ───────────────────────────────────────────────────────────────

DEFAULT_PROPOSAL = str(Path(__file__).parent / "data/sample/proposal_projects.csv")
DEFAULT_ACTUAL   = str(Path(__file__).parent / "data/sample/actual_projects.csv")
DEFAULT_CRITERIA = str(Path(__file__).parent / "config/audit_criteria.yaml")

HEALTH_ORDER  = ["Red", "Yellow", "Green"]
HEALTH_COLORS = {"Red": "#EF4444", "Yellow": "#F59E0B", "Green": "#22C55E"}
HEALTH_BG     = {"Red": "#FEE2E2", "Yellow": "#FEF3C7", "Green": "#DCFCE7"}
HEALTH_TEXT   = {"Red": "#991B1B", "Yellow": "#78350F", "Green": "#166534"}

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

    st.markdown("**Data Files**")
    proposal_path = st.text_input("Proposal CSV", value=DEFAULT_PROPOSAL)
    actual_path   = st.text_input("Actual CSV",   value=DEFAULT_ACTUAL)
    criteria_path = st.text_input("Criteria YAML", value=DEFAULT_CRITERIA)

    run_clicked = st.button("▶  Run Audit", type="primary", use_container_width=True)

    st.divider()
    st.markdown("**Filters**")
    filter_health  = st.multiselect("Health Status", HEALTH_ORDER, default=HEALTH_ORDER)
    filter_billing = st.multiselect("Billing Type",  ["fixed_fee", "t_and_e"],
                                    default=["fixed_fee", "t_and_e"])
    filter_pm      = st.multiselect("Project Manager", [], key="pm_filter")

    st.divider()
    st.caption("All processing is local.\nNo data leaves your machine.")


# ── session state ────────────────────────────────────────────────────────────

if "metrics" not in st.session_state:
    st.session_state.metrics  = None
    st.session_state.meta     = {}
    st.session_state.criteria = {}


# ── run audit ────────────────────────────────────────────────────────────────

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

tab_overview, tab_table, tab_insights = st.tabs(["Overview", "Project Detail", "Insights"])


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
        pm_health = (
            all_df.groupby(["project_manager", "health_status"])
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

    st.markdown("**Budget vs Hours Deviation** (filtered view)")
    scatter_df = df.copy()
    scatter_df["budget_dev_pct_disp"] = scatter_df["budget_dev_pct"] * 100
    scatter_df["hours_dev_pct_disp"]  = scatter_df["hours_dev_pct"]  * 100
    scatter_df["billing_label"] = scatter_df["billing_type"].str.replace("_", " ").str.title()

    fig_scatter = px.scatter(
        scatter_df,
        x="budget_dev_pct_disp",
        y="hours_dev_pct_disp",
        color="health_status",
        color_discrete_map=HEALTH_COLORS,
        symbol="billing_label",
        hover_name="project_name",
        hover_data={
            "project_id": True,
            "project_manager": True,
            "budget_dev_pct_disp": ":.1f",
            "hours_dev_pct_disp":  ":.1f",
            "health_status": True,
            "billing_label": True,
        },
        labels={
            "budget_dev_pct_disp": "Budget Deviation (%)",
            "hours_dev_pct_disp":  "Hours Deviation (%)",
            "health_status":       "Health",
            "billing_label":       "Billing Type",
        },
        category_orders={"health_status": HEALTH_ORDER},
    )

    # add zero lines and threshold bands
    fig_scatter.add_hline(y=0,  line_dash="dash", line_color="#CBD5E1", line_width=1)
    fig_scatter.add_vline(x=0,  line_dash="dash", line_color="#CBD5E1", line_width=1)
    fig_scatter.update_layout(
        height=380,
        margin=dict(t=10, b=10, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FAFBFC",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig_scatter.update_xaxes(zeroline=False, gridcolor="#E5E7EB")
    fig_scatter.update_yaxes(zeroline=False, gridcolor="#E5E7EB")
    st.plotly_chart(fig_scatter, use_container_width=True)


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

    st.divider()

    # ── Tier 3: Ollama narrative ──────────────────────────────────────────────
    st.markdown("**AI Narrative Summary** *(requires Ollama running locally)*")

    ollama_host   = st.text_input("Ollama host", value="http://localhost:11434",
                                   label_visibility="collapsed")
    available_models = check_ollama(ollama_host)

    if not available_models:
        st.info(
            "Ollama is not running or has no models loaded. "
            "Install Ollama from [ollama.com](https://ollama.com), "
            "then run `ollama pull llama3` (or any model), and refresh this page.",
            icon="ℹ️",
        )
    else:
        model_choice = st.selectbox("Model", available_models)
        if st.button("Generate Executive Summary", type="primary"):
            with st.spinner(f"Asking {model_choice}…"):
                narrative = generate_narrative(
                    findings,
                    st.session_state.metrics,
                    model=model_choice,
                    host=ollama_host,
                )
            st.markdown(
                f'<div style="background:#F8FAFC;border:1px solid #E2E5EA;border-radius:8px;'
                f'padding:20px 24px;font-size:13px;line-height:1.7;color:#1A1F2E">'
                f'{narrative}</div>',
                unsafe_allow_html=True,
            )
