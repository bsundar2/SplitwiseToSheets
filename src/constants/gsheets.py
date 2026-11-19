import os

# Default worksheet name used by the Google Sheets writer
DEFAULT_WORKSHEET_NAME = "test_expenses"

# Path to service account JSON (resolved relative to this file), or the
# GSHEETS_AUTH_FILE env var - e.g. a Render secret file under /etc/secrets/
SHEETS_AUTHENTICATION_FILE = os.environ.get("GSHEETS_AUTH_FILE") or os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "gsheets_authentication.json"
    )
)

# Worksheet names for summary sheets
WORKSHEET_MONTHLY_SUMMARY = "Monthly Summary"

# Column formatting constants
CURRENCY_COLUMNS = ["B", "H", "I", "J"]  # amount, my_paid, my_owed, my_net
CURRENCY_FORMAT_PATTERN = '"$"#,##0.00'
DATE_FORMAT_PATTERN = "yyyy-mm-dd"
DEFAULT_COLUMN_WIDTH = 200
