# Data Handling Policy

**Real company data stays on your local machine. It is never committed to this repository, never uploaded, and never transmitted anywhere.**

## Folders

| Folder | Contents | In version control? |
|---|---|---|
| `data/sample/` | Synthetic demonstration data only — fictional projects, clients, and numbers | Yes |
| `data/real/` | Your real project data (create this folder locally) | **No — blocked by .gitignore** |

## How the guardrails work

The repository's `.gitignore` enforces three layers of protection:

1. The entire `data/real/` folder is blocked from version control.
2. **All** CSV and Excel files (`.csv`, `.xls`, `.xlsx`, `.xlsm`) are blocked everywhere in the repository, regardless of where they are saved.
3. Only the synthetic samples in `data/sample/` are explicitly allowed back in.

This means even a `git add .` cannot accidentally stage a real data file — anywhere in the project.

## Verify it yourself

From the project root, run:

```
git check-ignore -v data/real/anything.csv
git check-ignore -v some_export.csv
```

Both should print a line pointing at `.gitignore` — that is git confirming the file is blocked. If you ever add genuinely new *synthetic* sample data, save it in `data/sample/` and it will be accepted.
