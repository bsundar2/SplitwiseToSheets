from unittest.mock import patch, call

from scripts.backfill_history import run_backfill, print_summary


@patch("scripts.backfill_history.time.sleep")
@patch("scripts.backfill_history.sync_from_splitwise")
def test_run_backfill_syncs_each_year_with_delay_between(mock_sync, mock_sleep):
    mock_sync.return_value = {
        "checked": 5, "inserted": 3, "updated": 1,
        "marked_deleted": 0, "unchanged": 1, "errors": 0,
    }

    results = run_backfill(2023, 2025, dry_run=False, delay_seconds=10.0)

    assert list(results.keys()) == [2023, 2024, 2025]
    assert mock_sync.call_count == 3
    mock_sync.assert_any_call(start_date="2023-01-01", end_date="2023-12-31", dry_run=False)
    mock_sync.assert_any_call(start_date="2024-01-01", end_date="2024-12-31", dry_run=False)
    mock_sync.assert_any_call(start_date="2025-01-01", end_date="2025-12-31", dry_run=False)

    # Delay happens between years, not after the last one.
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([call(10.0), call(10.0)])


@patch("scripts.backfill_history.time.sleep")
@patch("scripts.backfill_history.sync_from_splitwise")
def test_run_backfill_single_year_has_no_delay(mock_sync, mock_sleep):
    mock_sync.return_value = {
        "checked": 1, "inserted": 1, "updated": 0,
        "marked_deleted": 0, "unchanged": 0, "errors": 0,
    }

    run_backfill(2024, 2024, delay_seconds=10.0)

    mock_sleep.assert_not_called()


@patch("scripts.backfill_history.time.sleep")
@patch("scripts.backfill_history.sync_from_splitwise")
def test_run_backfill_one_year_failing_does_not_stop_others(mock_sync, mock_sleep):
    # A rate-limit or API failure on one year must not abort the rest -
    # each year is independent and can be retried on its own later.
    def side_effect(start_date, end_date, dry_run):
        if start_date.startswith("2024"):
            raise RuntimeError("Splitwise API circuit breaker is open")
        return {"checked": 1, "inserted": 1, "updated": 0, "marked_deleted": 0, "unchanged": 0, "errors": 0}

    mock_sync.side_effect = side_effect

    results = run_backfill(2023, 2025, delay_seconds=0)

    assert mock_sync.call_count == 3
    assert "error" in results[2024]
    assert "inserted" in results[2023]
    assert "inserted" in results[2025]


def test_print_summary_returns_zero_on_full_success():
    results = {
        2023: {"checked": 5, "inserted": 3, "updated": 1, "marked_deleted": 0, "unchanged": 1, "errors": 0},
        2024: {"checked": 2, "inserted": 2, "updated": 0, "marked_deleted": 0, "unchanged": 0, "errors": 0},
    }
    assert print_summary(results) == 0


def test_print_summary_returns_one_on_any_failed_year():
    results = {
        2023: {"checked": 5, "inserted": 3, "updated": 1, "marked_deleted": 0, "unchanged": 1, "errors": 0},
        2024: {"error": "Splitwise API circuit breaker is open"},
    }
    assert print_summary(results) == 1


def test_print_summary_returns_zero_with_per_expense_errors_but_no_failed_years():
    # A year that completed (didn't raise) but logged some per-expense parse
    # errors should still be treated as a success at the year level - the
    # errors are already visible in the per-year log line.
    results = {
        2023: {"checked": 5, "inserted": 3, "updated": 1, "marked_deleted": 0, "unchanged": 1, "errors": 2},
    }
    assert print_summary(results) == 0
