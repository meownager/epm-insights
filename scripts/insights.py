from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

OLLAMA_OPTIONAL_NOTE = (
    "Optional local AI feature: install and run Ollama locally, then select a model. "
    "Core audit metrics and health classifications do not depend on Ollama."
)


@dataclass
class Finding:
    title: str
    body: str
    severity: str = "info"
    metric: str = ""
    project_ids: list[str] = field(default_factory=list)


def analyse_patterns(metrics: pd.DataFrame, criteria: dict) -> list[Finding]:
    findings: list[Finding] = []
    if metrics.empty:
        return findings

    n_total  = len(metrics)
    n_red    = int((metrics["health_status"] == "Red").sum())
    n_yellow = int((metrics["health_status"] == "Yellow").sum())
    n_green  = int((metrics["health_status"] == "Green").sum())

    pct_red = n_red / n_total * 100
    sev = "critical" if pct_red >= 30 else ("warning" if pct_red >= 15 else "positive")
    findings.append(Finding(
        title="Portfolio Health Overview",
        body=(f"{n_total} completed projects audited. "
              f"{n_red} Red ({pct_red:.0f}%), {n_yellow} Yellow "
              f"({n_yellow/n_total*100:.0f}%), {n_green} Green "
              f"({n_green/n_total*100:.0f}%)."),
        severity=sev,
    ))

    red_yellow = metrics[metrics["health_status"].isin(["Red", "Yellow"])]
    if not red_yellow.empty:
        cp = criteria.get("completed_projects", {})
        ff = cp.get("fixed_fee", {})
        budget_green = ff.get("budget", {}).get("green_max", 0.15)
        hours_green  = ff.get("hours",  {}).get("green_max", 0.15)
        sched_green  = ff.get("schedule", {}).get("green_max_days", 7)

        over_budget = int((red_yellow["budget_dev_pct"].abs() > budget_green).sum())
        over_hours  = int((red_yellow["hours_dev_pct"].abs()  > hours_green).sum())
        over_sched  = int((red_yellow["schedule_dev_days"]    > sched_green).sum())

        dims = sorted(
            [("budget", over_budget), ("hours", over_hours), ("schedule", over_sched)],
            key=lambda x: -x[1],
        )
        top_dim, top_n = dims[0]
        findings.append(Finding(
            title="Dominant Risk Dimension",
            body=(f"Among non-Green projects, {top_dim} deviation is the most common trigger: "
                  f"{top_n} of {len(red_yellow)} projects exceeded the Green threshold on {top_dim}. "
                  f"Hours: {over_hours}, Schedule: {over_sched}, Budget: {over_budget}."),
            severity="warning",
            metric=top_dim,
        ))

    red_ff = metrics[
        (metrics["health_status"] == "Red") &
        (metrics["billing_type"] == "fixed_fee") &
        (metrics["budget_dev_abs"] > 0)
    ]
    if not red_ff.empty:
        total_at_risk = red_ff["budget_dev_abs"].sum()
        ids = red_ff["project_id"].tolist()
        findings.append(Finding(
            title="Margin Exposure — Red Fixed-Fee Overruns",
            body=(f"{len(red_ff)} Red fixed-fee project(s) ran over budget by a combined "
                  f"${total_at_risk:,.0f}. These overruns are absorbed by the company. "
                  f"Projects: {', '.join(ids)}."),
            severity="critical",
            metric="budget",
            project_ids=ids,
        ))

    if "project_manager" in metrics.columns:
        pm_counts = (
            metrics.groupby("project_manager")["health_status"]
            .value_counts()
            .unstack(fill_value=0)
        )
        for color in ["Red", "Yellow", "Green"]:
            if color not in pm_counts.columns:
                pm_counts[color] = 0
        pm_counts["non_green"] = pm_counts.get("Red", 0) + pm_counts.get("Yellow", 0)
        worst_pm = pm_counts["non_green"].idxmax()
        worst_n  = int(pm_counts.loc[worst_pm, "non_green"])
        total_pm = int(pm_counts.loc[worst_pm, ["Red", "Yellow", "Green"]].sum())
        if worst_n > 0:
            reds    = int(pm_counts.loc[worst_pm, "Red"])
            yellows = int(pm_counts.loc[worst_pm, "Yellow"])
            findings.append(Finding(
                title="PM with Most Non-Green Projects",
                body=(f"{worst_pm} has {worst_n} of {total_pm} projects flagged "
                      f"({reds} Red, {yellows} Yellow). "
                      f"Review for systemic estimation or execution patterns."),
                severity="warning" if reds == 0 else "critical",
            ))

    if "client" in metrics.columns:
        client_red = (
            metrics[metrics["health_status"] == "Red"]
            .groupby("client").size().sort_values(ascending=False)
        )
        if not client_red.empty:
            top_client = client_red.index[0]
            top_n_c = int(client_red.iloc[0])
            findings.append(Finding(
                title="Client with Most Red Projects",
                body=(f"{top_client} has {top_n_c} Red project(s). "
                      f"Consider a relationship review to discuss expectations and change management."),
                severity="warning",
            ))

    if "billing_type" in metrics.columns:
        for bt in ["fixed_fee", "t_and_e"]:
            bt_df = metrics[metrics["billing_type"] == bt]
            if bt_df.empty:
                continue
            bt_red = int((bt_df["health_status"] == "Red").sum())
            bt_pct = bt_red / len(bt_df) * 100
            label = "Fixed Fee" if bt == "fixed_fee" else "T&E"
            if bt_pct >= 30:
                findings.append(Finding(
                    title=f"{label} Projects — Elevated Red Rate",
                    body=(f"{bt_red} of {len(bt_df)} {label} projects ({bt_pct:.0f}%) are Red. "
                          f"{'Fixed-fee overruns directly impact company margin.' if bt == 'fixed_fee' else 'T&E overruns may indicate scope growth without change orders.'}"),
                    severity="critical",
                    metric="budget",
                ))

    if "closeout_notes" in metrics.columns:
        scope_keywords = ["scope", "change order", "added", "grew", "expanded",
                          "requested", "additional", "unplanned"]
        co_keywords    = ["change order"]
        flagged = []
        for _, row in metrics[metrics["health_status"].isin(["Red", "Yellow"])].iterrows():
            notes = str(row.get("closeout_notes", "")).lower()
            if any(kw in notes for kw in scope_keywords) and not any(kw in notes for kw in co_keywords):
                flagged.append(row.get("project_id", ""))
        if flagged:
            findings.append(Finding(
                title="Potential Scope Growth Without Change Order",
                body=(f"{len(flagged)} project(s) have closeout notes suggesting scope changes "
                      f"with no change order documented: {', '.join(flagged)}. "
                      f"Review whether missed change orders contributed to overruns."),
                severity="critical",
                metric="scope",
                project_ids=flagged,
            ))

    return findings


class NotesIndex:
    def __init__(self, vectorizer: Any, matrix: Any, project_ids: list[str]):
        self.vectorizer  = vectorizer
        self.matrix      = matrix
        self.project_ids = project_ids


def build_notes_index(metrics: pd.DataFrame) -> NotesIndex | None:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        return None

    if "closeout_notes" not in metrics.columns:
        return None

    docs = metrics["closeout_notes"].fillna("").astype(str).tolist()
    ids  = metrics["project_id"].tolist()
    if not any(docs):
        return None

    vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
    matrix = vectorizer.fit_transform(docs)
    return NotesIndex(vectorizer=vectorizer, matrix=matrix, project_ids=ids)


def search_notes(query: str, index: NotesIndex, metrics: pd.DataFrame,
                 top_k: int = 3) -> list[dict]:
    try:
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return []

    q_vec = index.vectorizer.transform([query])
    sims  = cosine_similarity(q_vec, index.matrix).flatten()
    top_i = np.argsort(sims)[::-1][:top_k]

    results = []
    for i in top_i:
        pid = index.project_ids[i]
        row = metrics[metrics["project_id"] == pid]
        if row.empty:
            continue
        r = row.iloc[0]
        results.append({
            "project_id":     pid,
            "project_name":   r.get("project_name", ""),
            "health_status":  r.get("health_status", ""),
            "closeout_notes": r.get("closeout_notes", ""),
            "score":          float(sims[i]),
        })
    return results


def check_ollama(host: str = "http://localhost:11434") -> list[str]:
    """Return locally available Ollama models, or empty list when unavailable."""
    try:
        import requests
        r = requests.get(f"{host}/api/tags", timeout=2)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def generate_narrative(findings: list[Finding], metrics: pd.DataFrame,
                       model: str, host: str = "http://localhost:11434") -> str:
    try:
        import requests
    except ImportError:
        return f"requests library not available. {OLLAMA_OPTIONAL_NOTE}"

    summary_lines = [f"- [{f.severity.upper()}] {f.title}: {f.body}" for f in findings]
    project_lines = []
    for _, row in metrics.iterrows():
        bt = str(row.get("billing_type", "")).replace("_", " ")
        project_lines.append(
            f"  {row.get('project_id','')} | {row.get('project_name','')} | "
            f"{row.get('client','')} | PM: {row.get('project_manager','')} | "
            f"{bt} | {row.get('health_status','')} | "
            f"Budget Δ: {row.get('budget_dev_pct', 0)*100:.1f}% | "
            f"Hours Δ: {row.get('hours_dev_pct', 0)*100:.1f}% | "
            f"Schedule Δ: {row.get('schedule_dev_days', 0):.0f} days | "
            f"Notes: {str(row.get('closeout_notes',''))[:120]}"
        )

    prompt = textwrap.dedent(f"""
        You are an engineering project management analyst. Write a concise executive summary
        (4-6 sentences) for an engineering leadership team based on this completed project
        health audit. Focus on patterns, risks, and actionable observations.
        Do not list every project individually. Be direct and specific.

        AUDIT FINDINGS:
        {chr(10).join(summary_lines)}

        PROJECT DATA:
        {chr(10).join(project_lines)}

        Write the executive summary now:
    """).strip()

    try:
        r = requests.post(f"{host}/api/generate",
                          json={"model": model, "prompt": prompt, "stream": False},
                          timeout=60)
        if r.status_code == 200:
            return r.json().get("response", "No response from model.").strip()
        return f"Ollama returned status {r.status_code}. {OLLAMA_OPTIONAL_NOTE}"
    except Exception as e:
        return f"Could not reach Ollama: {e}. {OLLAMA_OPTIONAL_NOTE}"