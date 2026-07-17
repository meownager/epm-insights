"""Generate pre-filled, editable Excel audit forms — one per project.

Reproduces the company Project Audit Form layout: header block on top
(customer, project, PM, cost, revenue, profit %), then the category / score /
comments / rubric table. Financial fields are pre-filled from converter output;
score and comment cells are left blank for the EPM, with live Excel formulas
for Profit %, Total Score, Total Possible, and Percent.

Usage:
    python scripts/generate_audit_form.py \
        --financials data/real/audit_inputs/project_financials.csv \
        --output-dir data/real/audit_forms
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

DEFAULT_RUBRIC_PATH = Path(__file__).parent.parent / "config" / "quality_rubric.yaml"

HEADER_FILL = PatternFill("solid", fgColor="1A1F2E")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
LABEL_FONT = Font(bold=True, size=10)
THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def build_form(project: dict, rubric: dict, out_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit Form"

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 42
    ws.column_dimensions["D"].width = 70

    # ── header block ──
    header_rows = [
        ("Customer Name", project.get("client", "")),
        ("Project Number", project.get("project_id", "")),
        ("Project Name", project.get("project_name", "")),
        ("Project Manager", project.get("project_manager", "")),
        ("Technical Lead", ""),
        ("Cost", project.get("cost", "")),
        ("Revenue", project.get("revenue", "")),
    ]
    r = 1
    for label, value in header_rows:
        ws.cell(row=r, column=1, value=label).font = LABEL_FONT
        ws.cell(row=r, column=2, value=value if value != "" else None)
        r += 1

    cost_row, revenue_row = 6, 7
    ws.cell(row=r, column=1, value="Profit %").font = LABEL_FONT
    ws.cell(row=r, column=2, value=f"=IF(B{revenue_row}=0,\"\",(B{revenue_row}-B{cost_row})/B{revenue_row})").number_format = "0.0%"
    profit_row = r
    r += 1

    first_cat_row = r + 5  # Total Score, Total Possible, Percent, blank, table header

    n_cats = len(rubric["categories"])
    last_cat_row = first_cat_row + n_cats - 1
    ws.cell(row=r, column=1, value="Total Score").font = LABEL_FONT
    ws.cell(row=r, column=2, value=f"=SUM(B{first_cat_row}:B{last_cat_row})")
    r += 1
    ws.cell(row=r, column=1, value="Total Possible").font = LABEL_FONT
    ws.cell(row=r, column=2, value=f"=COUNT(B{first_cat_row}:B{last_cat_row})*4")
    total_possible_row = r
    r += 1
    ws.cell(row=r, column=1, value="Percent").font = LABEL_FONT
    ws.cell(
        row=r, column=2,
        value=f"=IF(B{total_possible_row}=0,\"\",B{r-2}/B{total_possible_row})",
    ).number_format = "0.0%"
    r += 2

    # ── table header ──
    for col, title in enumerate(["Category", "Score", "Comments", "Rubric"], start=1):
        c = ws.cell(row=r, column=col, value=title)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.border = BORDER
    r += 1
    assert r == first_cat_row, "layout drift — header rows changed without updating formulas"

    # ── score validation: 1-4 or na ──
    dv = DataValidation(type="list", formula1='"1,2,3,4,na"', allow_blank=True)
    dv.error = "Score must be 1, 2, 3, 4, or na"
    ws.add_data_validation(dv)

    for cat in rubric["categories"]:
        anchors = "\n".join(f"{k} - {v}" for k, v in sorted(cat["anchors"].items()))
        ws.cell(row=r, column=1, value=cat["name"]).border = BORDER
        score_cell = ws.cell(row=r, column=2)
        score_cell.border = BORDER
        dv.add(score_cell)
        ws.cell(row=r, column=3).border = BORDER
        rc = ws.cell(row=r, column=4, value=anchors)
        rc.border = BORDER
        rc.alignment = Alignment(wrap_text=True, vertical="top")
        rc.font = Font(size=8, color="666666")
        ws.row_dimensions[r].height = 46
        r += 1

    # ── pre-filled quantitative summary (read-only reference) ──
    r += 1
    ws.cell(row=r, column=1, value="AUTO-FILLED FROM AUDIT DATA").font = Font(bold=True, size=9, color="1D4ED8")
    r += 1
    for label, key, fmt in [
        ("Billing Type", "billing_type", None),
        ("Estimate Total", "estimate_total", "#,##0.00"),
        ("Revenue Invoiced", "revenue_invoiced", "#,##0.00"),
        ("Planned Margin", "planned_margin_pct", "0.0%"),
        ("Actual Margin", "actual_margin_pct", "0.0%"),
        ("Margin Reliability", "margin_reliability", None),
        ("Change Orders", "co_count", None),
        ("CO Dollars", "co_dollars", "#,##0.00"),
        ("Unbilled WIP", "unbilled_wip", "#,##0.00"),
        ("Overdue Invoices", "overdue_invoices", None),
        ("Hours Source", "hours_source", None),
    ]:
        val = project.get(key, "")
        ws.cell(row=r, column=1, value=label).font = Font(size=9)
        cell = ws.cell(row=r, column=2, value=val if val != "" else None)
        cell.font = Font(size=9)
        if fmt:
            cell.number_format = fmt
        r += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate editable Excel audit forms")
    ap.add_argument("--financials", required=True, help="project_financials.csv from the converter")
    ap.add_argument("--output-dir", required=True, help="Folder for generated .xlsx forms")
    ap.add_argument("--rubric", default=str(DEFAULT_RUBRIC_PATH))
    args = ap.parse_args()

    rubric = yaml.safe_load(open(args.rubric))
    fin = pd.read_csv(args.financials)
    out_dir = Path(args.output_dir)

    for _, row in fin.iterrows():
        project = row.to_dict()
        # cost = planned internal+external actuals where known
        ext = pd.to_numeric(row.get("external_cost_bills"), errors="coerce") or 0
        exp = pd.to_numeric(row.get("external_cost_expenses"), errors="coerce") or 0
        internal = pd.to_numeric(row.get("internal_labor_cost"), errors="coerce")
        project["cost"] = round((internal if pd.notna(internal) else 0) + ext + exp, 2)
        project["revenue"] = row.get("revenue_invoiced", "")
        out = out_dir / f"audit_form_{row['project_id']}.xlsx"
        build_form(project, rubric, out)
        print(f"wrote {out}")

    print(f"\n{len(fin)} audit forms generated in {out_dir}")
    print("Rubric version:", rubric.get("version"))


if __name__ == "__main__":
    main()
