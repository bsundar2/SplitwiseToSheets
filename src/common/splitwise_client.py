"""Client for interacting with the Splitwise API.

This module provides a high-level interface for common Splitwise operations,
including expense management, search, and data export.
"""

# Standard library
import os
import time
from functools import cache

# Third-party
import pandas as pd
from splitwise import Splitwise
from splitwise.exception import (
    SplitwiseBadRequestException,
    SplitwiseException,
    SplitwiseNotAllowedException,
    SplitwiseNotFoundException,
    SplitwiseUnauthorizedException,
)

# Local application
from src.common.env import load_project_env
from src.common.transaction_filters import is_deleted_expense
from src.common.utils import (
    LOG,
    normalize_splitwise_date_to_local,
    parse_float_safe,
)
from src.constants.export_columns import ExportColumns
from src.constants.splitwise import (
    DELETED_AT_FIELD,
    REFUND_KEYWORDS,
    SPLIT_TYPE_PARTNER,
    SPLIT_TYPE_SELF,
    SPLIT_TYPE_SPLIT,
    SPLITWISE_PAGE_SIZE,
    SplitwiseUserId,
)

load_project_env()

# Non-retryable Splitwise exceptions: these map to 401/400/403/404 responses,
# where retrying the identical request will never succeed. Everything else
# (SplitwiseException raised for any other status - typically 429 or 5xx) is
# treated as transient and retried with backoff.
_NON_RETRYABLE_SPLITWISE_EXCEPTIONS = (
    SplitwiseUnauthorizedException,
    SplitwiseBadRequestException,
    SplitwiseNotAllowedException,
    SplitwiseNotFoundException,
)
_RETRY_MAX_ATTEMPTS = 4
_RETRY_BASE_DELAY_SECONDS = 2.0

# Circuit breaker: if this many calls in a row each exhaust their own retry
# budget (i.e. the API failed 4 times in a row on that single call, not just
# once), treat it as a persistent/systemic outage rather than routine
# transient noise. Further calls then fail immediately without retrying,
# so a batch of N calls (e.g. fetching details for 1000+ expenses) fails
# fast instead of paying the full ~14s retry tax on every single one.
_CIRCUIT_BREAKER_THRESHOLD = 3


# Handles Splitwise API/CSV integration
class SplitwiseClient:
    def __init__(self):
        self.consumer_key = os.getenv("SPLITWISE_CONSUMER_KEY")
        self.consumer_secret = os.getenv("SPLITWISE_CONSUMER_SECRET")
        self.api_key = os.getenv("SPLITWISE_API_KEY")
        # Error handling for missing env vars
        if not all([self.consumer_key, self.consumer_secret, self.api_key]):
            raise ValueError(
                "One or more Splitwise credentials are missing. Check config/.env and variable names."
            )
        self.sObj = Splitwise(
            self.consumer_key, self.consumer_secret, api_key=self.api_key
        )
        # Circuit breaker state: count of consecutive calls that each fully
        # exhausted their retry budget. Reset to 0 on any successful call.
        self._consecutive_retry_exhaustions = 0

    def _call_with_retry(self, func, *args, **kwargs):
        """Call a read-only Splitwise SDK method with retry/backoff on transient errors.

        Only retries the generic SplitwiseException (raised for any response
        that isn't 200/401/403/400/404 - typically 429 rate-limiting or a 5xx),
        since those are the failures observed to be transient. Auth/client
        errors (401/400/403/404) are re-raised immediately since retrying an
        identical request won't fix them.

        If _CIRCUIT_BREAKER_THRESHOLD consecutive calls have each already
        exhausted their retries, this call fails immediately without
        attempting the request or sleeping - a batch of many such calls (e.g.
        per-expense detail fetches) then fails fast instead of spending the
        full retry budget on every single one once the API is persistently
        down.

        Only use this for idempotent (read) calls - never for expense
        creation, where a retry after a successful-but-unconfirmed request
        risks creating a duplicate expense in Splitwise.
        """
        if self._consecutive_retry_exhaustions >= _CIRCUIT_BREAKER_THRESHOLD:
            raise SplitwiseException(
                f"Splitwise API circuit breaker is open after "
                f"{self._consecutive_retry_exhaustions} consecutive calls exhausted "
                "their retries; skipping this call instead of retrying."
            )

        for attempt in range(_RETRY_MAX_ATTEMPTS):
            try:
                result = func(*args, **kwargs)
                self._consecutive_retry_exhaustions = 0
                return result
            except _NON_RETRYABLE_SPLITWISE_EXCEPTIONS:
                raise
            except SplitwiseException as e:
                if attempt >= _RETRY_MAX_ATTEMPTS - 1:
                    self._consecutive_retry_exhaustions += 1
                    if self._consecutive_retry_exhaustions >= _CIRCUIT_BREAKER_THRESHOLD:
                        LOG.error(
                            "%d consecutive Splitwise API calls have exhausted retries; "
                            "opening circuit breaker so further calls this run fail fast.",
                            self._consecutive_retry_exhaustions,
                        )
                    raise
                delay = _RETRY_BASE_DELAY_SECONDS * (2**attempt)
                LOG.warning(
                    "Splitwise API call failed (attempt %d/%d): %s - retrying in %.1fs",
                    attempt + 1,
                    _RETRY_MAX_ATTEMPTS,
                    str(e),
                    delay,
                )
                time.sleep(delay)

    @cache
    def get_current_user(self):
        """Get current user from Splitwise API.

        Returns:
            Splitwise User object
        """
        return self._call_with_retry(self.sObj.getCurrentUser)

    @cache
    def get_current_user_id(self):
        """Get current user ID from Splitwise API.

        Returns:
            int: User ID
        """
        return self.get_current_user().getId()

    def _fetch_expenses_paginated(
        self, start_date_str: str, end_date_str: str, fetch_full_details: bool = False
    ):
        """Core method to fetch expenses with pagination and optional full details.

        Args:
            start_date_str: Start date as string (YYYY-MM-DD)
            end_date_str: End date as string (YYYY-MM-DD)
            fetch_full_details: If True, fetches each expense individually to populate
                              the details field (slower but necessary for duplicate detection)

        Returns:
            list: List of expense objects from Splitwise API
        """
        LOG.info(
            f"Fetching expenses from {start_date_str} to {end_date_str}"
            + (" with full details" if fetch_full_details else "")
        )
        all_expenses = []
        offset = 0
        page_size = SPLITWISE_PAGE_SIZE
        has_more = True

        # First, get the list of expense IDs
        while has_more:
            try:
                expenses = self._call_with_retry(
                    self.sObj.getExpenses,
                    dated_after=start_date_str,
                    dated_before=end_date_str,
                    limit=page_size,
                    offset=offset,
                )

                if not expenses:
                    break

                # Filter out deleted expenses from the basic list
                non_deleted = [exp for exp in expenses if not is_deleted_expense(exp)]

                all_expenses.extend(non_deleted)

                if len(expenses) < page_size:
                    has_more = False
                else:
                    offset += page_size

                LOG.debug(
                    f"Fetched {len(expenses)} expenses (total: {len(all_expenses)})"
                )

            except Exception as e:
                LOG.error(f"Error fetching expense list (offset {offset}): {str(e)}")
                raise

        # If requested, fetch full details for each expense
        if fetch_full_details:
            LOG.info(
                f"Fetched {len(all_expenses)} expenses, now getting full details for each"
            )
            detailed_expenses = []
            for i, exp in enumerate(all_expenses):
                try:
                    expense_id = exp.getId()
                    # Fetch full expense details (includes the details field)
                    full_expense = self._call_with_retry(
                        self.sObj.getExpense, expense_id
                    )

                    # Skip deleted expenses
                    if not (
                        hasattr(full_expense, DELETED_AT_FIELD)
                        and getattr(full_expense, DELETED_AT_FIELD)
                    ):
                        detailed_expenses.append(full_expense)

                    if (i + 1) % 20 == 0:
                        LOG.info(f"Processed {i + 1}/{len(all_expenses)} expenses")

                except Exception as e:
                    LOG.warning(
                        f"Error fetching details for expense {expense_id}: {str(e)}"
                    )
                    # If the circuit breaker just tripped, the API is persistently
                    # failing rather than hitting isolated blips. Stop here instead
                    # of looping through the remaining expenses (each now failing
                    # near-instantly but still producing a cache with missing
                    # `details` fields) - a duplicate-detection cache built from
                    # incomplete data risks not recognizing an expense that
                    # already exists, and creating a duplicate.
                    if self._consecutive_retry_exhaustions >= _CIRCUIT_BREAKER_THRESHOLD:
                        raise RuntimeError(
                            f"Splitwise API appears to be persistently failing "
                            f"(circuit breaker open after "
                            f"{self._consecutive_retry_exhaustions} consecutive calls "
                            f"exhausted retries). Aborting after {i + 1}/"
                            f"{len(all_expenses)} expense-detail fetches instead of "
                            "continuing with an incomplete cache."
                        ) from e
                    # Keep the original expense without full details
                    detailed_expenses.append(exp)
                    continue

            all_expenses = detailed_expenses

        LOG.info(f"Retrieved {len(all_expenses)} expenses")
        return all_expenses


    def get_my_expenses_by_date_range(self, start_date, end_date):
        """Fetch all expenses within a date range with automatic pagination.

        This will page through the Splitwise API until no more results are
        returned for the date range. No hard cap is applied here; the function
        will continue paging until the API indicates the end of results.

        Args:
            start_date: Start date (datetime or date object)
            end_date: End date (datetime or date object)

        Returns:
            DataFrame containing all matching expenses
        """
        # Use the core pagination method (without full details for performance)
        all_expenses = self._fetch_expenses_paginated(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
            fetch_full_details=False,
        )

        # Process the expenses into a DataFrame
        my_user_id = self.get_current_user_id()
        data = []

        for expense in all_expenses:
            try:
                users = expense.getUsers() or []

                def _user_name(u) -> str:
                    first = u.getFirstName() or ""
                    return first.strip() or str(u.getId())

                user_rows = []
                for u in users:
                    user_rows.append(
                        {
                            "id": u.getId(),
                            "name": _user_name(u),
                            "paid": parse_float_safe(u.getPaidShare()),
                            "owed": parse_float_safe(u.getOwedShare()),
                        }
                    )

                user_rows_sorted = sorted(
                    user_rows, key=lambda r: (r["name"] or "").lower()
                )

                # Sheets-friendly: single deterministic string, easy to parse with SPLIT/REGEX
                # Example: "Alice|paid=10.00|owed=0.00; Bob|paid=0.00|owed=10.00"
                friends_split = "; ".join(
                    [
                        f"{r['name']}|paid={r['paid']:.2f}|owed={r['owed']:.2f}"
                        for r in user_rows_sorted
                    ]
                )

                participant_names = ", ".join([r["name"] for r in user_rows_sorted])

                my_row = next(
                    (r for r in user_rows_sorted if r["id"] == my_user_id), None
                )
                my_paid = my_row["paid"] if my_row else 0.0
                my_owed = my_row["owed"] if my_row else 0.0

                # Check if this is a refund by description keywords
                description = expense.getDescription() or ""
                is_refund = any(
                    keyword in description.lower() for keyword in REFUND_KEYWORDS
                )

                # For refunds, negate my_owed and my_paid to show as credits
                if is_refund:
                    my_owed = -my_owed
                    my_paid = -my_paid

                my_net = my_paid - my_owed

                participant_ids = {r["id"] for r in user_rows_sorted}

                has_self_user = SplitwiseUserId.SELF_EXPENSE in participant_ids
                is_partner_only = participant_ids == {
                    my_user_id,
                    SplitwiseUserId.PARTNER_EXPENSE,
                }

                if has_self_user:
                    split_type = SPLIT_TYPE_SELF
                elif is_partner_only:
                    split_type = SPLIT_TYPE_PARTNER
                else:
                    other_nonzero = any(
                        r["id"] != my_user_id and (r["paid"] > 0 or r["owed"] > 0)
                        for r in user_rows_sorted
                    )
                    split_type = (
                        SPLIT_TYPE_SPLIT if bool(other_nonzero) else SPLIT_TYPE_SELF
                    )

                data.append(
                    {
                        ExportColumns.DATE: normalize_splitwise_date_to_local(
                            expense.getDate()
                        ),
                        ExportColumns.AMOUNT: expense.getCost(),
                        ExportColumns.CATEGORY: (
                            expense.getCategory().getName()
                            if expense.getCategory()
                            else None
                        ),
                        ExportColumns.DESCRIPTION: expense.getDescription(),
                        ExportColumns.DETAILS: expense.getDetails() or "",
                        ExportColumns.SPLIT_TYPE: split_type,
                        ExportColumns.PARTICIPANT_NAMES: participant_names,
                        ExportColumns.MY_PAID: my_paid,
                        ExportColumns.MY_OWED: my_owed,
                        ExportColumns.MY_NET: my_net,
                        ExportColumns.FRIENDS_SPLIT: friends_split,
                        ExportColumns.ID: expense.getId(),
                    }
                )
            except Exception as e:
                LOG.warning(
                    f"Error processing expense {getattr(expense, 'id', 'unknown')}: {str(e)}"
                )
                continue

        LOG.info(f"Found {len(data)} expenses between {start_date} and {end_date}")
        return pd.DataFrame(data)


    @cache
    def get_categories(self):
        """Get all available Splitwise categories and subcategories.

        Returns:
            list: List of category dictionaries with 'id', 'name', and 'subcategories'
        """
        return self._call_with_retry(self.sObj.getCategories)
