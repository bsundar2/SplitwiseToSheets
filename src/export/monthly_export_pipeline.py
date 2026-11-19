#!/usr/bin/env python3
"""Monthly export pipeline - Sync DB, export to sheets.

This pipeline automates the recurring refresh workflow:
1. Sync database with latest Splitwise data
2. Export from database to Google Sheets

There are no statement CSVs to import: Splitwise syncs linked cards
directly.

Budget-summary generation is also no longer wired in - summaries are now
pulled directly from the raw exported data in Sheets instead. `src/export/
generate_summaries.py` still works standalone if a summary tab is ever
needed again.

Usage examples:
  # Sync and export
  python src/export/monthly_export_pipeline.py --year 2026

  # Dry run to preview changes
  python src/export/monthly_export_pipeline.py --year 2026 --dry-run
"""

import argparse
import sys

from src.common.env import load_project_env
from src.common.utils import LOG
from src.db_sync.sync_from_splitwise import sync_from_splitwise
from src.export.splitwise_export import main as export_main

# Load environment variables
load_project_env()

# Pipeline constants
PIPELINE_NAME = "Monthly Export Pipeline"
DEFAULT_WORKSHEET_NAME = "Expense Log"


def run_sync_database(year: int, dry_run: bool = False, verbose: bool = False) -> bool:
    """Run database sync with Splitwise.

    Args:
        year: Year to sync
        dry_run: If True, preview without making changes
        verbose: If True, show detailed output

    Returns:
        True if successful, False otherwise
    """
    LOG.info("=" * 60)
    LOG.info("STEP 1: Sync database with Splitwise")
    LOG.info("=" * 60)

    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    stats = sync_from_splitwise(
        start_date=start_date, end_date=end_date, dry_run=dry_run, verbose=verbose
    )

    LOG.info("✓ Database sync completed successfully")
    LOG.info(
        f"  Updated: {stats['updated']}, Inserted: {stats['inserted']}, Deleted: {stats['marked_deleted']}\n"
    )
    return True


def run_export_to_sheets(
    year: int,
    worksheet_name: str = None,
    dry_run: bool = False,
    append_only: bool = False,
) -> bool:
    """Run export from database to Google Sheets.

    Args:
        year: Year to export
        worksheet_name: Name of worksheet to export to
        dry_run: If True, preview without making changes
        append_only: If True, only export unwritten transactions

    Returns:
        True if successful, False otherwise
    """
    LOG.info("=" * 60)
    LOG.info("STEP 2: Export to Google Sheets")
    LOG.info("=" * 60)

    # Default worksheet name
    if not worksheet_name:
        worksheet_name = DEFAULT_WORKSHEET_NAME

    # Build args for export
    sys.argv = [
        "splitwise_export.py",
        "--source",
        "database",
        "--year",
        str(year),
        "--worksheet",
        worksheet_name,
    ]

    # Add mode flags
    if append_only:
        # Append-only mode: only export unwritten transactions, use append
        sys.argv.append("--append-only")
    else:
        # Default: overwrite mode (full refresh)
        sys.argv.append("--overwrite")

    if dry_run:
        sys.argv.append("--dry-run")

    result = export_main()
    if result == 0:
        LOG.info("✓ Export to sheets completed successfully\n")
        return True
    else:
        LOG.error("✗ Export to sheets failed\n")
        return False


def main():
    """Main entry point for the pipeline."""
    parser = argparse.ArgumentParser(
        description="Monthly export pipeline - Sync database and export to sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync and export
  python src/export/monthly_export_pipeline.py --year 2026

  # Dry run to preview all changes
  python src/export/monthly_export_pipeline.py --year 2026 --dry-run
        """,
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Year for sync and export (e.g., 2026)",
    )
    parser.add_argument(
        "--worksheet",
        help=f"Worksheet name for export (default: {DEFAULT_WORKSHEET_NAME})",
    )
    parser.add_argument(
        "--append-only",
        action="store_true",
        help="Export only unwritten transactions (tracks written_to_sheet flag)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    # Print pipeline header
    print("\n" + "=" * 60)
    print(f"{PIPELINE_NAME}")
    print("=" * 60)
    print(f"Year: {args.year}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.append_only:
        print("Export mode: Append-only (unwritten transactions only)")
    else:
        print("Export mode: Overwrite (full refresh)")
    print("=" * 60 + "\n")

    total_steps = 2
    success_count = 0

    # Step 1: Sync database
    if run_sync_database(args.year, args.dry_run, args.verbose):
        success_count += 1
    else:
        LOG.error("Pipeline failed at database sync step")
        return 1

    # Step 2: Export to sheets
    if run_export_to_sheets(args.year, args.worksheet, args.dry_run, args.append_only):
        success_count += 1
    else:
        LOG.error("Pipeline failed at export step")
        return 1

    # Final summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Completed {success_count}/{total_steps} steps successfully")
    if args.dry_run:
        print("(DRY RUN - No changes were made)")
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
