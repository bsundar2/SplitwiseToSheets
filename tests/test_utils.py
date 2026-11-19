"""Additional utils tests to boost coverage for uncovered functions/branches."""
import pytest
from datetime import date
import dateparser

from src.common.utils import (
    parse_date_string,
    load_state,
    save_state_atomic,
    parse_date,
    normalize_splitwise_date_to_local,
    parse_float_safe,
    generate_fingerprint,
)

# === parse_date_string ===
def test_parse_date_string():
    assert parse_date_string("2026-04-01") == date(2026, 4, 1)
    with pytest.raises(ValueError):
        parse_date_string("invalid")


# === load_state / save_state_atomic ===
def test_load_state_missing():
    assert load_state("/nonexistent/path.json") == {}

def test_save_and_load_state(tmp_path):
    path = str(tmp_path / "state.json")
    save_state_atomic(path, {"key": "value"})
    state = load_state(path)
    assert state == {"key": "value"}


# === parse_date ===
def test_parse_date():
    assert parse_date("2026-04-01") == date(2026, 4, 1)


def test_normalize_splitwise_date_to_local():
    timestamp = "2026-04-07T02:35:44Z"
    expected = dateparser.parse(timestamp).astimezone().date().isoformat()
    assert normalize_splitwise_date_to_local(timestamp) == expected
    assert normalize_splitwise_date_to_local("2026-04-06") == "2026-04-06"


def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date(None)
    with pytest.raises(ValueError):
        parse_date("not_a_date_zzz_xyz")

# === parse_float_safe ===
def test_parse_float_safe():
    assert parse_float_safe("10.5") == 10.5
    assert parse_float_safe(None) == 0.0
    assert parse_float_safe("abc") == 0.0

# === generate_fingerprint ===
def test_generate_fingerprint():
    fp = generate_fingerprint("2026-04-01", "50.00", "Test")
    assert isinstance(fp, str)
    assert len(fp) == 64

def test_generate_fingerprint_bad_amount():
    fp = generate_fingerprint("2026-04-01", "bad", "Test")
    assert isinstance(fp, str)

def test_generate_fingerprint_errors():
    # Trigger exception path
    fp = generate_fingerprint(None, None, None)
    assert isinstance(fp, str)


