# SplitwiseToSheets

Keeps a Google Sheets copy of your Splitwise expenses for budget tracking: a scheduled GitHub Action syncs Splitwise into a local SQLite mirror and exports each year's expenses to a sheet, and a marimo dashboard charts your spending.

## Project Overview

**Architecture:**
- **Splitwise** = Source of Truth (Manual edits & split management)
- **Local SQLite Database** = Synced Mirror (Fast queries & historical archiving)
- **Google Sheets** = Viewing Layer (Formatted exports & spending analysis)

## Core Features

- **Automated Sync**: A scheduled GitHub Action syncs Splitwise to the local database and Google Sheets three times a day.
- **Bulk Category Updates**: Re-categorize existing Splitwise expenses by merchant or current category.
- **Budget Analysis**: Detailed monthly summaries, category breakdowns, and year-over-year trends in Google Sheets.
- **Interactive Spending Dashboard**: A local marimo app with category/merchant breakdowns, monthly & weekly trends, and recurring-charge (subscription) detection.
- **Historical Archiving**: Complete transaction history stored locally in SQLite.
- **Year-Based Exporting**: Clean, structured spreadsheets with separate tabs for each year.
- **Idempotent Updates**: Smart syncing ensures no duplicate entries and minimal API/Sheet writes.

## Setup
1. Create a virtual environment: `python -m venv .venv`
2. Activate the environment: `source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure environment variables:
   - Copy the template: `cp config/.env.example config/.env`
   - Open `config/.env` and add your API keys and configuration (see Environment Variables section below)
5. Set up Google Sheets access:
   - Place your service account JSON file at `config/gsheets_authentication.json`
   - Share your spreadsheet with the service account email address
6. Set PYTHONPATH: `export PYTHONPATH=$PWD`

## Quick Start

### Recommended: Monthly Export Pipeline

The **Monthly Export Pipeline** is the primary, automated tool for keeping things current. It syncs the local database with Splitwise and exports to Google Sheets in one command. Splitwise syncs linked cards directly, so there are no statements to import. Budget summaries are also no longer generated here - they're pulled directly from the raw exported data in Sheets instead; `src/export/generate_summaries.py` (see `docs/budget_summaries_guide.md`) still works standalone if a summary tab is ever needed again.

```bash
# 1. Activate venv and set PYTHONPATH
source .venv/bin/activate
export PYTHONPATH=$PWD

# 2. Run the pipeline
# This syncs DB → Exports to Sheets
python src/export/monthly_export_pipeline.py --year 2026
```

**What it does:**
1. **Syncs database** with latest Splitwise data.
2. **Exports to Google Sheets** (default: `Expense Log` worksheet).

#### Append Only Mode
By default, the pipeline overwrites the worksheet for a full refresh. Use `--append-only` to only add transactions that haven't been written to the sheet yet.

```bash
# Append-only export
python src/export/monthly_export_pipeline.py --year 2026 --append-only
```

#### Dry Run
Always run with `--dry-run` first to preview changes.

```bash
python src/export/monthly_export_pipeline.py --year 2026 --dry-run
```

### Export Options

Export from Splitwise API or database to Google Sheets:

```bash
# Export from database (recommended - faster, filtered)
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --worksheet "Expenses 2026" \
  --overwrite

# Export from Splitwise API (live data)
python src/export/splitwise_export.py \
  --source splitwise \
  --start-date 2026-01-01 \
  --end-date 2026-12-31 \
  --worksheet "Expenses 2026" \
  --overwrite

# Dry run to preview
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --dry-run
```

**Export features:**
- 12 columns: Date, Amount, Category, Description, Details (cc_ref), Split Type, Participant Names, My Paid, My Owed, My Net, Splitwise ID, Fingerprint
- Filters Payment transactions (excluded from sheets but tracked in DB)
- Overwrite mode for full refresh or default append mode


### Bulk Category Updates

Update categories for existing Splitwise expenses in bulk by merchant name or current category:

```bash
# Update all SpotHero expenses to Transportation > Parking
python src/update/bulk_update_categories.py --merchant "SpotHero" --subcategory parking

# Update Amazon (excluding AWS) to Household supplies
python src/update/bulk_update_categories.py --merchant "Amazon" --exclude "AWS" --subcategory household_supplies

# Update Costco expenses currently in "Home - Other" to Household supplies
python src/update/bulk_update_categories.py --merchant "Costco" --current-category "Home - Other" --subcategory-id 14

# Dry run to preview changes
python src/update/bulk_update_categories.py --merchant "SpotHero" --subcategory parking --dry-run

# Skip confirmation prompt
python src/update/bulk_update_categories.py --merchant "Costco" --subcategory household_supplies --yes
```

**Common Subcategory Options:**
- `parking` (ID: 9) - Transportation > Parking
- `household_supplies` (ID: 14) - Home > Household supplies
- `home_other` (ID: 28) - Home > Other
- `medical` (ID: 38) - Life > Medical expenses
- `groceries` (ID: 1) - Food and drink > Groceries
- `dining_out` (ID: 2) - Food and drink > Dining out

See `src/constants/splitwise.py` (SUBCATEGORY_IDS) for the full list of available subcategories.

Or use `--subcategory-id` with any Splitwise subcategory ID.


## Project Structure

```
SplitwiseToSheets/
├── src/
│   ├── database/               # Local SQLite database layer
│   │   ├── schema.py           # Table definitions (transactions, monthly_summaries, etc.)
│   │   ├── models.py           # Transaction dataclass
│   │   └── db_manager.py       # DatabaseManager with CRUD + summary methods
│   ├── db_sync/                # Database sync utilities
│   │   └── sync_from_splitwise.py # Sync DB with Splitwise (insert/update/delete)
│   ├── export/                 # Splitwise data export and summaries
│   │   ├── splitwise_export.py # Fetch and export Splitwise expenses
│   │   ├── monthly_export_pipeline.py # Automated 2-step pipeline (sync, export)
│   │   └── generate_summaries.py # Budget analysis and spending summaries
│   ├── analytics/               # Interactive spending analytics
│   │   ├── spending_analytics.py  # Category/merchant/trend/recurring calculations
│   │   └── spending_dashboard.py  # marimo dashboard built on the above
│   ├── update/                 # Bulk update utilities
│   │   ├── update_self_expenses.py # Fix self-expense splits
│   │   └── bulk_update_categories.py # Bulk category updates
│   ├── common/                 # Shared utilities
│   │   ├── splitwise_client.py # Splitwise API wrapper
│   │   ├── sheets_sync.py      # Google Sheets integration
│   │   └── utils.py            # Common helper functions
│   └── constants/              # Configuration constants
├── config/                     # Credentials and mappings
│   ├── .env                    # API keys (not in git)
│   ├── splitwise_category_ids.json    # Splitwise category/subcategory ids
│   └── gsheets_authentication.json    # Google Sheets credentials (not in git)
├── data/
│   └── transactions.db         # SQLite database (not in git)
└── docs/                       # Documentation
```


## Common Workflows

### Monthly Expense Processing Pipeline

The **Monthly Export Pipeline** is the recommended way to keep things current, since it ensures syncing and exporting are performed in the correct order.

```bash
python src/export/monthly_export_pipeline.py --year 2026
```

**Why the pipeline matters:**
- **Order of Operations**: It syncs Splitwise data before exporting, so the export reflects the latest splits/categories/deletions.
- **Chronological Sorting**: It uses `--overwrite` by default for exports, which re-sorts all expenses chronologically in Google Sheets.
- **Automation**: It combines 2 manual steps into a single idempotent command.

### Monthly Budget Sync
```bash
# Export current month's Splitwise expenses
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-01-31 --sheet-name "Jan 2025"

# Full year export with categories
python src/export/splitwise_export.py --start-date 2025-01-01 --end-date 2025-12-31 --overwrite --export-categories
```

## Configuration Files

### Environment Variables (.env)
Required API credentials and default settings:

```env
# Splitwise API
SPLITWISE_CONSUMER_KEY=your_key_here
SPLITWISE_CONSUMER_SECRET=your_secret_here
SPLITWISE_API_KEY=your_api_key_here

# Splitwise User IDs (Get these from your Splitwise profile or API)
SPLITWISE_SELF_ID=your_self_user_id_here
SPLITWISE_PARTNER_ID=your_partner_user_id_here

# Google Sheets
SPREADSHEET_KEY=your_google_sheets_key

# Default date range and worksheet (change for new year)
START_DATE=2026-01-01
END_DATE=2026-12-31
EXPENSES_WORKSHEET_NAME=Expenses 2026
```

**Note:** Update `START_DATE`, `END_DATE`, and `EXPENSES_WORKSHEET_NAME` at the start of each year to automatically target the new year's data.

## Running it on GitHub Actions

Fork or copy this repo, then add these under **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Value |
|---|---|
| `SPLITWISE_CONSUMER_KEY`, `SPLITWISE_CONSUMER_SECRET`, `SPLITWISE_API_KEY` | Your Splitwise app's credentials |
| `SPLITWISE_SELF_ID`, `SPLITWISE_PARTNER_ID` | Your and your partner's Splitwise user ids |
| `SPREADSHEET_KEY` | The budget spreadsheet's key (from its URL) |
| `GSHEETS_AUTH_JSON` | The service account JSON, pasted whole |
| `DB_CACHE_KEY` | Any long random string, e.g. from `openssl rand -base64 32` |

`splitwise-sync.yml` then runs three times a day. It keeps the SQLite database between runs in the Actions cache, encrypted with `DB_CACHE_KEY` (`scripts/ci/db_cache.sh`), because a public repo's caches can be restored by workflow runs from forks' pull requests, which never receive secrets. Changing the key makes the cached copy unreadable: the run fails until you delete the cache (**Actions → Caches**) and run the backfill below. To be safe, also set **Settings → Actions → General → Fork pull request workflows** to require approval for all external contributors.

GitHub turns off a public repo's scheduled workflows after 60 days without activity, so `keepalive.yml` re-enables them once a month.

## Backfilling historical years

The Monthly Export Pipeline only ever syncs the *current* year's date range into the local database - by design, since re-syncing the full multi-year history on every run would be slow and API-heavy. If the cached local database ever ends up reflecting only the current year (e.g. after a GitHub Actions cache reset or eviction), all-time views built from the exported Sheets data will silently lose prior years' data, even though Splitwise itself - the actual source of truth - is completely unaffected.

To rebuild the local mirror's history, dispatch the **Backfill Historical Years** workflow (`.github/workflows/backfill-history.yml`) with a year range, e.g. `start_year=2013 end_year=2025`. It re-syncs one year at a time (idempotent - inserts/updates by `splitwise_id`, safe to interrupt and re-run), with a pause between years (`delay_seconds`, default 10) to avoid bursting the Splitwise API across a large range. A failure on one year doesn't stop the rest - failed years are reported at the end so they can be retried individually. `dry_run` defaults to `true` to preview counts first.

Can also be run directly: `python scripts/backfill_history.py --start-year 2013 --end-year 2025 [--dry-run] [--delay-seconds 10]`.

## Interactive Spending Analytics Dashboard

A local [marimo](https://marimo.io) app for exploring spending patterns beyond what lives in the exported Google Sheet - it reads directly from the local `data/transactions.db` (whatever the sync pipeline last populated), so it's always in sync with the sheet without needing its own upload step.

```bash
marimo run src/analytics/spending_dashboard.py
```

Filter by year and category, search by merchant, then use the "Reload from database" button to pick up changes after re-running the sync pipeline. It shows:

- **Category & merchant breakdown** - where your share of spend (post-split) actually goes.
- **Merchant search** - a "Matching Transactions" list of every transaction (within the current year/category filter) whose merchant matches a typed search term, separate from the aggregate breakdowns above.
- **Monthly & weekly trends** - spend over time, with month-over-month and year-over-year % change surfaced in both the chart tooltips and a "vs Last Year" KPI for the most recent month that has one.
- **What changed vs. last month** - which categories moved the most (up or down) between the two most recent calendar months in view.
- **Spending pace** - a linear year-end projection ("at this rate, ~$X by Dec 31") based on the current calendar year's spend-to-date, shown regardless of the year/category filter.
- **Shared vs. personal spend** - how much of spend was on Splitwise-shared expenses vs. solo (non-split) ones.
- **Biggest transactions** - the largest individual purchases in the current filter.
- **Recurring charges** - merchants billing a similar amount on a monthly, quarterly, or annual cadence, as a proxy for subscriptions worth reviewing. Merchant names are matched case/whitespace-insensitively (not fuzzy - a real rename, like Splitwise's own "Fastrak Csc Tolls" → "FasTrak", still won't merge), and a single price change (e.g. a subscription price increase) doesn't disqualify a merchant - the estimated cost shown reflects the current price, not a blend of old and new.
- **Spend concentration** - what share of total spend the top merchants account for.
- **Budget vs. actual** - this month's spend against a per-category monthly target, for the most recent month in view.

The underlying calculations live in `src/analytics/spending_analytics.py` and are unit-tested (`tests/test_spending_analytics.py`); the dashboard cells themselves are a thin rendering layer on top and aren't covered by the test suite, mirroring the split used by the `pnl_tracker.py` / `pnl_calculator.py` dashboard in the sibling RobinhoodToSheets repo.

### Budget targets (optional)

Budget-vs-actual reads per-category monthly targets from the `CATEGORY_BUDGETS` env var - a static JSON object of `category name -> monthly $ amount`, e.g. `{"Food and drink": 700, "Travel": 300}` (see `config/.env.example`). Amounts can be a plain number or a currency-formatted string ("$700.00"). Category name matching is case/whitespace-insensitive (`" travel "` matches a real category recorded as `"Travel"`), since a hand-typed config is more typo-prone than the category names already flowing through the DB - the displayed name prefers the real transaction data's own casing. `python scripts/print_category_budgets_template.py` prints every category currently in your local DB as a ready-to-fill-in JSON template (`{"Category": 0, ...}`) so you don't have to guess or copy names by hand. No local DB or Splitwise credentials handy? The "Print Category Budgets Template" GitHub Action (`.github/workflows/print_category_budgets.yml`, manually dispatched) does a bounded live resync of the last 2 years from Splitwise (uncheck `sync_first` to skip it and use whatever's already cached) and posts the same template to the run's summary page - copy it from there instead.

`load_category_budgets()` in `spending_analytics.py` is entirely optional and silently no-ops (section hidden, no error) when `CATEGORY_BUDGETS` isn't set - same graceful-absence pattern as the Render resync. If it's set but isn't valid JSON (or isn't a JSON object), the section shows the parse error instead of crashing, and the header badge switches to "⚠ BUDGET CONFIG INVALID". These are meant to be static numbers set once and rarely touched, so there's no live Sheets/network dependency involved at all - just a restart (locally, or a Render redeploy) to pick up an edited value, since env vars are only read at process startup.

The dashboard's dark theme is styled in its own `<style>` block, but marimo also has its own separate light/dark theme controlling the app shell and native widgets (dropdown, multiselect, button) - without matching it, marimo's own chrome stays light regardless of the page's custom CSS, showing as white gaps around/between the dashboard's sections. `.marimo.toml` at the repo root (`[display]` / `theme = "dark"`) sets marimo's own theme to match.

### Hosting it on Render (optional)

`render.yaml` defines a free-tier Render web service (`spending-dashboard`) that runs the dashboard continuously at a URL, instead of you running `marimo run` locally each time - the same pattern the sibling RobinhoodToSheets repo uses to host `pnl_tracker.py`.

Unlike `pnl_tracker.py` (which takes a fresh CSV upload every visit, so it needs no server-side data), this dashboard reads a local SQLite file, and Render's free tier wipes a service's disk on every idle-timeout wake - so the deployed app resyncs itself from Splitwise before each load. That resync is intentionally bounded to the last 3 years (`sync_recent_years_if_on_render()` in `spending_analytics.py`) and isn't user-configurable, to keep cold starts fast and API usage low; it's a no-op when run locally (gated on Render's own `RENDER=true` env var, set automatically on every Render service). If the sync fails (e.g. a transient Splitwise API issue), the dashboard falls back to whatever's already in the local DB and shows a "⚠ SYNC FAILED" badge rather than crashing.

To deploy: connect the repo in the Render dashboard (it picks up `render.yaml` automatically), then set `MARIMO_TOKEN`, the `SPLITWISE_*` secrets (same values as your `config/.env`), and optionally `CATEGORY_BUDGETS` as environment variables on the service - they're marked `sync: false` in `render.yaml` so Render prompts for them rather than expecting them in the file.

#### Reading the Expense Log instead of resyncing (optional)

Set `EXPENSE_LOG_SPREADSHEET_KEYS` to the key of the budget spreadsheet the scheduled export writes to (the same value as the `SPREADSHEET_KEY` secret), and upload `config/gsheets_authentication.json` as a Render Secret File named `gsheets_authentication.json` (`GSHEETS_AUTH_FILE` in `render.yaml` points at it; the spreadsheet must be shared with that service account). The dashboard then reads the "Expense Log" tab (`load_dashboard_transactions()` in `spending_analytics.py`) instead of resyncing from Splitwise, so a cold start takes seconds instead of minutes. The badge reads "BUDGET SHEET", and "Reload data" re-reads the tab. List several keys, comma-separated, to combine years; an expense in more than one is counted once (by Splitwise ID).

What changes with this source:
- **Freshness**: the tab is rewritten three times a day by `splitwise-sync.yml` (05:17, 13:17 and 21:17 UTC), so an expense added in Splitwise shows up after the next run (or a manual run of that workflow).
- **History**: each budget spreadsheet's Expense Log holds one year, so the years before this one (out of the same 2-year window as the resync) are synced from Splitwise in a background thread (`start_history_sync()`, once per container, using the `SPLITWISE_*` secrets) while the page shows this year. The badge reads "BUDGET SHEET · LOADING EARLIER YEARS" until they arrive, then the page updates itself (a `mo.Thread` sets marimo state, which re-runs the cells that read it), resetting the year/category filters. If that sync fails, the badge reads "⚠ THIS YEAR ONLY" and the page keeps working with the sheet's data. Locally nothing is synced; earlier years come from the local DB as is.
- **Same numbers as the budget sheet**: the tab only holds expenses you're part of, and refunds detected from the description ("refund", "credit", "return") are negative, matching what the budget's Monthly Expenses formulas total.

Unset, the dashboard resyncs from Splitwise as described above.

## Tips & Best Practices

- **Always set PYTHONPATH** before running commands: `export PYTHONPATH=$PWD`
- **Use dry-run first** to preview changes before writing to Splitwise or Sheets
- **Use --overwrite for exports** to get a clean dataset with deleted transactions filtered out
- **Check logs** in terminal output for detailed processing information
- **Update config/.env dates** at the start of each year (START_DATE, END_DATE, EXPENSES_WORKSHEET_NAME)

## Automation Considerations

**Implemented:**
- GitHub Actions scheduled execution (three times a day - see "Running it on GitHub Actions" above): syncs the database from Splitwise and exports to Google Sheets. Budget summaries are computed directly from that raw exported data rather than a separate generated tab.

**Future enhancements:**
- Email/Slack notifications on completion or errors

## Troubleshooting

**Import fails with "ModuleNotFoundError"**: Set PYTHONPATH to project root (e.g., `export PYTHONPATH=$PWD`)  
**Wrong categories**: Fix them in Splitwise (or with `bulk_update_categories.py`), then re-run the export with `--overwrite`  
**Deleted expenses appearing**: Use `--overwrite` flag when exporting to filter them out  
**Date mismatch (one day off)**: Fixed in export - dates no longer use UTC conversion  
**Category updates not reflected**: Run export with `--overwrite` after bulk updates  
**Wrong year data**: Update `START_DATE`, `END_DATE`, and `EXPENSES_WORKSHEET_NAME` in `config/.env`


