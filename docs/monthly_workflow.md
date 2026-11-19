# Monthly Sync Workflow

This guide covers the automated monthly workflow for syncing Splitwise data to Google Sheets. Splitwise syncs linked cards directly, so there are no statements to import.

## Overview

The automated workflow consists of two steps:
1. **Sync** - Pull latest data from Splitwise API to database (updates splits, payments)
2. **Export** - Write filtered transactions from database to Google Sheets

Budget summaries are no longer generated as part of this workflow either - they're computed directly from the raw exported Sheets data; `src/export/generate_summaries.py` (see `docs/budget_summaries_guide.md`) still works standalone if a summary tab is ever needed again.

## Quick Reference

### Recommended: Automated Pipeline

Run sync and export with a single command:

```bash
export PYTHONPATH=$PWD

# Sync and export
python src/export/monthly_export_pipeline.py --year 2026

# Append-only mode (only export unwritten transactions)
python src/export/monthly_export_pipeline.py --year 2026 --append-only

# Dry run to preview
python src/export/monthly_export_pipeline.py --year 2026 --dry-run
```

### Manual Steps (for troubleshooting)

If you need to run steps individually:

```bash
# Step 1: Sync database
python src/db_sync/sync_from_splitwise.py --year 2026 --live

# Step 2: Export to sheets
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --worksheet "Expenses 2026" \
  --overwrite
```

## Workflow Details

### Step 1: Sync Database

**What it does:**
- Fetches latest expense data from Splitwise API
- Compares with local database
- Updates changed transactions (splits, amounts, categories)
- Marks deleted expenses
- Populates payment information (Paid/Owe/With)

**Why this matters:**
- Splitwise is the source of truth for manual edits
- You can fix splits, delete duplicates, change categories in Splitwise
- Sync brings those changes back to the database
- Payment details (who paid, who owes) are only available via API

**Key flags:**
- `--year` - Year to sync
- `--live` - Apply changes (without this, dry run mode)
- `--verbose` - Show detailed comparison output

**What gets updated:**
- Transaction amounts, descriptions, categories
- Split information (is_shared flag, participant names)
- Payment details in notes field
- Deleted status for removed expenses

### Step 2: Export to Sheets

**What it does:**
- Reads transactions from database
- Filters out Payment transactions
- Formats as 12-column export
- Writes to Google Sheets
- Marks transactions as written_to_sheet

**Key flags:**
- `--source database` - Use database as source (recommended)
- `--year` - Filter by year
- `--worksheet` - Target sheet name
- `--overwrite` - Replace all rows (vs append)
- `--dry-run` - Preview without writing

**What gets exported:**
12 columns in this order:
1. Date
2. Amount
3. Category
4. Description
5. Details (cc_reference_id only)
6. Split Type (split/self)
7. Participant Names
8. My Paid
9. My Owed
10. My Net
11. Splitwise ID
12. Transaction Fingerprint

**What gets filtered:**
- Payment transactions (description="Payment" AND category="General")
- Deleted transactions (marked in database)
- Transactions with no user participation

## Common Scenarios

### After Making Manual Edits in Splitwise

If you deleted duplicates, fixed splits, or changed categories in Splitwise:

```bash
python src/export/monthly_export_pipeline.py --year 2026
```

### Incremental Updates (Append-Only Mode)

For ongoing monthly tracking without re-exporting everything:

```bash
# Only export transactions not yet written to sheets
python src/export/monthly_export_pipeline.py --year 2026 --append-only
```

**How it works:**
- Tracks `written_to_sheet` flag in database
- Only exports transactions where `written_to_sheet = False`
- Marks transactions as written after successful export
- Prevents duplicate exports and unnecessary overwrites
- Ideal for mid-month updates or historical month corrections

**When to use:**
- Adding new transactions to an existing month
- After manual Splitwise edits that added/updated transactions
- Incremental updates without full refresh

**When NOT to use:**
- Initial month setup (use overwrite mode)
- Major data cleanup or reformatting
- When you need to re-export everything

### Refreshing Google Sheets

To re-export all data with latest formatting:

```bash
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --worksheet "Expenses 2026" \
  --overwrite
```

## Troubleshooting

### Missing payment information in export

Run the sync script to pull payment details from Splitwise:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

### Transactions show $0 amounts or missing splits

Database is out of sync with Splitwise. Run sync script:

```bash
python src/db_sync/sync_from_splitwise.py --year 2026 --live
```

### Export shows wrong transaction count

Check if Payment transactions are being counted:

```bash
# Preview with dry run
python src/export/splitwise_export.py \
  --source database \
  --year 2026 \
  --dry-run
```

Payment transactions are filtered from sheets but remain in database.

## Best Practices

1. **Always use dry run first** - Preview changes before applying
2. **Edit in Splitwise, sync to DB** - Never edit database directly
3. **Use automated pipeline** - Reduces errors from manual steps
4. **Check export preview** - Verify transaction count before overwriting

## Architecture

```
Splitwise app (linked cards sync directly)
                              ↓
                    [Manual edits/splits in Splitwise]
                              ↓
Database ← Sync ← Splitwise API (updates, deletes)
   ↓
Export (filtered) → Google Sheets
```

**Why this flow:**
- Splitwise = Source of truth for manual edits
- Database = Fast queries, offline access
- Sheets = Filtered view for budget tracking
