
import pandas as pd

from src.common.transaction_filters import (
    is_deleted_expense,
    parse_my_paid_owed,
    settlement_row_mask,
)


class MockExpense:
    def __init__(self, deleted_at=None):
        self.deleted_at = deleted_at


class MockTransaction:
    def __init__(
        self,
        splitwise_deleted_at=None,
        is_refund=False,
        description=None,
        merchant=None,
    ):
        self.splitwise_deleted_at = splitwise_deleted_at
        self.is_refund = is_refund
        self.description = description
        self.merchant = merchant


def test_is_deleted_expense():
    assert is_deleted_expense(MockExpense(deleted_at="2023-01-01T00:00:00Z")) is True
    assert is_deleted_expense(MockExpense(deleted_at="")) is False
    assert is_deleted_expense(MockExpense(deleted_at=None)) is False

    # Object without deleted_at attribute
    class NoDeletedAtObj:
        pass

    assert is_deleted_expense(NoDeletedAtObj()) is False


def test_settlement_row_mask_settle_all_balances_always_excluded():
    descriptions = pd.Series(["Settle all balances", "Groceries"])
    categories = pd.Series(["General", "Food"])

    result = settlement_row_mask(descriptions, categories)

    assert result.tolist() == [True, False]


def test_settlement_row_mask_payment_wording_scoped_to_general_category():
    descriptions = pd.Series(
        ["Payment", "Mobile Payment Received", "Mortgage Payment", "Car Payment"]
    )
    categories = pd.Series(["General", "General", "Mortgage", "Transportation"])

    result = settlement_row_mask(descriptions, categories)

    assert result.tolist() == [True, True, False, False]


def test_settlement_row_mask_no_category_series_treats_all_as_eligible():
    descriptions = pd.Series(["Mortgage Payment", "Groceries"])

    result = settlement_row_mask(descriptions)

    assert result.tolist() == [True, False]


def test_settlement_row_mask_handles_missing_values():
    descriptions = pd.Series(["Groceries", None])
    categories = pd.Series([None, "General"])

    result = settlement_row_mask(descriptions, categories)

    assert result.tolist() == [False, False]


# ── parse_my_paid_owed ──────────────────────────────────────────────────────


def test_parse_my_paid_owed_from_notes():
    my_paid, my_owed = parse_my_paid_owed(
        "Imported from Splitwise API | Paid: $100.00 | Owe: $50.00 | With: Partner",
        is_refund=False,
        is_shared=True,
    )
    assert my_paid == 100.0
    assert my_owed == 50.0


def test_parse_my_paid_owed_partner_paid_gives_negative_net_but_positive_owed():
    # Partner paid, so my_paid is 0 - but my share (my_owed) is still a
    # real, positive spend even though my_net (my_paid - my_owed) is
    # negative here.
    my_paid, my_owed = parse_my_paid_owed(
        "Paid: $0.00 | Owe: $50.00",
        is_refund=False,
        is_shared=True,
    )
    assert my_paid == 0.0
    assert my_owed == 50.0
    assert (my_paid - my_owed) < 0  # my_net would be negative
    assert my_owed > 0  # but the real spend (my_owed) is still positive


def test_parse_my_paid_owed_refund_forces_negative_via_abs():
    # -abs() rather than plain negation: notes may already store a
    # negative Owe, and a plain negation would double-negate it positive.
    my_paid, my_owed = parse_my_paid_owed(
        "Paid: $-20.00 | Owe: $-20.00",
        is_refund=True,
        is_shared=False,
    )
    assert my_paid == -20.0
    assert my_owed == -20.0


def test_parse_my_paid_owed_fallback_self_uses_full_amount():
    my_paid, my_owed = parse_my_paid_owed(
        notes=None,
        is_refund=False,
        is_shared=False,
        raw_amount=80.0,
    )
    assert my_paid == 80.0
    assert my_owed == 80.0


def test_parse_my_paid_owed_fallback_shared_assumes_50_50():
    my_paid, my_owed = parse_my_paid_owed(
        notes=None,
        is_refund=False,
        is_shared=True,
        raw_amount=80.0,
    )
    assert my_paid == 40.0
    assert my_owed == 40.0


def test_parse_my_paid_owed_fallback_uses_net_amount_if_no_raw_amount():
    my_paid, my_owed = parse_my_paid_owed(
        notes=None,
        is_refund=False,
        is_shared=False,
        raw_amount=None,
        net_amount=30.0,
    )
    assert my_paid == 30.0
    assert my_owed == 30.0


def test_parse_my_paid_owed_no_fallback_when_disabled():
    my_paid, my_owed = parse_my_paid_owed(
        notes=None,
        is_refund=False,
        is_shared=False,
        raw_amount=80.0,
        apply_fallback=False,
    )
    assert my_paid == 0.0
    assert my_owed == 0.0
