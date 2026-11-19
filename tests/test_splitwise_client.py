import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import datetime as dt_module

from splitwise.exception import SplitwiseException, SplitwiseUnauthorizedException
from src.common.splitwise_client import SplitwiseClient

@pytest.fixture
def mock_env():
    with patch.dict("os.environ", {
        "SPLITWISE_CONSUMER_KEY": "fake_key",
        "SPLITWISE_CONSUMER_SECRET": "fake_secret",
        "SPLITWISE_API_KEY": "fake_api"
    }):
        yield

@pytest.fixture
def splitwise_client(mock_env):
    with patch("src.common.splitwise_client.Splitwise"):
        return SplitwiseClient()

def test_init_raises_value_error_if_missing_credentials():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError):
            SplitwiseClient()

def test_get_current_user_id(splitwise_client):
    mock_user = MagicMock()
    mock_user.getId.return_value = 12345
    splitwise_client.sObj.getCurrentUser.return_value = mock_user
    assert splitwise_client.get_current_user_id() == 12345

def test_fetch_expenses_paginated(splitwise_client):
    mock_exp1 = MagicMock()
    mock_exp1.deleted_at = None
    mock_exp2 = MagicMock()
    mock_exp2.deleted_at = "deleted_timestamp"
    splitwise_client.sObj.getExpenses.side_effect = [[mock_exp1, mock_exp2], []]
    res = splitwise_client._fetch_expenses_paginated("2026-01-01", "2026-01-31")
    assert len(res) == 1
    assert res[0] == mock_exp1
    splitwise_client.sObj.getExpenses.assert_called()

@patch("src.common.splitwise_client.time.sleep")
def test_call_with_retry_succeeds_after_transient_error(mock_sleep, splitwise_client):
    """A generic SplitwiseException (rate limit / 5xx) is retried with backoff
    and succeeds once the transient failure clears."""
    fn = MagicMock(side_effect=[SplitwiseException("Unknown error happened"), "ok"])
    result = splitwise_client._call_with_retry(fn)
    assert result == "ok"
    assert fn.call_count == 2
    mock_sleep.assert_called_once_with(2.0)

@patch("src.common.splitwise_client.time.sleep")
def test_call_with_retry_does_not_retry_auth_error(mock_sleep, splitwise_client):
    """SplitwiseUnauthorizedException (401) is not retried - retrying an
    identical request can't fix bad credentials."""
    fn = MagicMock(side_effect=SplitwiseUnauthorizedException("bad token"))
    with pytest.raises(SplitwiseUnauthorizedException):
        splitwise_client._call_with_retry(fn)
    assert fn.call_count == 1
    mock_sleep.assert_not_called()

@patch("src.common.splitwise_client.time.sleep")
def test_call_with_retry_exhausts_and_raises(mock_sleep, splitwise_client):
    """After the max attempts are all transient failures, the last exception
    propagates instead of retrying forever."""
    fn = MagicMock(side_effect=SplitwiseException("Unknown error happened"))
    with pytest.raises(SplitwiseException):
        splitwise_client._call_with_retry(fn)
    assert fn.call_count == 4
    assert mock_sleep.call_count == 3

@patch("src.common.splitwise_client.time.sleep")
def test_call_with_retry_circuit_breaker_trips_after_repeated_exhaustion(
    mock_sleep, splitwise_client
):
    """Once 3 separate calls have each exhausted their own retries, a further
    call fails immediately without attempting the request or sleeping - so a
    batch of many calls fails fast instead of paying the full retry cost on
    every single one during a persistent outage."""
    fn = MagicMock(side_effect=SplitwiseException("Unknown error happened"))

    for _ in range(3):
        with pytest.raises(SplitwiseException):
            splitwise_client._call_with_retry(fn)

    fn.reset_mock()
    mock_sleep.reset_mock()

    with pytest.raises(SplitwiseException, match="circuit breaker is open"):
        splitwise_client._call_with_retry(fn)
    fn.assert_not_called()
    mock_sleep.assert_not_called()

@patch("src.common.splitwise_client.time.sleep")
def test_call_with_retry_resets_circuit_breaker_on_success(mock_sleep, splitwise_client):
    """A successful call resets the consecutive-exhaustion counter, so an
    isolated run of failures doesn't permanently trip the breaker."""
    for _ in range(2):
        fn = MagicMock(side_effect=SplitwiseException("Unknown error happened"))
        with pytest.raises(SplitwiseException):
            splitwise_client._call_with_retry(fn)
    assert splitwise_client._consecutive_retry_exhaustions == 2

    ok_fn = MagicMock(return_value="ok")
    assert splitwise_client._call_with_retry(ok_fn) == "ok"
    assert splitwise_client._consecutive_retry_exhaustions == 0


@patch("os.getenv")
def test_get_my_expenses_pagination_detailed(mock_getenv):
    mock_getenv.return_value = "dummy_val"
    client = SplitwiseClient()
    mock_sw = MagicMock()
    client.sObj = mock_sw
    
    expense1 = MagicMock()
    expense1.getId.return_value = 1
    expense1.getCost.return_value = "10.0"
    expense1.getDate.return_value = "2026-01-01T00:00:00Z"
    expense1.getDescription.return_value = "Test1"
    expense1.getDetails.return_value = "details"
    expense1.getCurrencyCode.return_value = "USD"
    expense1.deleted_at = None
    expense1.getDeletedAt.return_value = None
    expense1.getUpdatedAt.return_value = "2026-01-01T00:00:00Z"
    expense1.getCreatedAt.return_value = "2026-01-01T00:00:00Z"
    expense1.getCategory.return_value.getName.return_value = "Food"
    
    user1 = MagicMock()
    user1.getId.return_value = 12345
    user1.getPaidShare.return_value = "10.0"
    user1.getOwedShare.return_value = "5.0"
    user1.getFirstName.return_value = "Me"
    user1.getLastName.return_value = "Self"
    expense1.getUsers.return_value = [user1]
    
    mock_sw.getExpenses.side_effect = [[expense1], []]
    mock_sw.getCurrentUser.return_value.getId.return_value = 12345
    
    df = client.get_my_expenses_by_date_range(
        dt_module.date(2026, 1, 1), 
        dt_module.date(2026, 1, 2)
    )
    assert len(df) == 1

@patch("os.getenv")
def test_get_my_expenses_error_handling(mock_getenv):
    mock_getenv.return_value = "dummy_val"
    client = SplitwiseClient()
    mock_sw = MagicMock()
    client.sObj = mock_sw
    mock_sw.getExpenses.side_effect = Exception("API Error")
    
    with pytest.raises(Exception, match="API Error"):
        client.get_my_expenses_by_date_range(
            dt_module.date(2026, 1, 1), 
            dt_module.date(2026, 1, 2)
        )
