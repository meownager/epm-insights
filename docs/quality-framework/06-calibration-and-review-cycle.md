# Calibration and Review Cycle

## Purpose

Audit thresholds are not permanent. They are calibrated against real project outcomes over time. This document defines when reviews happen, what triggers them, and what a review produces.

## Scheduled Review

The Audit Criteria Register is reviewed on the following schedule:

| Review | Trigger | Action |
|---|---|---|
| Quarterly review | Every three months | Compare threshold performance against recent completed projects; adjust if thresholds are systematically over- or under-flagging |
| Post-portfolio review | After each full portfolio audit cycle | Review whether Green/Yellow/Red distribution reflects actual project risk experienced |
| Triggered review | A finding in the corrective action log identifies a threshold problem | Immediate review of the affected threshold |

## What a Review Examines

1. **False Green rate:** Projects classified Green that had unreported issues discovered later. If this is non-zero, Green thresholds may be too loose.
2. **False Red rate:** Projects classified Red that were actually successful by all stakeholder measures. If this is high, Red thresholds may be too tight.
3. **Yellow usefulness:** Projects in Yellow — were they genuinely borderline, or systematically Green or Red in hindsight? If Yellow is rarely meaningful, threshold spacing may need adjustment.
4. **New metric candidates:** Are there patterns in closeout notes that no current metric captures?

## How to Record a Review

1. Run the audit against completed project history with the current criteria version.
2. Compare results against stakeholder assessments of those projects.
3. Document findings in `07-findings-and-corrective-action-log.md`.
4. If thresholds change, update `config/audit_criteria.yaml` following the process in `03-criteria-register-management.md`.
5. Record the review date and outcome in the table below.

## Review History

| Date | Criteria Version Reviewed | Outcome | New Version (if changed) |
|---|---|---|---|
| 2026-07-13 | 1.0.0 | Initial release — thresholds set based on engineering judgment; no historical data yet available. Baseline established for future calibration. | — |

## Document Owner

Syeda M. (smonowar@purdue.edu)
