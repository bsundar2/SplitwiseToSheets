import os
import json

import dateparser
from datetime import datetime, date
import logging
import hashlib
import tempfile
from typing import Union

from src.common.env import load_project_env

# Load environment once
load_project_env()

LOG = logging.getLogger("cc_splitwise")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
LOG.addHandler(handler)
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# Date format constants
DATE_FORMAT = "%Y-%m-%d"


def parse_date_string(date_str: str) -> date:
    """Parse YYYY-MM-DD date string to date object.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        date object

    Raises:
        ValueError: If date_str is not in valid format
    """
    return datetime.strptime(date_str, DATE_FORMAT).date()


def load_state(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def save_state_atomic(path, obj):
    """Write JSON to a temp file then atomically replace the destination."""
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        # If replace failed, try to remove the temp file. Only catch OSError for filesystem ops.
        try:
            os.remove(tmp)
        except OSError:
            # If we can't remove the temp file, log and re-raise the original exception.
            LOG.warning("Failed to remove temp file %s: %s", tmp, e)
        raise


def parse_date(s: str) -> date:
    """Parse a date string and return a datetime.date.

    Raises ValueError if parsing fails. This is a small helper intended for
    callers that want a date object (unlike parse_date_safe which returns an ISO
    string or None).
    """
    if s is None:
        raise ValueError("No date string provided")
    parsed = dateparser.parse(str(s))
    if not parsed:
        raise ValueError(f"Could not parse date: {s}")
    return parsed.date()


def normalize_splitwise_date_to_local(date_str: str) -> str:
    """Normalize Splitwise date/time strings into a local YYYY-MM-DD date.

    Some Splitwise API results include UTC timestamps like
    "2026-04-07T02:35:44Z". Those should be converted to the local calendar
    date before storing/exporting so the sheet matches the user-visible Splitwise
    date.
    """
    if not date_str:
        return date_str

    try:
        parsed = dateparser.parse(str(date_str))
        if parsed is None:
            raise ValueError("Could not parse date")

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()

        return parsed.date().isoformat()
    except Exception:
        normalized = str(date_str)
        if "T" in normalized:
            return normalized.split("T")[0]
        return normalized


def parse_float_safe(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def generate_fingerprint(
    date_val: str, amount_val: Union[str, float], desc_val: str
) -> str:
    """Generate a stable fingerprint for a transaction.

    Args:
        date_val: Date string in any parseable format
        amount_val: Transaction amount (string or float)
        desc_val: Transaction description

    Returns:
        A stable fingerprint string for the transaction
    """
    try:
        # Parse and normalize date
        date_obj = dateparser.parse(str(date_val))
        date_str = date_obj.strftime("%Y-%m-%d") if date_obj else "unknown_date"

        # Normalize amount to 2 decimal places as string
        try:
            amount = float(amount_val)
            amount_str = f"{amount:.2f}"
        except (ValueError, TypeError):
            amount_str = str(amount_val).strip()

        # Normalize description
        desc = (desc_val or "").strip()

        # Create fingerprint
        fingerprint_str = f"{date_str}|{amount_str}|{desc}"
        return hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()
    except Exception as e:
        LOG.error(f"Error generating fingerprint: {e}")
        # Fallback to a less reliable but more robust method
        return hashlib.sha256(
            f"{date_val}|{amount_val}|{desc_val}".encode("utf-8")
        ).hexdigest()
