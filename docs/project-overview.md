# epm-insights 

## Project Overview

### Purpose

epm-insights is an AI-assisted project analysis and audit system for Engineering Program/Project Managers.

I am building it to compare proposal expectations with actual performance, evaluate completed or paused work against defined audit metrics, and generate project health and post-mortem reports that are clear enough to use in real review conversations.

The focus is structured evaluation supported by data analytics and an intelligent insights layer. epm-insights is designed to show what was planned, what changed, where performance moved away from the original expectation, and what that means for future estimating, execution, project control, and program-level visibility.

### Target User

The first version is designed for individual project review. Once the workflow is stable, it can be shared with other engineering project managers for broader review and feedback.

### Core Problem

Engineering project managers often need to understand whether a project performed as expected. That review usually requires checking estimates, hours, rates, resource usage, billing status, deadlines, change orders, and final outcomes across multiple files.

epm-insights brings that information into one workflow so I can review each project or program with the same structure and the same performance logic.

### Core Inputs

1. Proposal package
   - Expected budget
   - Estimated hours
   - Planned resources
   - Labor rates or team rates
   - Expected timeline
   - Scope assumptions
   - Optional baseline score

2. Actual project data
   - Actual hours
   - Actual billing or balance
   - Actual resource usage
   - Change orders
   - Project status
   - Completion or pause state

3. Optional portfolio data
   - Similar projects
   - Project type comparison
   - Company performance trends
   - Growth and workload patterns

### Core Outputs

1. Project health report
   - Current position
   - Risk level
   - Scorecard
   - Key project insights
   - Recommended actions

2. Project audit report
   - Proposal versus actual comparison
   - Variance analysis
   - Metric-by-metric audit
   - Lessons learned
   - Findings and recommendations

## System Workflow

```mermaid
flowchart TD
    A[Proposal Package] --> B[Expected Project Baseline]
    C[Actual Project Data] --> D[Actual Project State]
    E[Optional Portfolio Data] --> F[Comparison Context]
    B --> G[Data Validation and Normalization]
    D --> G
    F --> G
    G --> H[Audit Engine]
    H --> I[Metric Calculations]
    I --> J[Threshold Review]
    J --> K[Project Health Positioning]
    K --> L[Project Health Report]
    K --> M[Project Audit Report]
```

### Future Prospects

Future versions may include:

- Local dashboard for daily and weekly project review
- PDF or Word report export
- Project similarity analysis
- Estimate accuracy tracking
- Resource workload analysis
- Risk classification using machine learning
- Anomaly detection for unusual hours, billing, or schedule patterns
- Optional local-only report assistance

## Project Ownership

Author and project owner: Syeda M. (smonowar@purdue.edu)