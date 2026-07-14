# External Audit Alignment Map

## Purpose

This document maps each element of the epm-insights quality framework to the concepts that external auditors and quality reviewers look for when assessing whether an audit process is controlled, measurable, and improvable. No specific standard is referenced by name — the alignment is structural and self-evident from the framework elements themselves.

## Alignment Map

| Quality Concept | How epm-insights Addresses It |
|---|---|
| **Defined scope and boundaries** | Audit Charter (`01-audit-charter.md`) defines exactly what is audited, what is not, eligible project states, and the privacy boundary. |
| **Documented roles and authority** | Roles and Responsibilities (`02-roles-and-responsibilities.md`) names who owns criteria, who may change thresholds, who approves reports, and the separation of duties. |
| **Controlled criteria** | Audit Criteria Register (`config/audit_criteria.yaml`) is the sole source of thresholds. Every change is versioned with a recorded reason. No threshold exists elsewhere. |
| **Documented procedures** | Defined Process Steps (`05-defined-process-steps.md`) specifies every pipeline stage with inputs, outputs, formulas, pass criteria, and failure handling. |
| **Traceability and records** | Every run produces a run record containing run ID, timestamp, criteria version, and input fingerprints. Reports state the criteria version that produced them. |
| **Document control** | Document and Record Control (`04-document-and-record-control.md`) lists all controlled documents, their owners, and the run record schema. All documents are version-controlled in git. |
| **Measurement and monitoring** | Deviation metrics (budget, hours, schedule, resources) are computed by visible formulas. Health classification rules are explicit and criteria-driven, not subjective. |
| **Continual improvement** | Calibration and Review Cycle (`06-calibration-and-review-cycle.md`) schedules regular threshold reviews against real outcomes. Findings and Corrective Action Log (`07-findings-and-corrective-action-log.md`) tracks process deficiencies through to resolution. |
| **Nonconformance handling** | Findings log captures process-level nonconformances with root cause, corrective action, owner, and resolution date. |
| **Interested parties** | Audit Charter identifies all parties with a stake in the audit results and their interests. |
| **Separation of AI from audit decisions** | AI features (Phase 5) are explicitly additive — they can explain, compare, and draft, but cannot change a metric or health classification. Audit numbers are byte-identical with insights on or off. |
| **Data integrity** | Input files are fingerprinted (SHA-256) in run records. Real company data never enters the repository — only synthetic data is committed. |
| **Competence** | Roles document names the system owner and defines the boundary of what project managers may and may not do (provide data; not modify thresholds or results). |

## What an External Reviewer Would Find

An external reviewer examining this framework would find:

1. A written scope with clear in/out boundaries
2. Named ownership of every controlled element
3. A single, versioned source of criteria with a change process
4. Step-by-step documented procedures with pass/fail criteria
5. A traceable record for every run
6. A scheduled calibration process with a written history
7. A log for process-level findings with follow-up tracking
8. This alignment map itself — demonstrating that the framework was designed with auditability in mind

## Document Owner

Syeda M. (smonowar@purdue.edu)
