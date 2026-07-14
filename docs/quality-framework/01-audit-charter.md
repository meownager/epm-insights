# Audit Charter

## Purpose

This charter defines the scope, authority, and boundaries of the epm-insights audit system. It establishes what the system audits, what it does not audit, and who it serves.

## Scope

The audit system evaluates engineering project performance by comparing approved proposal baselines against actual outcomes. It covers all projects that have entered the approved state and progressed through the active lifecycle.

Auditable project states: `approved` → `active` → `paused` → `completed`

The first implemented audit slice covers `completed` and `closed` projects. Active and paused project auditing reuses the same engine with additional in-flight metrics.

## What the Audit Measures

- Budget deviation (actual vs. proposed)
- Hours deviation (actual vs. proposed)
- Schedule deviation (actual end date vs. proposed end date)
- Resource count deviation (actual vs. proposed)
- Advisory health classification (Green / Yellow / Red)
- Structured findings per project

## What the Audit Does Not Do

- The audit does not evaluate project quality, client satisfaction, or engineering judgment.
- The audit does not change any metric or health classification based on AI or narrative input.
- The audit does not access real company data — only data explicitly provided by the user.
- Proposal data (pre-approval) is the comparison baseline, not an audited state.

## Authority and Use

Audit results are advisory. Health classifications (Green / Yellow / Red) are decision-support tools, not binding determinations. The project owner reviews findings and determines follow-up actions.

All thresholds that drive health classification are defined in the Audit Criteria Register (`config/audit_criteria.yaml`). No thresholds exist in any other location.

## Interested Parties

| Party | Interest |
|---|---|
| Project owner (Syeda M.) | Accurate, traceable audit results for portfolio review |
| Project managers | Fair, criteria-based performance feedback |
| Clients | Indirectly — project health affects delivery commitments |
| Future team members | Consistent, documented process they can learn and trust |

## Boundaries

- All processing is local. No data leaves the user's machine.
- Only synthetic or public data is committed to the repository. Real company data stays local and git-ignored.
- The audit engine is deterministic — the same inputs and criteria version always produce the same outputs.

## Document Owner

Syeda M. (smonowar@purdue.edu)
