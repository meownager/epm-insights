# epm-insights

epm-insights is a project audit and analysis system for Engineering Program/Project Managers. It compares what a project promised (the proposal baseline) against what actually happened, classifies each completed project's health as Green / Yellow / Red, and produces traceable, criteria-driven audit reports — all locally on your machine. No data ever leaves your computer.

## What It Does

- **Audit engine** — computes budget, hours, schedule, and resource deviations for completed projects against their proposal baselines
- **Health classification** — advisory Green / Yellow / Red status based on versioned thresholds in the Audit Criteria Register (`config/audit_criteria.yaml`), with separate budget tolerances for fixed-fee and T&E projects
- **Run records** — every audit run produces a JSON record with a run ID, timestamp, criteria version, and SHA-256 fingerprints of the input files, so any result can be reproduced and traced
- **HTML reports** — downloadable, self-contained audit reports you can open, print, or share
- **Interactive dashboard** — charts, filters, and a color-coded project table in your browser
- **Insights** — automated pattern findings (margin exposure, scope growth without change orders, EPM and client concentrations) and a closeout-notes similarity search

## Supported Runtime Matrix

- **Supported Python versions:** 3.11, 3.12
- **Supported operating systems:** Linux, macOS, Windows
- **Known-good dependency set:** pinned in `/home/runner/work/epm-insights/epm-insights/requirements.txt`

## Canonical Bootstrap (clean machine)

Use this exact setup path for reproducible local runs:

1. Download this repository (green **Code** button → Download ZIP, then extract) or clone it:

   ```
   git clone https://github.com/meownager/epm-insights.git
   cd epm-insights
   ```

2. Create and activate a virtual environment:

   **macOS/Linux**
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell)**
   ```
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install pinned dependencies:

   ```
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. Verify the environment:

   ```
   python -m pytest tests/ -v
   ```

5. Launch the dashboard:

   ```
   streamlit run dashboard.py
   ```

Your browser opens automatically. Click **Run Audit** in the sidebar — default paths point to included synthetic sample data.

## Using Your Own (Real) Project Data

1. Create a folder called `data/real/` inside the project. **This folder is git-ignored — files inside it can never be accidentally committed or uploaded.**
2. Prepare two CSV files matching the column layout of the samples in `data/sample/`:
   - `proposal_projects.csv` — one row per project: proposed budget, hours, dates, resource count, billing type (`fixed_fee` or `t_and_e`)
   - `actual_projects.csv` — one row per project: actual budget, hours, dates, status, closeout notes
3. In the dashboard sidebar, change the two file paths to point at your files and click **Run Audit**.

All processing happens on your machine. Nothing is transmitted anywhere.

## Command-Line Usage (without the dashboard)

```
python scripts/completed_project_health.py --proposal data/sample/proposal_projects.csv --actual data/sample/actual_projects.csv --output-dir outputs

python scripts/generate_html_report.py --detail outputs/completed_project_health_detail.csv --run-record "outputs/runs/run_*.json" --output outputs/audit_report.html
```

You can print startup/runtime diagnostics without running an audit:

```
python scripts/completed_project_health.py --proposal data/sample/proposal_projects.csv --actual data/sample/actual_projects.csv --diagnostics-only
```

## How Health Is Classified

Thresholds live in one place: `config/audit_criteria.yaml` (the Audit Criteria Register). Every change to a threshold increments the register version and records a reason. Reports state the criteria version that produced them.

| Metric | Fixed Fee Green | Fixed Fee Yellow | T&E Green | T&E Yellow |
|---|---|---|---|---|
| Budget deviation | ≤ 15% | ≤ 30% | ≤ 25% | ≤ 40% |
| Hours deviation | ≤ 15% | ≤ 30% | ≤ 15% | ≤ 30% |
| Schedule slip | ≤ 7 days | ≤ 21 days | ≤ 7 days | ≤ 21 days |

A project is Green only if **all** metrics are within the Green band; one metric in the Yellow band makes it Yellow; one metric beyond Yellow makes it Red. Classifications are advisory — they flag projects for review, they do not assign blame.

## Quality Framework

The audit process itself is documented and controlled. See `docs/quality-framework/` for the audit charter, roles, criteria management process, document control, defined process steps, calibration cycle, findings log, and external audit alignment map.

## Running the Tests

```
python -m pytest tests/ -v
```

Every deviation formula and classification boundary has a known-answer test.

## Optional Local AI Features (not required)

- Core audit metrics, thresholds, and health classifications are fully local and deterministic without AI.
- Optional narrative generation depends on a locally running Ollama service (`http://localhost:11434`) and an installed model.
- If Ollama is not installed or running, only the optional narrative layer is unavailable; core audit outputs still run normally.

## Reproducibility Bundle

Generate a repeatable sample bundle with pinned dependencies, run artifacts, and SHA-256 fingerprints:

```
python scripts/build_repro_bundle.py --output-dir outputs/repro
```

## Project Principles

- Real company data stays private and protected — only synthetic data is committed to this repository
- All processing is local; no data leaves the machine; no required network calls
- Built with free and open-source tools
- Audit logic is transparent and explainable — no black boxes in the numbers
- AI features are additive only: they can explain and summarize, but can never change a metric or a health classification

## Project Ownership

Author and project owner: Syeda M. (smonowar@purdue.edu)
