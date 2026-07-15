#!/usr/bin/env python3
"""Generate a standalone HTML audit report from completed_project_health output.

Reads the detail CSV (and optional run record JSON) produced by
completed_project_health.py and writes a self-contained HTML file with
no external dependencies.

Usage:
    python scripts/generate_html_report.py \
        --detail outputs/sample/completed_project_health_detail.csv \
        --run-record outputs/sample/runs/run_*.json \
        --output outputs/sample/audit_report.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


HEALTH_COLOR = {
    "Green": ("#166534", "#dcfce7"),   # text, background
    "Yellow": ("#713f12", "#fef9c3"),
    "Red": ("#991b1b", "#fee2e2"),
}
HEALTH_SORT = {"Red": 0, "Yellow": 1, "Green": 2}


def fmt_pct(val) -> str:
    if pd.isna(val):
        return "—"
    return f"{val:+.1%}"


def fmt_dollar(val) -> str:
    if pd.isna(val):
        return "—"
    return f"${val:,.0f}"


def fmt_days(val) -> str:
    if pd.isna(val):
        return "—"
    v = int(val)
    return f"+{v}" if v > 0 else str(v)


def badge(status: str) -> str:
    color, bg = HEALTH_COLOR.get(status, ("#374151", "#f3f4f6"))
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'font-weight:600;font-size:0.78rem;color:{color};background:{bg}">'
        f"{status}</span>"
    )


def summary_card(label: str, count: int, status: str) -> str:
    color, bg = HEALTH_COLOR.get(status, ("#374151", "#f3f4f6"))
    return (
        f'<div style="flex:1;min-width:140px;padding:18px 24px;border-radius:10px;'
        f'background:{bg};border:1px solid {color}22">'
        f'<div style="font-size:2rem;font-weight:700;color:{color}">{count}</div>'
        f'<div style="font-size:0.9rem;color:{color};font-weight:600">{label}</div>'
        f"</div>"
    )


def build_report(detail: pd.DataFrame, meta: dict) -> str:
    detail = detail.copy()
    detail["_sort"] = detail["health_status"].map(HEALTH_SORT).fillna(99)
    detail = detail.sort_values("_sort").drop(columns=["_sort"])

    counts = detail["health_status"].value_counts()
    n_green = int(counts.get("Green", 0))
    n_yellow = int(counts.get("Yellow", 0))
    n_red = int(counts.get("Red", 0))
    n_total = len(detail)

    run_id = meta.get("run_id", "—")[:8]
    ts = meta.get("timestamp", "—")[:19].replace("T", " ")
    criteria_ver = meta.get("criteria_version", "—")
    proposal_fp = meta.get("proposal_fingerprint", "—")[:12]
    actual_fp = meta.get("actual_fingerprint", "—")[:12]

    rows = []
    for _, r in detail.iterrows():
        status = r.get("health_status", "")
        _, row_bg = HEALTH_COLOR.get(status, ("#374151", "#ffffff"))
        finding = str(r.get("audit_finding", "")).replace("<", "&lt;").replace(">", "&gt;")
        notes = str(r.get("closeout_notes", "")).replace("<", "&lt;").replace(">", "&gt;")
        billing = str(r.get("billing_type", "")).replace("_", " ").title()
        rows.append(f"""
        <tr style="background:{row_bg}88">
          <td style="font-weight:600">{r.get('project_id','')}</td>
          <td>{r.get('project_name','')}</td>
          <td>{r.get('client','')}</td>
          <td>{r.get('project_manager','')}</td>
          <td>{r.get('project_type','')}</td>
          <td>{billing}</td>
          <td style="text-align:right">{fmt_dollar(r.get('proposed_budget'))}</td>
          <td style="text-align:right">{fmt_dollar(r.get('actual_budget'))}</td>
          <td style="text-align:right">{fmt_dollar(r.get('budget_dev_abs'))}</td>
          <td style="text-align:right">{fmt_pct(r.get('budget_dev_pct'))}</td>
          <td style="text-align:right">{r.get('proposed_hours','—')}</td>
          <td style="text-align:right">{r.get('actual_hours','—')}</td>
          <td style="text-align:right">{fmt_pct(r.get('hours_dev_pct'))}</td>
          <td style="text-align:right">{fmt_days(r.get('schedule_dev_days'))}</td>
          <td style="text-align:center">{badge(status)}</td>
          <td style="font-size:0.82rem;color:#374151">{finding}</td>
          <td style="font-size:0.82rem;color:#6b7280">{notes}</td>
        </tr>""")

    rows_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Completed Project Health Audit</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0; padding: 24px 32px;
    background: #f9fafb; color: #111827;
    font-size: 14px;
  }}
  h1 {{ margin: 0 0 4px; font-size: 1.5rem; color: #111827; }}
  .subtitle {{ color: #6b7280; margin-bottom: 24px; font-size: 0.88rem; }}
  .meta-bar {{
    display: flex; gap: 24px; flex-wrap: wrap;
    background: #fff; border: 1px solid #e5e7eb;
    border-radius: 8px; padding: 12px 18px; margin-bottom: 20px;
    font-size: 0.82rem; color: #6b7280;
  }}
  .meta-bar span {{ white-space: nowrap; }}
  .meta-bar strong {{ color: #374151; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px; }}
  .section-label {{
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.05em;
    text-transform: uppercase; color: #6b7280; margin-bottom: 10px;
  }}
  .table-wrap {{ overflow-x: auto; border-radius: 10px; border: 1px solid #e5e7eb; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 1100px; background: #fff; }}
  thead tr {{ background: #f3f4f6; }}
  th {{
    padding: 10px 12px; text-align: left; font-size: 0.75rem;
    font-weight: 600; color: #6b7280; text-transform: uppercase;
    letter-spacing: 0.04em; white-space: nowrap;
    border-bottom: 1px solid #e5e7eb;
  }}
  td {{
    padding: 9px 12px; border-bottom: 1px solid #e5e7eb11;
    vertical-align: top; white-space: nowrap;
  }}
  td:nth-child(16), td:nth-child(17) {{ white-space: normal; min-width: 200px; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ filter: brightness(0.97); }}
  .footer {{
    margin-top: 28px; font-size: 0.78rem; color: #9ca3af;
    border-top: 1px solid #e5e7eb; padding-top: 16px;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f172a; color: #e2e8f0; }}
    h1 {{ color: #f1f5f9; }}
    .meta-bar {{ background: #1e293b; border-color: #334155; color: #94a3b8; }}
    .meta-bar strong {{ color: #e2e8f0; }}
    .table-wrap {{ border-color: #334155; }}
    table {{ background: #1e293b; }}
    thead tr {{ background: #0f172a; }}
    th {{ color: #94a3b8; }}
    td {{ border-bottom-color: #33415511; }}
  }}
</style>
</head>
<body>

<h1>Completed Project Health Audit</h1>
<p class="subtitle">Advisory health classifications based on deviation from approved baseline. For management review only — not a financial statement.</p>

<div class="meta-bar">
  <span><strong>Run ID:</strong> {run_id}…</span>
  <span><strong>Generated:</strong> {ts} UTC</span>
  <span><strong>Criteria:</strong> v{criteria_ver}</span>
  <span><strong>Projects audited:</strong> {n_total}</span>
  <span><strong>Proposal SHA-256:</strong> {proposal_fp}…</span>
  <span><strong>Actual SHA-256:</strong> {actual_fp}…</span>
</div>

<div class="section-label">Health Summary</div>
<div class="cards">
  {summary_card("Red — needs attention", n_red, "Red")}
  {summary_card("Yellow — monitor", n_yellow, "Yellow")}
  {summary_card("Green — on track", n_green, "Green")}
</div>

<div class="section-label">Project Detail — sorted by severity</div>
<div class="table-wrap">
<table>
<thead>
<tr>
  <th>Project ID</th>
  <th>Project Name</th>
  <th>Client</th>
  <th>PM</th>
  <th>Type</th>
  <th>Billing</th>
  <th>Proposed $</th>
  <th>Actual $</th>
  <th>Δ $</th>
  <th>Δ %</th>
  <th>Prop. Hrs</th>
  <th>Act. Hrs</th>
  <th>Hrs Δ%</th>
  <th>Sched Δ days</th>
  <th>Health</th>
  <th>Audit Finding</th>
  <th>Closeout Notes</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>

<div class="footer">
  epm-insights · Audit Criteria Register v{criteria_ver} ·
  Classifications are advisory. Green/Yellow/Red reflect deviation from approved baseline only.
  All processing is local; no data was transmitted externally.
</div>

</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML audit report")
    parser.add_argument("--detail", required=True, help="Path to completed_project_health_detail.csv")
    parser.add_argument("--run-record", help="Path to run record JSON (optional)")
    parser.add_argument("--output", required=True, help="Path for output HTML file")
    args = parser.parse_args()

    detail = pd.read_csv(args.detail)

    meta: dict = {}
    if args.run_record:
        rr_path = Path(args.run_record)
        if rr_path.exists():
            meta = json.loads(rr_path.read_text())
        else:
            # glob support: if user passed a glob pattern like "outputs/runs/*.json"
            matches = sorted(rr_path.parent.glob(rr_path.name))
            if matches:
                meta = json.loads(matches[-1].read_text())

    html = build_report(detail, meta)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"HTML report written to: {out}")


if __name__ == "__main__":
    main()
