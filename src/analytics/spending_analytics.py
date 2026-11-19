"""Pure spending-analytics calculations over the local transactions database.

Shared by the interactive marimo dashboard (src/analytics/spending_dashboard.py)
and covered directly by tests/test_spending_analytics.py - the same split used
by the sibling FinanceToSheets repo between src/pnl_calculator.py (tested)
and src/pnl_tracker.py (dashboard, untested).

All spend figures use the `amount` column - load_transactions_df()
overwrites it with each transaction's my_owed (your true allocated share
of the expense, recovered from `notes` via parse_my_paid_owed()) rather
than the DB's own `amount` column, which stores my_net (my_paid -
my_owed). my_net is a cash-flow/settlement figure, not a spend figure: it
goes negative for any expense your split partner paid, even though your
real share of it is a positive spend - summed across a lot of
partner-paid expenses, that can silently cancel out a large chunk of your
true spend. my_owed is what the trusted Sheets export and budget
summaries actually use for their own totals, so this keeps the dashboard
consistent with them.
"""

import json
import os
import threading
from datetime import date
from typing import Optional

import pandas as pd

from src.common.transaction_filters import parse_my_paid_owed, settlement_row_mask
from src.common.utils import LOG
from src.constants.export_columns import ExportColumns
from src.constants.splitwise import SPLIT_TYPE_SELF
from src.database.db_manager import DELETED_FILTER_CLAUSE, DatabaseManager

UNCATEGORIZED = "Uncategorized"
RECENT_SYNC_YEARS_BACK = 2
CATEGORY_BUDGETS_ENV_VAR = "CATEGORY_BUDGETS"
EXPENSE_LOG_SPREADSHEET_KEYS_ENV_VAR = "EXPENSE_LOG_SPREADSHEET_KEYS"
EXPENSE_LOG_WORKSHEET = "Expense Log"

# Process-lifetime cache for sync_recent_years_if_on_render(): each browser
# session runs the dashboard's notebook independently, so without this,
# opening a second tab (or reconnecting) would kick off a second concurrent
# sync against the same SQLite file - which is exactly what caused a
# "UNIQUE constraint failed: transactions.splitwise_id" crash in practice
# (two sessions both inserting the same not-yet-committed row). The lock
# also means the sync only happens once per Render container boot, not on
# every page load.
_render_sync_lock = threading.Lock()
_render_sync_done = False
_render_sync_result: Optional[str] = None


def load_transactions_df(
    db_path: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_deleted: bool = False,
) -> pd.DataFrame:
    """Load transactions from the local SQLite DB into an analysis-ready DataFrame.

    Excludes Splitwise-deleted rows (unless `include_deleted`) and
    settlement/payment rows via settlement_row_mask() - the same shared
    logic the Sheets export and budget summaries use, so a real,
    properly-categorized expense like "Mortgage Payment" under a "Mortgage"
    category is never dropped just because its wording contains "payment".

    Overwrites `amount` with each row's my_owed (see module docstring) -
    the true personal-spend figure, not the DB's stored my_net.

    Args:
        db_path: Path to the SQLite DB. Defaults to data/transactions.db.
        start_date: Optional ISO date (YYYY-MM-DD) lower bound, inclusive.
        end_date: Optional ISO date (YYYY-MM-DD) upper bound, inclusive.
        include_deleted: If True, keep Splitwise-deleted transactions.

    Returns:
        DataFrame with a parsed `date` column, `amount` recomputed as
        my_owed, and `category` defaulted to "Uncategorized" where missing.
    """
    db = DatabaseManager(db_path) if db_path else DatabaseManager()
    conn = db.get_connection()
    try:
        query = "SELECT * FROM transactions WHERE 1=1"
        params: list = []
        if not include_deleted:
            query += f" AND {DELETED_FILTER_CLAUSE}"
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return df

    df = df[~settlement_row_mask(df["merchant"], df["category"])].copy()
    df["date"] = pd.to_datetime(df["date"])
    # Strip whitespace so e.g. "Rent" and "Rent " (or a stray leading
    # space) don't group as two separate rows downstream - the DB schema
    # doesn't enforce trimmed values.
    df["merchant"] = df["merchant"].str.strip()
    df["category"] = df["category"].fillna(UNCATEGORIZED).str.strip()
    if "subcategory" in df.columns:
        df["subcategory"] = df["subcategory"].str.strip()

    def _my_owed(row):
        notes = row["notes"] if pd.notna(row["notes"]) else None
        raw_amount = row["raw_amount"] if pd.notna(row["raw_amount"]) else None
        _, my_owed = parse_my_paid_owed(
            notes=notes,
            is_refund=bool(row["is_refund"]),
            is_shared=bool(row["is_shared"]),
            raw_amount=raw_amount,
            net_amount=row["amount"],
        )
        return my_owed

    df["amount"] = df.apply(_my_owed, axis=1)

    return df.reset_index(drop=True)


def expense_log_spreadsheet_keys() -> list[str]:
    """Spreadsheets whose "Expense Log" tab the dashboard reads instead of
    the local DB: EXPENSE_LOG_SPREADSHEET_KEYS, comma-separated (e.g. this
    year's budget sheet plus last year's). Empty when unset."""
    raw = os.environ.get(EXPENSE_LOG_SPREADSHEET_KEYS_ENV_VAR, "")
    return [key.strip() for key in raw.split(",") if key.strip()]


def _sheet_number(value) -> float:
    """A currency cell as Sheets formats it ("$1,234.56", "-$5.00", "($5.00)")."""
    text = str(value if value is not None else "").strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "")
    number = pd.to_numeric(text, errors="coerce")
    if pd.isna(number):
        return 0.0
    return -float(number) if negative else float(number)


def expense_log_to_transactions_df(log: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Map rows of the "Expense Log" tab (written by splitwise_export.py)
    onto the columns load_transactions_df() returns, so every analytics
    function works on either source.

    `amount` is the My Owed column - the same my_owed figure
    load_transactions_df() recovers from notes. Description doubles as
    `merchant`, as it does in the DB (sync_from_splitwise sets merchant to
    the description), and `is_shared` is any Split Type other than "self".
    """
    columns = [
        "date",
        "merchant",
        "description",
        "category",
        "amount",
        "is_shared",
        "splitwise_id",
    ]
    if log is None or log.empty:
        return pd.DataFrame(columns=columns)

    def text(column) -> pd.Series:
        if column not in log.columns:
            return pd.Series("", index=log.index)
        return log[column].fillna("").astype(str).str.strip()

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(text(ExportColumns.DATE), errors="coerce"),
            "merchant": text(ExportColumns.DESCRIPTION),
            "category": text(ExportColumns.CATEGORY).replace("", UNCATEGORIZED),
            "amount": log[ExportColumns.MY_OWED].map(_sheet_number),
            "is_shared": text(ExportColumns.SPLIT_TYPE).str.lower() != SPLIT_TYPE_SELF,
            "splitwise_id": text(ExportColumns.ID),
        }
    )
    df["description"] = df["merchant"]
    df = df.dropna(subset=["date"])
    df = df[~settlement_row_mask(df["merchant"], df["category"])]
    return df[columns].sort_values("date").reset_index(drop=True)


def load_transactions_from_sheets(
    spreadsheet_keys: list[str],
) -> tuple[pd.DataFrame, Optional[str]]:
    """Every listed spreadsheet's Expense Log, combined. An expense in more
    than one of them (same Splitwise ID) is kept once.

    Returns:
        (transactions, error) - error is a message naming what couldn't be
        read, with the rest of the spreadsheets still loaded.
    """
    # Imported here so the html-wasm build, which has no pygsheets, can
    # still import this module.
    from src.common.sheets_sync import read_from_sheets

    frames, errors = [], []
    for key in spreadsheet_keys:
        try:
            log = read_from_sheets(key, EXPENSE_LOG_WORKSHEET, numerize=False)
        except Exception as e:  # noqa: BLE001 - any Sheets/auth/network failure
            LOG.warning("Couldn't read Expense Log from %s: %s", key, e)
            errors.append(f"{key}: {e}")
            continue
        df = expense_log_to_transactions_df(log)
        if not df.empty:
            frames.append(df)

    error = f"Couldn't read the Expense Log ({'; '.join(errors)})." if errors else None
    if not frames:
        return expense_log_to_transactions_df(None), error

    combined = pd.concat(frames, ignore_index=True)
    has_id = combined["splitwise_id"] != ""
    combined = pd.concat(
        [combined[has_id].drop_duplicates("splitwise_id"), combined[~has_id]]
    )
    return combined.sort_values("date").reset_index(drop=True), error


def load_dashboard_transactions(
    force: bool = False,
) -> tuple[pd.DataFrame, Optional[str]]:
    """The dashboard's transactions: the Expense Log tab(s) when
    EXPENSE_LOG_SPREADSHEET_KEYS is set - a few seconds, with no Splitwise
    resync on a cold start - otherwise the local DB, resynced first on
    Render (see sync_recent_years_if_on_render()).

    Returns:
        (transactions, error) - error is None unless loading failed.
    """
    keys = expense_log_spreadsheet_keys()
    if keys:
        return load_transactions_from_sheets(keys)
    sync_error = sync_recent_years_if_on_render(force=force)
    return load_transactions_df(), sync_error


def category_breakdown(df: pd.DataFrame, by: str = "category") -> pd.DataFrame:
    """Total spend grouped by category (or subcategory).

    `pct_of_total` is each category's net total as a share of *gross*
    spend (positive-amount transactions only, matching
    spend_concentration()) - not a share of the net total across all
    categories. Net totals can be negative for a refund-heavy category, so
    dividing by their sum instead makes it a moving target: one category
    with a large refund shrinks the denominator for every other category,
    and an unrelated category's share can balloon past 100%. Gross spend
    is a stable, always-positive denominator, so no single category's
    share of it can do that.

    Args:
        df: Transactions DataFrame (from load_transactions_df).
        by: Column to group by - "category" or "subcategory".

    Returns:
        DataFrame with [by, total, count, pct_of_total], sorted by total desc.
    """
    columns = [by, "total", "count", "pct_of_total"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    grouped_col = df[by].fillna(UNCATEGORIZED)
    grouped = (
        df.assign(**{by: grouped_col})
        .groupby(by)["amount"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("total", ascending=False)
    )
    gross_spend = df[df["amount"] > 0]["amount"].sum()
    grouped["pct_of_total"] = (
        (grouped["total"] / gross_spend * 100) if gross_spend else 0.0
    )
    return grouped[columns].reset_index(drop=True)


def merchant_breakdown(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Total spend grouped by merchant, top N by total spend.

    Args:
        df: Transactions DataFrame (from load_transactions_df).
        top_n: Number of top merchants to keep.

    Returns:
        DataFrame with [merchant, total, count, avg_amount], sorted by total desc.
    """
    columns = ["merchant", "total", "count", "avg_amount"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        df.groupby("merchant")["amount"]
        .agg(total="sum", count="count", avg_amount="mean")
        .reset_index()
        .sort_values("total", ascending=False)
    )
    return grouped[columns].head(top_n).reset_index(drop=True)


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly spend with month-over-month and year-over-year % change.

    Args:
        df: Transactions DataFrame (from load_transactions_df).

    Returns:
        DataFrame with [year_month, total, count, mom_pct, yoy_pct], sorted
        chronologically. year_month is a pandas Period (freq="M").
    """
    columns = ["year_month", "total", "count", "mom_pct", "yoy_pct"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    monthly = (
        df.assign(year_month=df["date"].dt.to_period("M"))
        .groupby("year_month")["amount"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("year_month")
    )
    # Reindex across every month in range so a month with zero spend still
    # occupies a row - otherwise pct_change(periods=12) would compare by row
    # position rather than by actual calendar month whenever a month is
    # skipped (e.g. no transactions at all that month).
    full_range = pd.period_range(
        monthly["year_month"].min(), monthly["year_month"].max(), freq="M"
    )
    monthly = (
        monthly.set_index("year_month")
        .reindex(full_range, fill_value=0)
        .rename_axis("year_month")
        .reset_index()
    )
    monthly["count"] = monthly["count"].astype(int)
    monthly["mom_pct"] = monthly["total"].pct_change() * 100
    monthly["yoy_pct"] = monthly["total"].pct_change(periods=12) * 100
    return monthly[columns].reset_index(drop=True)


def weekly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly spend, reindexed across every week in range so weeks with
    no spend show as zero rather than being omitted (keeps a continuous,
    comparable x-axis for charting).

    Args:
        df: Transactions DataFrame (from load_transactions_df).

    Returns:
        DataFrame with [week, total, count], sorted chronologically. week is
        a pandas Period (freq="W-SUN").
    """
    columns = ["week", "total", "count"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    weekly = (
        df.assign(week=df["date"].dt.to_period("W-SUN"))
        .groupby("week")["amount"]
        .agg(total="sum", count="count")
        .reset_index()
        .sort_values("week")
    )
    full_range = pd.period_range(
        weekly["week"].min(), weekly["week"].max(), freq="W-SUN"
    )
    weekly = (
        weekly.set_index("week")
        .reindex(full_range, fill_value=0)
        .rename_axis("week")
        .reset_index()
    )
    weekly["count"] = weekly["count"].astype(int)
    return weekly[columns]


# Recognized repeat-charge cadences: the day-gap window a merchant's
# charges must (mostly) fall within, the divisor to normalize its amount
# to a monthly-equivalent cost, and how many occurrences are realistic to
# expect within the ~2-year window the dashboard actually keeps synced
# (RECENT_SYNC_YEARS_BACK) - 3 occurrences of an annual charge would need
# 3 years of history, which the Render deployment's bounded resync never
# has, so annual gets a lower bar than monthly/quarterly.
RECURRING_CADENCES = {
    "monthly": {"days": (25, 35), "divisor": 1, "min_occurrences": 3},
    "quarterly": {"days": (80, 100), "divisor": 3, "min_occurrences": 3},
    "annual": {"days": (350, 380), "divisor": 12, "min_occurrences": 2},
}


def _normalize_merchant(name) -> str:
    """Case/whitespace-insensitive key so the same merchant re-synced under
    a slightly different spelling (e.g. Splitwise renaming "Fastrak Csc
    Tolls" to "FasTrak" mid-history) still groups as one recurring charge
    instead of splitting across variants that individually never reach
    min_occurrences. Not fuzzy matching - still requires an exact match
    once case/whitespace differences are removed."""
    return str(name).strip().casefold()


def _cluster_amounts(amounts: list, tolerance_pct: float) -> list:
    """Group a sorted amount list into price tiers, merging each value into
    the running cluster while it stays within `tolerance_pct` of that
    cluster's mean - tolerates a small number of price changes (e.g. one
    subscription price increase) instead of requiring near-uniform
    variance across the merchant's entire history."""
    clusters = [[amounts[0]]]
    for amount in amounts[1:]:
        cluster_mean = sum(clusters[-1]) / len(clusters[-1])
        if cluster_mean and abs(amount - cluster_mean) / cluster_mean <= tolerance_pct:
            clusters[-1].append(amount)
        else:
            clusters.append([amount])
    return clusters


def _current_price(amounts: pd.Series, tolerance_pct: float) -> float:
    """Average of the charges near the chronologically *last* one - the
    "what am I paying now" price. Deliberately not the highest-valued
    price cluster: a price cut (promo ending, plan downgrade) should read
    as the new lower price, not the old higher one just because it sorts
    last."""
    last_amount = amounts.iloc[-1]
    current_tier = amounts[(amounts - last_amount).abs() <= last_amount * tolerance_pct]
    return current_tier.mean()


def _match_cadence(median_gap: float) -> Optional[str]:
    """Name of the RECURRING_CADENCES bucket whose day window contains
    `median_gap`, or None if it matches none of them."""
    return next(
        (
            name
            for name, spec in RECURRING_CADENCES.items()
            if spec["days"][0] <= median_gap <= spec["days"][1]
        ),
        None,
    )


def detect_recurring_charges(
    df: pd.DataFrame,
    min_occurrences: Optional[int] = None,
    amount_tolerance_pct: float = 0.05,
    max_price_tiers: int = 2,
) -> pd.DataFrame:
    """Flag merchants with a regular, similarly-priced repeating charge - a
    proxy for subscriptions worth reviewing.

    Merchants are grouped by a case/whitespace-normalized name (see
    _normalize_merchant), then checked against each cadence in
    RECURRING_CADENCES (monthly/quarterly/annual) using the *median* gap
    between charges - robust to a single off gap (a weekend shift, a
    skipped cycle) in a way a strict per-gap window isn't, especially
    with few occurrences. A merchant qualifies when: its median gap falls
    within one cadence's day window; most other gaps are reasonably close
    to that median (`gap_consistency`, guards against a coincidental
    median from genuinely irregular spending); its amounts fall into at
    most `max_price_tiers` clusters (see _cluster_amounts - tolerates a
    price change, not just a perfectly flat price); and it has at least
    that cadence's min_occurrences (or the `min_occurrences` override,
    applied to every cadence, if given).

    Args:
        df: Transactions DataFrame (from load_transactions_df).
        min_occurrences: Overrides every cadence's own min_occurrences
            when given (mainly for tests); defaults to each cadence's
            value in RECURRING_CADENCES otherwise.
        amount_tolerance_pct: Max relative distance from a price cluster's
            mean for a charge to join that cluster.
        max_price_tiers: Max distinct price clusters allowed - 2 means "at
            most one price change" across the merchant's history.

    Returns:
        DataFrame with [merchant, cadence, occurrences, avg_amount,
        estimated_monthly_cost, avg_interval_days, first_seen, last_seen],
        sorted by estimated monthly cost desc. avg_amount and
        estimated_monthly_cost reflect the most recent price tier (what
        you're actually being charged now), not a blend across a price
        change. merchant is the most recent occurrence's own spelling.
    """
    columns = [
        "merchant",
        "cadence",
        "occurrences",
        "avg_amount",
        "estimated_monthly_cost",
        "avg_interval_days",
        "first_seen",
        "last_seen",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)

    spend = df[df["amount"] > 0].copy()
    spend["_merchant_key"] = spend["merchant"].map(_normalize_merchant)

    rows = []
    for _, group in spend.groupby("_merchant_key"):
        group = group.sort_values("date")

        if (
            len(_cluster_amounts(sorted(group["amount"]), amount_tolerance_pct))
            > max_price_tiers
        ):
            continue

        gaps = group["date"].diff().dt.days.dropna()
        if gaps.empty:
            continue
        median_gap = gaps.median()
        cadence = _match_cadence(median_gap)
        if cadence is None:
            continue

        spec = RECURRING_CADENCES[cadence]
        required = (
            min_occurrences if min_occurrences is not None else spec["min_occurrences"]
        )
        if len(group) < required:
            continue

        if (gaps.sub(median_gap).abs() <= median_gap * 0.35).mean() < 0.6:
            continue

        latest_amount = _current_price(group["amount"], amount_tolerance_pct)
        rows.append(
            {
                "merchant": group.iloc[-1]["merchant"],
                "cadence": cadence,
                "occurrences": len(group),
                "avg_amount": round(latest_amount, 2),
                "estimated_monthly_cost": round(latest_amount / spec["divisor"], 2),
                "avg_interval_days": round(gaps.mean(), 1),
                "first_seen": group["date"].min().date(),
                "last_seen": group["date"].max().date(),
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame(rows)
    return result.sort_values("estimated_monthly_cost", ascending=False)[
        columns
    ].reset_index(drop=True)


def spend_concentration(df: pd.DataFrame, by: str = "merchant", top_n: int = 5) -> dict:
    """What share of total spend the top-N merchants or categories account for.

    Args:
        df: Transactions DataFrame (from load_transactions_df).
        by: "merchant" or "category".
        top_n: Number of top groups to include.

    Returns:
        Dict with by, top_n, top_total, total_spend, pct_of_total, and a
        `groups` DataFrame of the top-N breakdown.
    """
    if by == "merchant":
        breakdown = merchant_breakdown(df, top_n=top_n)
    else:
        breakdown = category_breakdown(df, by=by).head(top_n)

    total_spend = df[df["amount"] > 0]["amount"].sum() if not df.empty else 0.0
    top_total = breakdown["total"].sum() if not breakdown.empty else 0.0

    return {
        "by": by,
        "top_n": top_n,
        "top_total": round(top_total, 2),
        "total_spend": round(total_spend, 2),
        "pct_of_total": (
            round((top_total / total_spend * 100), 1) if total_spend else 0.0
        ),
        "groups": breakdown,
    }


def biggest_transactions(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """The largest individual spend transactions (positive amounts only).

    A simpler, non-statistical replacement for the removed outlier
    detector: just the plain "what were my biggest purchases" list.

    Args:
        df: Transactions DataFrame (from load_transactions_df).
        top_n: Number of transactions to return.

    Returns:
        DataFrame with [date, merchant, category, amount], sorted by
        amount desc.
    """
    columns = ["date", "merchant", "category", "amount"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    spend = df[df["amount"] > 0]
    return (
        spend.sort_values("amount", ascending=False)[columns]
        .head(top_n)
        .reset_index(drop=True)
    )


def shared_vs_personal_breakdown(df: pd.DataFrame) -> dict:
    """How much of spend was on Splitwise-shared expenses vs. solo ones.

    `is_shared` is collected from Splitwise for every synced transaction
    but wasn't previously surfaced anywhere in the dashboard.

    Args:
        df: Transactions DataFrame (from load_transactions_df).

    Returns:
        Dict with shared_total, personal_total, shared_pct, personal_pct,
        shared_count, personal_count.
    """
    empty = {
        "shared_total": 0.0,
        "personal_total": 0.0,
        "shared_pct": 0.0,
        "personal_pct": 0.0,
        "shared_count": 0,
        "personal_count": 0,
    }
    if df.empty or "is_shared" not in df.columns:
        return empty

    spend = df[df["amount"] > 0]
    is_shared = spend["is_shared"].fillna(False).astype(bool)
    shared_total = spend.loc[is_shared, "amount"].sum()
    personal_total = spend.loc[~is_shared, "amount"].sum()
    total = shared_total + personal_total

    return {
        "shared_total": round(shared_total, 2),
        "personal_total": round(personal_total, 2),
        "shared_pct": round(shared_total / total * 100, 1) if total else 0.0,
        "personal_pct": round(personal_total / total * 100, 1) if total else 0.0,
        "shared_count": int(is_shared.sum()),
        "personal_count": int((~is_shared).sum()),
    }


def category_month_over_month_movers(df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Which categories moved the most (up or down) between the two most
    recent calendar months present in the data.

    Args:
        df: Transactions DataFrame (from load_transactions_df).
        top_n: Number of biggest movers to return.

    Returns:
        DataFrame with [category, current_total, prior_total, delta,
        delta_pct], sorted by absolute delta desc. delta_pct is NaN when
        prior_total is 0 (can't express a % change from zero). Empty if
        fewer than two distinct months are present.
    """
    columns = ["category", "current_total", "prior_total", "delta", "delta_pct"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    months = sorted(df["date"].dt.to_period("M").unique())
    if len(months) < 2:
        return pd.DataFrame(columns=columns)

    by_month_category = (
        df.assign(
            year_month=df["date"].dt.to_period("M"),
            category=df["category"].fillna(UNCATEGORIZED),
        )
        .groupby(["category", "year_month"])["amount"]
        .sum()
        .unstack(fill_value=0.0)
        .reindex(columns=months[-2:], fill_value=0.0)
    )

    result = by_month_category.set_axis(["prior_total", "current_total"], axis=1)
    result["delta"] = result["current_total"] - result["prior_total"]
    result["delta_pct"] = (result["delta"] / result["prior_total"] * 100).where(
        result["prior_total"] != 0
    )
    result = result.round(2).reset_index()[columns]

    return (
        result.reindex(result["delta"].abs().sort_values(ascending=False).index)
        .head(top_n)
        .reset_index(drop=True)
    )


def spending_pace_projection(
    df: pd.DataFrame, today: Optional[date] = None
) -> Optional[dict]:
    """Simple linear year-end projection: at the current daily spend rate
    for the current calendar year, roughly how much by Dec 31.

    Only meaningful for a year still in progress, so this always projects
    off `today`'s year regardless of any year filter applied upstream -
    returns None once that year is complete (or has no data yet).

    Args:
        df: Transactions DataFrame (from load_transactions_df) - pass the
            unfiltered set so a year filter elsewhere doesn't hide this
            year's data.
        today: Override for "today" (for tests). Defaults to date.today().

    Returns:
        Dict with year, days_elapsed, days_in_year, total_so_far,
        daily_rate, projected_total - or None if there's nothing to
        project (no data this year yet, or the year is already over).
    """
    today = today or date.today()
    year_start = date(today.year, 1, 1)
    days_in_year = (date(today.year + 1, 1, 1) - year_start).days
    days_elapsed = (today - year_start).days + 1
    if days_elapsed >= days_in_year or df.empty:
        return None

    year_df = df[df["date"].dt.year == today.year]
    if year_df.empty:
        return None

    total_so_far = year_df["amount"].sum()
    daily_rate = total_so_far / days_elapsed
    projected_total = daily_rate * days_in_year

    return {
        "year": today.year,
        "days_elapsed": days_elapsed,
        "days_in_year": days_in_year,
        "total_so_far": round(total_so_far, 2),
        "daily_rate": round(daily_rate, 2),
        "projected_total": round(projected_total, 2),
    }


def _parse_budget_amount(value) -> Optional[float]:
    """Parse a budget value into a float, tolerating currency formatting
    ("$1,200.00", "1,200") whether it arrived as a JSON number or string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_category_budgets(raw_json: Optional[str] = None) -> tuple:
    """Read per-category monthly budget targets from the CATEGORY_BUDGETS
    env var - a static JSON object mapping category name (matching the
    dashboard's own category names) to a monthly $ target, e.g.
    '{"Food and drink": 700, "Travel": 300}'. Values may be a plain
    number or a currency-formatted string ("$700.00").

    Set directly as an env var - locally in config/.env, or as a Render
    service env var - rather than fetched from anywhere live: these are
    meant to be static numbers set once and rarely changed, so there's
    no Sheets/network dependency to configure or fail.

    Entirely optional and silently absent (returns (None, None)) when
    CATEGORY_BUDGETS isn't set - the same way the Render resync silently
    no-ops when RENDER isn't set.

    Args:
        raw_json: Override for the env var's raw value (for tests).
            Defaults to the CATEGORY_BUDGETS env var.

    Returns:
        (budgets, error) - budgets is a {category: monthly_budget} dict,
        or None if not configured or nothing usable was found. error is
        None on success or when simply not configured, or a message
        string if CATEGORY_BUDGETS was set but couldn't be parsed -
        callers should degrade gracefully (hide the section, show the
        message) rather than crash on a malformed config value.
    """
    if raw_json is None:
        raw_json = os.environ.get(CATEGORY_BUDGETS_ENV_VAR)
    if not raw_json:
        return None, None

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        LOG.warning("%s isn't valid JSON: %s", CATEGORY_BUDGETS_ENV_VAR, e)
        return (
            None,
            f"{CATEGORY_BUDGETS_ENV_VAR} isn't valid JSON ({e}); budget-vs-actual hidden.",
        )

    if not isinstance(parsed, dict):
        return (
            None,
            f"{CATEGORY_BUDGETS_ENV_VAR} must be a JSON object of category -> "
            "budget amount; budget-vs-actual hidden.",
        )

    budgets = {}
    for category, value in parsed.items():
        amount = _parse_budget_amount(value)
        if amount is None:
            continue
        budgets[str(category).strip()] = amount

    return (budgets or None), None


def _normalize_category(name) -> str:
    """Case/whitespace-insensitive key so a hand-typed budget entry like
    "travel" or " Travel " still matches a real category recorded as
    "Travel" - a typed-in CATEGORY_BUDGETS value is far more typo-prone
    than the category names already flowing through the DB."""
    return str(name).strip().casefold()


def budget_vs_actual(df: pd.DataFrame, budgets: Optional[dict]) -> pd.DataFrame:
    """Actual spend vs. budget target, per category, for the most recent
    calendar month present in `df`.

    Budget category names are matched against real transaction categories
    case/whitespace-insensitively (see _normalize_category) - the
    displayed category name prefers the real transaction data's own
    casing, falling back to the budget dict's casing for a budgeted
    category with no matching spend this month (including a typo'd name
    that matches nothing at all).

    Args:
        df: Transactions DataFrame (from load_transactions_df) - whatever
            year/category filter is applied narrows both the month
            considered "current" and which categories have actual spend.
        budgets: {category: monthly_budget} dict, e.g. from
            load_category_budgets().

    Returns:
        DataFrame with [category, budget, actual, remaining, pct_used],
        sorted by pct_used desc (categories closest to or over budget
        first; categories with no budget target sort last, since
        pct_used is undefined without one). Empty if there's no data or
        no budgets configured.
    """
    columns = ["category", "budget", "actual", "remaining", "pct_used"]
    if df.empty or not budgets:
        return pd.DataFrame(columns=columns)

    current_month = df["date"].dt.to_period("M").max()
    month_df = df[df["date"].dt.to_period("M") == current_month]
    actual = month_df.groupby(month_df["category"].fillna(UNCATEGORIZED))[
        "amount"
    ].sum()

    budget_rows = {_normalize_category(k): (k, v) for k, v in budgets.items()}
    actual_rows = {_normalize_category(k): (k, v) for k, v in actual.items()}

    rows = []
    for key in sorted(set(budget_rows) | set(actual_rows)):
        budget_label, budget_amount = budget_rows.get(key, (None, None))
        actual_label, actual_amount = actual_rows.get(key, (None, 0.0))
        rows.append(
            {
                "category": actual_label or budget_label,
                "budget": budget_amount,
                "actual": actual_amount,
            }
        )

    result = pd.DataFrame(rows, columns=["category", "budget", "actual"])
    result["remaining"] = result["budget"] - result["actual"]
    result["pct_used"] = (result["actual"] / result["budget"] * 100).where(
        result["budget"].notna() & (result["budget"] != 0)
    )
    result = result.round(2)

    return result.sort_values("pct_used", ascending=False, na_position="last")[
        columns
    ].reset_index(drop=True)


def recent_years_range(
    years_back: int = RECENT_SYNC_YEARS_BACK, today: Optional[date] = None
) -> tuple:
    """(start_date, end_date) ISO strings covering the last `years_back`
    calendar years through today, inclusive.

    Used to bound how much history gets re-synced from Splitwise on a cold
    start - e.g. the dashboard's Render deployment, whose disk resets on
    every idle-timeout wake.

    Args:
        years_back: Number of calendar years to cover, including this one.
        today: Override for "today" (for tests). Defaults to date.today().

    Returns:
        (start_date, end_date) as ISO date strings.
    """
    today = today or date.today()
    start_year = today.year - (years_back - 1)
    return date(start_year, 1, 1).isoformat(), today.isoformat()


def sync_recent_years_if_on_render(
    years_back: int = RECENT_SYNC_YEARS_BACK,
    force: bool = False,
) -> Optional[str]:
    """On Render, live-resync the last `years_back` years from Splitwise
    before the dashboard reads the local DB - once per running container,
    not once per page load.

    Render's free tier wipes the container's disk on every idle-timeout
    wake, so without this the dashboard would come up empty until some
    other process re-syncs it. Bounded and not configurable on purpose:
    resyncing full history on every wake would be slow and needlessly
    API-heavy for what's usually a quick spending check.

    Results are cached for the lifetime of the process: each browser tab
    runs the notebook as its own independent session, so without this, a
    second tab (or a reconnect) would kick off a second concurrent sync
    against the same SQLite file - which previously caused a "UNIQUE
    constraint failed: transactions.splitwise_id" crash when two sessions
    both tried to insert the same not-yet-committed row. Pass `force=True`
    (e.g. from an explicit "reload" action) to bypass the cache and sync
    again.

    No-op locally, where RENDER isn't set - the dashboard just reads
    whatever's already in the local DB, as before.

    Args:
        years_back: Number of calendar years to sync, including this one.
        force: If True, sync again even if already done this process.

    Returns:
        None on success/skip/cache-hit; an error message string if the
        sync was attempted but failed - callers should fall back to
        whatever's already in the local DB rather than crashing on a
        transient Splitwise API/network failure.
    """
    global _render_sync_done, _render_sync_result

    if os.environ.get("RENDER") != "true":
        return None

    if _render_sync_done and not force:
        return _render_sync_result

    with _render_sync_lock:
        if _render_sync_done and not force:
            return _render_sync_result

        from src.db_sync.sync_from_splitwise import sync_from_splitwise

        start_date, end_date = recent_years_range(years_back)
        try:
            sync_from_splitwise(start_date=start_date, end_date=end_date, dry_run=False)
            _render_sync_result = None
        except Exception as e:  # noqa: BLE001 - any Splitwise/API/network failure
            LOG.warning("Render sync failed: %s", e)
            _render_sync_result = (
                f"Live sync failed ({e}); showing last available data."
            )

        _render_sync_done = True
        return _render_sync_result


# Process-lifetime state for start_history_sync(): like the cold-start sync
# above, one background sync per Render container, shared by every browser
# session (each of which only waits on _history_done).
_history_lock = threading.Lock()
_history_done = threading.Event()
_history_started = False
_history_error: Optional[str] = None


def history_years_range(
    years_back: int = RECENT_SYNC_YEARS_BACK, today: Optional[date] = None
) -> Optional[tuple]:
    """(start_date, end_date) of the years before this one, out of the last
    `years_back` - shown alongside this year's Expense Log, which only holds
    this year. None when `years_back` is just this year."""
    today = today or date.today()
    if years_back <= 1:
        return None
    return (
        date(today.year - (years_back - 1), 1, 1).isoformat(),
        date(today.year - 1, 12, 31).isoformat(),
    )


def _sync_history(years_back: int) -> None:
    global _history_error

    from src.db_sync.sync_from_splitwise import sync_from_splitwise

    start_date, end_date = history_years_range(years_back)
    try:
        sync_from_splitwise(start_date=start_date, end_date=end_date, dry_run=False)
    except Exception as e:  # noqa: BLE001 - any Splitwise/API/network failure
        LOG.warning("Background history sync failed: %s", e)
        _history_error = f"Earlier years failed to sync from Splitwise ({e})."
    finally:
        _history_done.set()


def start_history_sync(years_back: int = RECENT_SYNC_YEARS_BACK) -> threading.Event:
    """On Render, sync the years before this one from Splitwise into the
    local DB in a background thread, so the dashboard can show this year
    from the Expense Log right away and add the earlier years when they
    arrive. Starts once per process; later calls return the same event.

    Locally (RENDER unset) nothing is synced - the local DB is used as is,
    as in sync_recent_years_if_on_render().

    Returns:
        An event that's set once the earlier years are in the local DB (or
        the sync failed - see load_history_df()).
    """
    global _history_started

    with _history_lock:
        if not _history_started:
            _history_started = True
            if os.environ.get("RENDER") == "true" and history_years_range(years_back):
                threading.Thread(
                    target=_sync_history,
                    args=(years_back,),
                    name="history-sync",
                    daemon=True,
                ).start()
            else:
                _history_done.set()
    return _history_done


def load_history_df(
    years_back: int = RECENT_SYNC_YEARS_BACK, today: Optional[date] = None
) -> tuple[pd.DataFrame, Optional[str]]:
    """The years before this one from the local DB, for after
    start_history_sync() has finished.

    Returns:
        (transactions, error) - error is set if the sync or the read failed.
    """
    date_range = history_years_range(years_back, today)
    if date_range is None:
        return pd.DataFrame(), _history_error
    try:
        df = load_transactions_df(start_date=date_range[0], end_date=date_range[1])
    except Exception as e:  # noqa: BLE001 - e.g. an unreadable local DB
        LOG.warning("Couldn't read earlier years from the local DB: %s", e)
        return pd.DataFrame(), f"Couldn't read earlier years ({e})."
    return df, _history_error


def combine_with_history(
    sheet_df: pd.DataFrame, history_df: pd.DataFrame
) -> pd.DataFrame:
    """The Expense Log rows plus the earlier-years rows dated before the
    first of them, in the Expense Log's columns. Anything the sheets cover
    comes from the sheets, so nothing is counted twice."""
    if history_df.empty:
        return sheet_df

    history = history_df
    if not sheet_df.empty:
        history = history[history["date"] < sheet_df["date"].min()]
    history = history.reindex(columns=sheet_df.columns).assign(
        is_shared=history["is_shared"].fillna(False).astype(bool),
        splitwise_id=history["splitwise_id"].map(
            lambda value: "" if pd.isna(value) else str(int(value))
        ),
    )
    return (
        pd.concat([history, sheet_df], ignore_index=True)
        .sort_values("date")
        .reset_index(drop=True)
    )
