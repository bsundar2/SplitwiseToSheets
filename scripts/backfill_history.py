#!/usr/bin/env python3
"""One-off backfill: re-syncs historical years' Splitwise expenses into the
local database, one year at a time, for cases where the local DB only
reflects the current year (e.g. after a cache reset) and all-time views
like the Monthly Summary sheet lose historical data as a result.

Splitwise itself is always the source of truth and is untouched either
way - this only rebuilds the local mirror from it.

Safe to interrupt and re-run: sync_from_splitwise() is idempotent per year
(inserts/updates by splitwise_id), so a partially-completed backfill just
picks up where it left off.

Usage:
  python scripts/backfill_history.py --start-year 2013 --end-year 2025 --dry-run
  python scripts/backfill_history.py --start-year 2013 --end-year 2025
"""

import argparse
import sys
import time

from src.common.env import load_project_env

load_project_env()

from src.common.utils import LOG
from src.db_sync.sync_from_splitwise import sync_from_splitwise


def run_backfill(
    start_year: int, end_year: int, dry_run: bool = False, delay_seconds: float = 10.0
) -> dict:
    """Syncs each year in [start_year, end_year] in turn.

    A failure on one year is logged and does not stop the remaining years -
    each year is independent, and a failed year can simply be re-run later.

    Returns:
        Dict mapping year -> sync stats dict (or {"error": str} on failure).
    """
    years = list(range(start_year, end_year + 1))
    results = {}

    for i, year in enumerate(years):
        LOG.info("=" * 60)
        LOG.info("Backfilling %d (%d/%d)", year, i + 1, len(years))
        LOG.info("=" * 60)
        try:
            results[year] = sync_from_splitwise(
                start_date=f"{year}-01-01",
                end_date=f"{year}-12-31",
                dry_run=dry_run,
            )
        except Exception as e:
            LOG.exception("Failed to backfill %d: %s", year, e)
            results[year] = {"error": str(e)}

        # Pause between years (not after the last one) so a multi-year
        # backfill doesn't burst the Splitwise API back-to-back.
        if i < len(years) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

    return results


def print_summary(results: dict) -> int:
    """Prints a per-year summary and returns a process exit code."""
    LOG.info("=" * 60)
    LOG.info("Backfill summary")
    LOG.info("=" * 60)

    total_inserted = 0
    total_errors = 0
    failed_years = []
    for year, stats in results.items():
        if "error" in stats:
            LOG.error("  %d: FAILED - %s", year, stats["error"])
            failed_years.append(year)
            continue
        LOG.info(
            "  %d: inserted=%d updated=%d deleted=%d errors=%d",
            year, stats["inserted"], stats["updated"],
            stats["marked_deleted"], stats["errors"],
        )
        total_inserted += stats["inserted"]
        total_errors += stats["errors"]

    LOG.info("-" * 60)
    LOG.info("Total inserted across all years: %d", total_inserted)

    if failed_years:
        LOG.error(
            "Years that failed and should be retried: %s",
            ", ".join(str(y) for y in failed_years),
        )
        return 1
    if total_errors:
        LOG.warning(
            "Completed with %d per-expense error(s) - see log above", total_errors
        )
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical years into the local transactions database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backfill_history.py --start-year 2013 --end-year 2025 --dry-run
  python scripts/backfill_history.py --start-year 2013 --end-year 2025
        """,
    )
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument(
        "--delay-seconds", type=float, default=10.0,
        help="Pause between years to avoid bursting the Splitwise API (default: 10)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing to the database",
    )
    args = parser.parse_args()

    if args.start_year > args.end_year:
        parser.error("--start-year must be <= --end-year")

    results = run_backfill(
        args.start_year, args.end_year, dry_run=args.dry_run,
        delay_seconds=args.delay_seconds,
    )
    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
