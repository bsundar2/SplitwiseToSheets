"""Transaction filtering utilities.

Provides common filtering logic for deleted expenses, payments, refunds, etc.
Centralizes these checks to avoid duplication across the codebase.
"""

import re
from typing import Any, Optional

import pandas as pd

from src.constants.splitwise import (
    DELETED_AT_FIELD,
    ExcludedSplitwiseDescriptions,
)

# Splitwise's catch-all category - where its own auto-generated settlement/
# payment records land. A "payment"-worded description only counts as a
# settlement record when it's also filed under this category; a real
# expense filed under its own category (e.g. "Mortgage Payment" under
# "Mortgage") is never a settlement record just because of its wording.
GENERAL_CATEGORY = "General"


def is_deleted_expense(expense_obj: Any) -> bool:
    """Check if Splitwise expense object is deleted.

    Args:
        expense_obj: Splitwise expense object from API

    Returns:
        True if expense is marked as deleted
    """
    return (
        hasattr(expense_obj, DELETED_AT_FIELD)
        and getattr(expense_obj, DELETED_AT_FIELD) is not None
        and getattr(expense_obj, DELETED_AT_FIELD) != ""
    )


_PAID_RE = re.compile(r"Paid:\s*\$?\s*(-?[\d,]+\.?\d*)")
_OWED_RE = re.compile(r"Owe:\s*\$?\s*(-?[\d,]+\.?\d*)")


def parse_my_paid_owed(
    notes: Optional[str],
    is_refund: bool,
    is_shared: bool,
    raw_amount: Optional[float] = None,
    net_amount: float = 0.0,
    apply_fallback: bool = True,
) -> tuple:
    """Recover a transaction's my_paid/my_owed split from its `notes` field.

    The local DB only stores `amount` (my_net = my_paid - my_owed, a
    cash-flow/settlement figure - it goes negative for an expense your
    split partner paid, even though your real *share* of it is a positive
    spend) and `raw_amount` (the full, un-split expense cost) - my_paid and
    my_owed themselves are never stored as their own columns. They're only
    recoverable from the "Paid: $X | Owe: $Y" text sync_from_splitwise()
    writes into `notes` at sync time.

    `my_owed` (not my_net) is the number that represents a personal
    budget's real "how much did I spend" figure - your allocated share of
    every expense regardless of who fronted the payment.

    Args:
        notes: The transaction's notes field.
        is_refund: Whether this transaction is a refund/credit.
        is_shared: Whether this transaction was split with someone else.
        raw_amount: The full expense cost before splitting (for the
            fallback below).
        net_amount: my_net, used as a last-resort fallback if raw_amount
            isn't available either.
        apply_fallback: If True and notes didn't yield a value (e.g. an
            older CSV-imported row with no notes), estimate my_paid/my_owed
            from raw_amount/net_amount instead of leaving them at 0 - the
            full amount if not shared, an assumed 50/50 split if shared.

    Returns:
        (my_paid, my_owed) tuple.
    """
    my_paid = 0.0
    my_owed = 0.0

    if notes:
        paid_match = _PAID_RE.search(notes)
        if paid_match:
            my_paid = float(paid_match.group(1).replace(",", ""))
        owe_match = _OWED_RE.search(notes)
        if owe_match:
            my_owed = float(owe_match.group(1).replace(",", ""))

    if is_refund:
        # -abs() rather than plain negation: notes may already store a
        # negative Owe value, and a plain negation would double-negate
        # that back to positive.
        my_owed = -abs(my_owed)
        my_paid = -abs(my_paid)

    if apply_fallback and my_paid == 0.0 and my_owed == 0.0:
        base = raw_amount if raw_amount else net_amount
        signed = -abs(base) if is_refund else abs(base)
        if is_shared:
            my_paid = signed / 2
            my_owed = signed / 2
        else:
            my_paid = signed
            my_owed = signed

    return my_paid, my_owed


def settlement_row_mask(
    descriptions: pd.Series, categories: Optional[pd.Series] = None
) -> pd.Series:
    """Boolean mask identifying Splitwise-generated settlement/payment rows
    to exclude from budgeting/analysis - NOT a general "is this a payment
    merchant" check (see is_payment_transaction for that, broader, use case
    over raw credit-card statement lines).

    A row counts as a settlement record when its description exactly
    matches "Settle all balances" (case-insensitive, trimmed), or when its
    description exactly matches "Payment" or contains the word "payment"
    AND its category is Splitwise's catch-all "General". That category
    scoping matters: a real, properly-categorized expense like "Mortgage
    Payment" filed under a "Mortgage" category must never be dropped just
    because its wording contains "payment".

    This is the single implementation shared by the raw expenses export,
    the budget summaries, and the spending dashboard (previously
    duplicated separately in each, which is how a stricter version of this
    check once slipped into the dashboard and hid real "payment"-worded
    expenses that weren't in the General category).

    Args:
        descriptions: Series of transaction descriptions/merchant names.
        categories: Series of transaction categories, aligned by index with
            `descriptions`. If omitted, every row is treated as eligible
            for the payment-wording check (matches the behavior of callers
            that don't always have a category column available).

    Returns:
        Boolean Series, aligned with `descriptions`, True for rows that are
        settlement/payment records rather than real expenses.
    """
    desc = descriptions.fillna("").astype(str).str.strip()
    settle_mask = desc.str.lower().eq(
        ExcludedSplitwiseDescriptions.SETTLE_ALL_BALANCES.value.lower()
    )
    payment_exact = desc.str.lower().eq(
        ExcludedSplitwiseDescriptions.PAYMENT.value.lower()
    )
    payment_word = desc.str.contains(r"\bpayment\b", case=False, na=False)
    payment_candidate = payment_exact | payment_word

    if categories is not None:
        category_general = (
            categories.fillna("").astype(str).str.strip().eq(GENERAL_CATEGORY)
        )
        payment_mask = payment_candidate & category_general
    else:
        payment_mask = payment_candidate

    return settle_mask | payment_mask


def extract_participant_names(notes: str) -> str:
    """Extract participant names from transaction notes.

    Extracts the comma-separated list of names from the "With: name1, name2"
    field in transaction notes.

    Args:
        notes: Transaction notes field

    Returns:
        Comma-separated participant names, or empty string if not found
    """
    if not notes:
        return ""

    with_match = re.search(r"With:\s*([^|]+?)(?:\s*$|\s*\|)", notes)
    if with_match:
        return with_match.group(1).strip()

    return ""


def is_user_participant(txn, current_user_name: str) -> bool:
    """Check if current user is a participant in the transaction.

    Args:
        txn: Transaction object from database
        current_user_name: Current user's first name from Splitwise

    Returns:
        True if user is in the participant list, False otherwise
    """
    if not current_user_name or not txn.notes:
        return True  # Allow if we can't determine

    participant_names = extract_participant_names(txn.notes)
    return current_user_name in participant_names
