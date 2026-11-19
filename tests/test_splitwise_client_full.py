"""Extended SplitwiseClient tests for get_expense_by_id and add_expense_from_txn."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from splitwise.exception import SplitwiseException
from src.common.splitwise_client import SplitwiseClient
from src.constants.export_columns import ExportColumns

@pytest.fixture
def mock_env():
    with patch.dict("os.environ", {
        "SPLITWISE_CONSUMER_KEY": "fake",
        "SPLITWISE_CONSUMER_SECRET": "fake",
        "SPLITWISE_API_KEY": "fake"
    }):
        yield

@pytest.fixture
def client(mock_env):
    with patch("src.common.splitwise_client.Splitwise"):
        return SplitwiseClient()


# === get_categories ===
def test_get_categories(client):
    client.sObj.getCategories.return_value = [{"id": 1, "name": "Food"}]
    cats = client.get_categories()
    assert len(cats) == 1

# === _fetch_expenses_paginated ===
def test_fetch_paginated_full_details(client):
    mock_exp = MagicMock()
    mock_exp.getId.return_value = 1
    mock_exp.deleted_at = None
    
    mock_full = MagicMock()
    mock_full.getId.return_value = 1
    mock_full.deleted_at = None
    
    client.sObj.getExpenses.side_effect = [[mock_exp], []]
    client.sObj.getExpense.return_value = mock_full
    
    res = client._fetch_expenses_paginated("2026-01-01", "2026-01-02", fetch_full_details=True)
    assert len(res) == 1

def test_fetch_paginated_api_error(client):
    client.sObj.getExpenses.side_effect = Exception("Connection error")
    with pytest.raises(Exception, match="Connection error"):
        client._fetch_expenses_paginated("2026-01-01", "2026-01-02")

@patch("src.common.splitwise_client.time.sleep")
def test_fetch_paginated_full_details_aborts_once_circuit_breaker_trips(
    mock_sleep, client
):
    """If getExpense is persistently failing (not just an isolated blip), the
    per-expense detail loop should stop once the circuit breaker trips rather
    than looping through every remaining expense - each of which would fail
    fast but leave the cache built from incomplete data, risking a duplicate
    expense being created because an existing one wasn't recognized."""
    mock_exps = []
    for i in range(10):
        exp = MagicMock()
        exp.getId.return_value = i
        exp.deleted_at = None
        mock_exps.append(exp)

    client.sObj.getExpenses.side_effect = [mock_exps, []]
    client.sObj.getExpense.side_effect = SplitwiseException("Unknown error happened")

    with pytest.raises(RuntimeError, match="circuit breaker open"):
        client._fetch_expenses_paginated(
            "2026-01-01", "2026-01-02", fetch_full_details=True
        )

    # 3 expenses each exhaust their 4-attempt retry budget (12 calls total);
    # the 3rd exhaustion trips the breaker and the loop aborts before ever
    # attempting expense #4 - far fewer than 10 * 4 = 40 attempts.
    assert client.sObj.getExpense.call_count == 12


# === get_my_expenses_by_date_range ===
def test_get_my_expenses_partner_split(client):
    from src.constants.splitwise import SPLIT_TYPE_PARTNER
    client.get_current_user_id = MagicMock(return_value=101)
    
    mock_exp = MagicMock()
    mock_exp.getId.return_value = 1
    mock_exp.getDate.return_value = "2026-01-01T00:00:00Z"
    mock_exp.getCreatedAt.return_value = "2026-01-01T00:00:00Z"
    mock_exp.getUpdatedAt.return_value = "2026-01-01T00:00:00Z"
    mock_exp.getDescription.return_value = "Groceries"
    mock_exp.getCost.return_value = "50.0"
    mock_exp.getDetails.return_value = ""
    mock_exp.getCategory.return_value.getName.return_value = "Food"
    mock_exp.getCreationMethod.return_value = "equal"
    
    mock_user_me = MagicMock()
    mock_user_me.getId.return_value = 101
    mock_user_me.getFirstName.return_value = "Me"
    mock_user_me.getPaidShare.return_value = "50.0"
    mock_user_me.getOwedShare.return_value = "25.0"
    
    mock_ids = MagicMock()
    mock_ids.SELF_EXPENSE = 303
    mock_ids.PARTNER_EXPENSE = 202
    
    with patch("src.common.splitwise_client.SplitwiseUserId", mock_ids):
        
        mock_user_partner = MagicMock()
        mock_user_partner.getId.return_value = 202
        mock_user_partner.getFirstName.return_value = "Partner"
        mock_user_partner.getPaidShare.return_value = "0.0"
        mock_user_partner.getOwedShare.return_value = "25.0"
        
        mock_exp.getUsers.return_value = [mock_user_me, mock_user_partner]
        client._fetch_expenses_paginated = MagicMock(return_value=[mock_exp])
        
        df = client.get_my_expenses_by_date_range(datetime(2026, 1, 1), datetime(2026, 1, 31))
        assert len(df) == 1
        assert df.iloc[0][ExportColumns.SPLIT_TYPE] == SPLIT_TYPE_PARTNER


