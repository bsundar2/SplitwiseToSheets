import pytest
from unittest.mock import patch
import sys
from src.export.monthly_export_pipeline import (
    run_sync_database,
    run_export_to_sheets,
    main,
)

@patch("src.export.monthly_export_pipeline.sync_from_splitwise")
def test_run_sync_database(mock_sync):
    mock_sync.return_value = {"updated": 1, "inserted": 2, "marked_deleted": 0}
    assert run_sync_database(2026) is True
    mock_sync.assert_called_once()

@patch("src.export.monthly_export_pipeline.export_main")
def test_run_export_to_sheets(mock_export):
    mock_export.return_value = 0
    assert run_export_to_sheets(2026) is True
    assert "--overwrite" in sys.argv

    assert run_export_to_sheets(2026, append_only=True) is True
    assert "--append-only" in sys.argv

@patch("src.export.monthly_export_pipeline.run_sync_database")
@patch("src.export.monthly_export_pipeline.run_export_to_sheets")
def test_main_sync_and_export(mock_export, mock_sync):
    mock_sync.return_value = True
    mock_export.return_value = True

    with patch("sys.argv", ["script", "--year", "2026"]):
        assert main() == 0
        mock_sync.assert_called_once()
        mock_export.assert_called_once()


@patch("src.export.monthly_export_pipeline.run_sync_database")
@patch("src.export.monthly_export_pipeline.run_export_to_sheets")
def test_main_reports_correct_step_count(mock_export, mock_sync, capsys):
    mock_sync.return_value = True
    mock_export.return_value = True

    with patch("sys.argv", ["script", "--year", "2026"]):
        assert main() == 0

    out = capsys.readouterr().out
    assert "Completed 2/2 steps successfully" in out


@patch("src.export.monthly_export_pipeline.run_sync_database")
@patch("src.export.monthly_export_pipeline.run_export_to_sheets")
def test_main_stops_on_sync_failure(mock_export, mock_sync):
    mock_sync.return_value = False

    with patch("sys.argv", ["script", "--year", "2026"]):
        assert main() == 1
        mock_export.assert_not_called()


def test_main_requires_year():
    with patch("sys.argv", ["script"]):
        with pytest.raises(SystemExit):
            main()
