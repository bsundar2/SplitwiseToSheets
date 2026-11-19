# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

SplitwiseToSheets keeps a Google Sheets copy of Splitwise expenses for budget tracking.

- **Splitwise** is the source of truth. Linked cards sync into it directly, and splits and categories are edited there.
- **A local SQLite database** (`data/transactions.db`, not in git) mirrors it.
- **Google Sheets** is the view: one `Expense Log` tab per budget sheet, read by the budget's formulas.

## Layout

```
src/
├── db_sync/sync_from_splitwise.py   # Splitwise -> SQLite (insert/update/delete)
├── export/
│   ├── monthly_export_pipeline.py   # Sync, then export (what the scheduled workflow runs)
│   ├── splitwise_export.py          # SQLite or Splitwise -> Google Sheets
│   └── generate_summaries.py        # Standalone budget-summary tab (not scheduled)
├── analytics/
│   ├── spending_analytics.py        # Tested calculations for the dashboard
│   └── spending_dashboard.py        # marimo dashboard (hosted on Render, see render.yaml)
├── update/                          # One-off bulk edits of existing Splitwise expenses
├── database/                        # schema.py, models.py, db_manager.py
├── common/                          # Splitwise client, Sheets helpers, env loading, filters
└── constants/                       # Column names, sheet names, Splitwise ids and split types
scripts/
├── backfill_history.py              # Re-sync past years into SQLite
├── print_category_budgets_template.py
└── ci/db_cache.sh                   # Encrypts/decrypts the cached database in workflows
config/
├── .env.example                     # Copy to config/.env (gitignored)
└── splitwise_category_ids.json      # Splitwise category/subcategory ids
```

## Workflows (`.github/workflows/`)

- `splitwise-sync.yml`: three times a day, runs `monthly_export_pipeline.py` for the current year. The SQLite database is kept between runs in the Actions cache, encrypted with the `DB_CACHE_KEY` secret by `scripts/ci/db_cache.sh`. Only ever cache the `.enc` file: the repo is public, and fork pull requests can restore caches but never get secrets.
- `backfill-history.yml`: re-syncs historical years into that cached database. Run it manually.
- `print_category_budgets.yml`: prints a `CATEGORY_BUDGETS` template from the category names in your data.
- `python-tests.yml`: runs `pytest` on pushes and PRs.
- `keepalive.yml`: once a month, re-enables the scheduled workflows, which GitHub disables after 60 days without repo activity. A new scheduled workflow goes in its list.

## Commands

```bash
source .venv/bin/activate
export PYTHONPATH=$PWD
python src/export/monthly_export_pipeline.py --year 2026 --dry-run   # preview
python src/export/monthly_export_pipeline.py --year 2026             # sync + export
marimo run src/analytics/spending_dashboard.py                      # dashboard
pytest                                                              # tests
```

## Conventions

- **Virtualenv:** activate it before running Python or installing packages.
- **Imports:** set `PYTHONPATH` to the project root so `src.` imports resolve.
- **Style:** follow `.github/coding_style.md`.
- **Tests:** they mock Splitwise and Google Sheets, so no credentials are needed.
- **Personal data stays out of the repo.** Credentials, spreadsheet keys, Splitwise user ids and budgets come from `config/.env` locally, or repo secrets in Actions. Don't commit real transactions, names or account details. Test data must be made up.
- **Logs:** keep merchant names and amounts out of workflow logs, since Actions logs are visible to anyone who can see the repo.
- **VS Code:** `.vscode/launch.json` passes `config/.env` as `envFile`. Don't put `${env:VAR}` in `args`, because VS Code substitutes an empty string when the variable isn't already in its own environment.
