from datetime import date

import pandas as pd
import pytest

from src.analytics.spending_analytics import (
    biggest_transactions,
    combine_with_history,
    history_years_range,
    load_history_df,
    start_history_sync,
    budget_vs_actual,
    category_breakdown,
    category_month_over_month_movers,
    detect_recurring_charges,
    expense_log_spreadsheet_keys,
    expense_log_to_transactions_df,
    load_dashboard_transactions,
    load_transactions_from_sheets,
    load_category_budgets,
    load_transactions_df,
    merchant_breakdown,
    monthly_trend,
    recent_years_range,
    shared_vs_personal_breakdown,
    spend_concentration,
    spending_pace_projection,
    sync_recent_years_if_on_render,
    weekly_trend,
)
from src.database.db_manager import DatabaseManager
from src.database.models import Transaction


def make_df(rows):
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if "category" not in df.columns:
        df["category"] = "Uncategorized"
    return df


# ── load_transactions_df ──────────────────────────────────────────────────


def create_txn(**kwargs):
    defaults = {"source": "splitwise", "imported_at": "2026-04-01T00:00:00Z"}
    defaults.update(kwargs)
    return Transaction(**defaults)


@pytest.fixture
def db_manager(tmp_path):
    return DatabaseManager(db_path=str(tmp_path / "test_transactions.db"))


def test_load_transactions_df_excludes_deleted_and_payments(db_manager):
    db_manager.insert_transactions_batch(
        [
            create_txn(
                date="2026-01-01", merchant="Coffee Shop", amount=5.0, category="Food"
            ),
            create_txn(
                date="2026-01-02",
                merchant="Settle all balances",
                amount=50.0,
                category="General",
            ),
            create_txn(
                date="2026-01-03",
                merchant="Deleted Expense",
                amount=20.0,
                splitwise_deleted_at="2026-01-04T00:00:00Z",
            ),
        ]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert len(df) == 1
    assert df.iloc[0]["merchant"] == "Coffee Shop"


def test_load_transactions_df_keeps_categorized_payment_named_expenses(db_manager):
    # A real, properly-categorized expense whose description happens to
    # contain the word "payment" (e.g. a recurring bill) must not be
    # treated as a Splitwise settlement record just because of that word -
    # only "General"-category payment-like rows are settlement records.
    db_manager.insert_transactions_batch(
        [
            create_txn(
                date="2026-01-01",
                merchant="Mortgage Payment",
                amount=2200.0,
                category="Mortgage",
            ),
            create_txn(
                date="2026-01-02",
                merchant="Car Payment",
                amount=350.0,
                category="Transportation",
            ),
        ]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert len(df) == 2
    assert set(df["merchant"]) == {"Mortgage Payment", "Car Payment"}


def test_load_transactions_df_excludes_general_category_payments(db_manager):
    db_manager.insert_transactions_batch(
        [
            create_txn(
                date="2026-01-01",
                merchant="Payment",
                amount=100.0,
                category="General",
            ),
            create_txn(
                date="2026-01-02",
                merchant="Mobile Payment Received",
                amount=50.0,
                category="General",
            ),
            create_txn(
                date="2026-01-03",
                merchant="Coffee Shop",
                amount=5.0,
                category="Food",
            ),
        ]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert len(df) == 1
    assert df.iloc[0]["merchant"] == "Coffee Shop"


def test_load_transactions_df_date_range_filter(db_manager):
    db_manager.insert_transactions_batch(
        [
            create_txn(date="2026-01-01", merchant="A", amount=5.0),
            create_txn(date="2026-06-01", merchant="B", amount=5.0),
        ]
    )

    df = load_transactions_df(
        db_path=db_manager.db_path, start_date="2026-05-01", end_date="2026-12-31"
    )

    assert len(df) == 1
    assert df.iloc[0]["merchant"] == "B"


def test_load_transactions_df_defaults_missing_category(db_manager):
    db_manager.insert_transactions_batch(
        [create_txn(date="2026-01-01", merchant="A", amount=5.0)]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert df.iloc[0]["category"] == "Uncategorized"


def test_load_transactions_df_strips_whitespace_from_category_and_merchant(db_manager):
    # A stray leading/trailing space (e.g. "Rent " vs "Rent") must not
    # create a duplicate-looking row downstream - the DB schema doesn't
    # enforce trimmed values.
    db_manager.insert_transactions_batch(
        [
            create_txn(
                date="2026-01-01", merchant=" Landlord ", amount=2000.0, category="Rent"
            ),
            create_txn(
                date="2026-02-01",
                merchant="Landlord",
                amount=2000.0,
                category="Rent ",
            ),
        ]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert set(df["merchant"]) == {"Landlord"}
    assert set(df["category"]) == {"Rent"}

    breakdown = category_breakdown(df)
    assert len(breakdown) == 1
    assert breakdown.iloc[0]["category"] == "Rent"
    assert breakdown.iloc[0]["total"] == 4000.0


def test_load_transactions_df_empty_db_returns_empty(db_manager):
    df = load_transactions_df(db_path=db_manager.db_path)
    assert df.empty


def test_load_transactions_df_uses_my_owed_not_my_net_for_amount(db_manager):
    # amount stores my_net (my_paid - my_owed), which goes negative for a
    # shared expense your partner paid - even though your real share
    # (my_owed) is a positive spend. The loaded `amount` must reflect
    # my_owed, recovered from notes, not the DB's raw my_net value.
    db_manager.insert_transactions_batch(
        [
            create_txn(
                date="2026-01-01",
                merchant="Dinner",
                amount=-50.0,  # my_net stored in the DB: partner paid, I owe $50
                is_shared=True,
                notes="Paid: $0.00 | Owe: $50.00",
            ),
        ]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert df.iloc[0]["amount"] == 50.0


def test_load_transactions_df_falls_back_to_50_50_split_when_no_notes(db_manager):
    db_manager.insert_transactions_batch(
        [
            create_txn(
                date="2026-01-01",
                merchant="Dinner",
                amount=40.0,
                raw_amount=80.0,
                is_shared=True,
            ),
        ]
    )

    df = load_transactions_df(db_path=db_manager.db_path)

    assert df.iloc[0]["amount"] == 40.0


# ── category_breakdown ────────────────────────────────────────────────────


def test_category_breakdown_totals_and_pct():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 30.0, "category": "Food"},
            {"date": "2026-01-02", "amount": 10.0, "category": "Food"},
            {"date": "2026-01-03", "amount": 60.0, "category": "Transport"},
        ]
    )

    result = category_breakdown(df)

    assert list(result["category"]) == ["Transport", "Food"]
    assert result.iloc[0]["total"] == 60.0
    assert result.iloc[1]["total"] == 40.0
    assert result.iloc[0]["pct_of_total"] == 60.0
    assert result.iloc[1]["pct_of_total"] == 40.0


def test_category_breakdown_empty_df():
    result = category_breakdown(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["category", "total", "count", "pct_of_total"]


def test_category_breakdown_pct_not_inflated_by_refund_in_other_category():
    # A large refund/credit in one category (net negative) must not shrink
    # the denominator for every other category's percentage - previously
    # pct_of_total divided by the net sum across all categories, so a big
    # refund elsewhere could push an unrelated category's share past 100%.
    df = make_df(
        [
            {"date": "2025-01-01", "amount": 24000.0, "category": "Rent"},
            {"date": "2025-02-01", "amount": -20000.0, "category": "Travel"},
        ]
    )

    result = category_breakdown(df)

    rent_pct = result[result["category"] == "Rent"]["pct_of_total"].iloc[0]
    assert rent_pct == pytest.approx(100.0)
    assert (result["pct_of_total"] <= 100.0).all()


# ── merchant_breakdown ────────────────────────────────────────────────────


def test_merchant_breakdown_top_n():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 5.0, "merchant": "A"},
            {"date": "2026-01-02", "amount": 100.0, "merchant": "B"},
            {"date": "2026-01-03", "amount": 20.0, "merchant": "C"},
        ]
    )

    result = merchant_breakdown(df, top_n=2)

    assert len(result) == 2
    assert list(result["merchant"]) == ["B", "C"]


# ── monthly_trend ──────────────────────────────────────────────────────────


def test_monthly_trend_mom_and_yoy():
    df = make_df(
        [
            {"date": "2025-01-15", "amount": 100.0},
            {"date": "2026-01-15", "amount": 150.0},
            {"date": "2026-02-15", "amount": 300.0},
        ]
    )

    result = monthly_trend(df)

    assert len(result) == 14  # zero-filled from 2025-01 through 2026-02
    jan_2026 = result[result["year_month"] == pd.Period("2026-01", freq="M")].iloc[0]
    feb_2026 = result[result["year_month"] == pd.Period("2026-02", freq="M")].iloc[0]
    assert jan_2026["yoy_pct"] == 50.0
    assert feb_2026["mom_pct"] == 100.0


# ── weekly_trend ───────────────────────────────────────────────────────────


def test_weekly_trend_fills_gaps_with_zero():
    df = make_df(
        [
            {"date": "2026-01-05", "amount": 10.0},  # week 1
            {"date": "2026-01-19", "amount": 20.0},  # week 3, skipping week 2
        ]
    )

    result = weekly_trend(df)

    assert len(result) == 3
    assert result["total"].tolist() == [10.0, 0, 20.0]


def test_weekly_trend_empty_df():
    result = weekly_trend(pd.DataFrame())
    assert result.empty


# ── detect_recurring_charges ────────────────────────────────────────────────


def test_detect_recurring_charges_flags_stable_monthly_merchant():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-02-01", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-03-03", "amount": 15.99, "merchant": "Streaming Co"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3)

    assert len(result) == 1
    assert result.iloc[0]["merchant"] == "Streaming Co"
    assert result.iloc[0]["cadence"] == "monthly"
    assert result.iloc[0]["estimated_monthly_cost"] == 15.99


def test_detect_recurring_charges_ignores_irregular_merchant():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 15.99, "merchant": "Random Store"},
            {"date": "2026-01-05", "amount": 42.10, "merchant": "Random Store"},
            {"date": "2026-03-20", "amount": 3.50, "merchant": "Random Store"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3)

    assert result.empty


def test_detect_recurring_charges_requires_min_occurrences():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-02-01", "amount": 15.99, "merchant": "Streaming Co"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3)

    assert result.empty


def test_detect_recurring_charges_normalizes_merchant_case_and_whitespace():
    # Splitwise re-syncing a merchant under a slightly different spelling
    # (e.g. "Fastrak Csc Tolls" -> "FasTrak") must not split one recurring
    # charge across variants that individually never reach min_occurrences.
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 9.99, "merchant": "netflix"},
            {"date": "2026-02-01", "amount": 9.99, "merchant": "Netflix"},
            {"date": "2026-03-03", "amount": 9.99, "merchant": " NETFLIX "},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3)

    assert len(result) == 1
    # Most recent occurrence's own spelling is used for display.
    assert result.iloc[0]["merchant"] == " NETFLIX "


def test_detect_recurring_charges_detects_quarterly_cadence():
    from datetime import date, timedelta

    start = date(2026, 1, 1)
    df = make_df(
        [
            {"date": str(start), "amount": 30.0, "merchant": "Quarterly Box"},
            {
                "date": str(start + timedelta(days=90)),
                "amount": 30.0,
                "merchant": "Quarterly Box",
            },
            {
                "date": str(start + timedelta(days=180)),
                "amount": 30.0,
                "merchant": "Quarterly Box",
            },
        ]
    )

    result = detect_recurring_charges(df)

    assert len(result) == 1
    assert result.iloc[0]["cadence"] == "quarterly"
    assert result.iloc[0]["estimated_monthly_cost"] == pytest.approx(10.0)


def test_detect_recurring_charges_detects_annual_cadence_with_two_occurrences():
    from datetime import date, timedelta

    start = date(2025, 1, 1)
    df = make_df(
        [
            {"date": str(start), "amount": 120.0, "merchant": "Domain Registrar"},
            {
                "date": str(start + timedelta(days=365)),
                "amount": 120.0,
                "merchant": "Domain Registrar",
            },
        ]
    )

    # No min_occurrences override - annual's own default (2) applies.
    result = detect_recurring_charges(df)

    assert len(result) == 1
    assert result.iloc[0]["cadence"] == "annual"
    assert result.iloc[0]["occurrences"] == 2
    assert result.iloc[0]["estimated_monthly_cost"] == pytest.approx(10.0)


def test_detect_recurring_charges_rejects_weekly_cadence():
    # Deliberately not a supported cadence - a ~weekly gap must not match
    # any recognized window (monthly/quarterly/annual).
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 12.0, "merchant": "Weekly Thing"},
            {"date": "2026-01-08", "amount": 12.0, "merchant": "Weekly Thing"},
            {"date": "2026-01-15", "amount": 12.0, "merchant": "Weekly Thing"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3)

    assert result.empty


def test_detect_recurring_charges_tolerates_one_price_change():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-02-01", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-03-03", "amount": 17.99, "merchant": "Streaming Co"},
            {"date": "2026-04-02", "amount": 17.99, "merchant": "Streaming Co"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=4)

    assert len(result) == 1
    # Reflects the current (most recent) price, not a blend of both.
    assert result.iloc[0]["estimated_monthly_cost"] == 17.99


def test_detect_recurring_charges_reflects_a_price_decrease():
    # A price cut (promo ending, plan downgrade) must read as the new
    # lower price - not the old higher one, just because sorting the
    # amounts ascending happens to put the higher price last.
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 20.00, "merchant": "Streaming Co"},
            {"date": "2026-02-01", "amount": 20.00, "merchant": "Streaming Co"},
            {"date": "2026-03-03", "amount": 12.00, "merchant": "Streaming Co"},
            {"date": "2026-04-02", "amount": 12.00, "merchant": "Streaming Co"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=4)

    assert len(result) == 1
    assert result.iloc[0]["estimated_monthly_cost"] == 12.00


def test_detect_recurring_charges_rejects_too_many_price_tiers():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 10.0, "merchant": "Erratic Co"},
            {"date": "2026-02-01", "amount": 20.0, "merchant": "Erratic Co"},
            {"date": "2026-03-03", "amount": 30.0, "merchant": "Erratic Co"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3, max_price_tiers=2)

    assert result.empty


def test_detect_recurring_charges_median_gap_tolerates_a_skewed_pair():
    # Only 3 occurrences means only 2 gaps (20 and 40 days) - neither
    # individually falls in the old strict [25, 35] monthly window (the
    # old implementation would have rejected this outright), but their
    # median (30) does, and both sit within a reasonable spread of it.
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-01-21", "amount": 15.99, "merchant": "Streaming Co"},
            {"date": "2026-03-02", "amount": 15.99, "merchant": "Streaming Co"},
        ]
    )

    result = detect_recurring_charges(df, min_occurrences=3)

    assert len(result) == 1
    assert result.iloc[0]["cadence"] == "monthly"


# ── spend_concentration ─────────────────────────────────────────────────────


def test_spend_concentration_by_merchant():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 80.0, "merchant": "A"},
            {"date": "2026-01-02", "amount": 10.0, "merchant": "B"},
            {"date": "2026-01-03", "amount": 10.0, "merchant": "C"},
        ]
    )

    result = spend_concentration(df, by="merchant", top_n=1)

    assert result["top_total"] == 80.0
    assert result["total_spend"] == 100.0
    assert result["pct_of_total"] == 80.0
    assert len(result["groups"]) == 1


def test_spend_concentration_empty_df():
    result = spend_concentration(pd.DataFrame(), by="merchant", top_n=5)
    assert result["total_spend"] == 0.0
    assert result["pct_of_total"] == 0.0


# ── biggest_transactions ──────────────────────────────────────────────────


def test_biggest_transactions_sorted_desc_and_excludes_refunds():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 30.0, "merchant": "A"},
            {"date": "2026-01-02", "amount": 500.0, "merchant": "B"},
            {"date": "2026-01-03", "amount": -80.0, "merchant": "Refund"},
        ]
    )

    result = biggest_transactions(df, top_n=2)

    assert list(result["merchant"]) == ["B", "A"]
    assert len(result) == 2


def test_biggest_transactions_empty_df():
    result = biggest_transactions(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["date", "merchant", "category", "amount"]


# ── shared_vs_personal_breakdown ──────────────────────────────────────────


def test_shared_vs_personal_breakdown_splits_by_is_shared():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 60.0, "is_shared": True},
            {"date": "2026-01-02", "amount": 40.0, "is_shared": False},
        ]
    )

    result = shared_vs_personal_breakdown(df)

    assert result["shared_total"] == 60.0
    assert result["personal_total"] == 40.0
    assert result["shared_pct"] == 60.0
    assert result["personal_pct"] == 40.0
    assert result["shared_count"] == 1
    assert result["personal_count"] == 1


def test_shared_vs_personal_breakdown_empty_df():
    result = shared_vs_personal_breakdown(pd.DataFrame())
    assert result["shared_total"] == 0.0
    assert result["personal_pct"] == 0.0


# ── category_month_over_month_movers ──────────────────────────────────────


def test_category_month_over_month_movers_ranks_by_absolute_delta():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 100.0, "category": "Food"},
            {"date": "2026-02-01", "amount": 150.0, "category": "Food"},
            {"date": "2026-01-05", "amount": 50.0, "category": "Travel"},
            {"date": "2026-02-05", "amount": 10.0, "category": "Travel"},
            {"date": "2026-02-10", "amount": 20.0, "category": "New Category"},
        ]
    )

    result = category_month_over_month_movers(df, top_n=5)

    assert list(result["category"]) == ["Food", "Travel", "New Category"]
    travel = result[result["category"] == "Travel"].iloc[0]
    assert travel["delta"] == -40.0
    assert travel["delta_pct"] == -80.0
    new_cat = result[result["category"] == "New Category"].iloc[0]
    assert new_cat["prior_total"] == 0.0
    assert pd.isna(new_cat["delta_pct"])


def test_category_month_over_month_movers_requires_two_months():
    df = make_df([{"date": "2026-01-01", "amount": 100.0, "category": "Food"}])
    result = category_month_over_month_movers(df)
    assert result.empty


def test_category_month_over_month_movers_empty_df():
    result = category_month_over_month_movers(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == [
        "category",
        "current_total",
        "prior_total",
        "delta",
        "delta_pct",
    ]


# ── spending_pace_projection ────────────────────────────────────────────


def test_spending_pace_projection_extrapolates_linearly():
    df = make_df(
        [
            {"date": "2026-01-01", "amount": 100.0},
            {"date": "2026-01-10", "amount": 100.0},
        ]
    )

    result = spending_pace_projection(df, today=date(2026, 1, 10))

    assert result["year"] == 2026
    assert result["days_elapsed"] == 10
    assert result["total_so_far"] == 200.0
    assert result["daily_rate"] == pytest.approx(20.0)
    assert result["projected_total"] == pytest.approx(20.0 * 365)


def test_spending_pace_projection_none_when_year_complete():
    df = make_df([{"date": "2026-06-01", "amount": 100.0}])
    result = spending_pace_projection(df, today=date(2026, 12, 31))
    assert result is None


def test_spending_pace_projection_none_when_no_data_this_year():
    df = make_df([{"date": "2025-06-01", "amount": 100.0}])
    result = spending_pace_projection(df, today=date(2026, 6, 1))
    assert result is None


def test_spending_pace_projection_none_for_empty_df():
    result = spending_pace_projection(pd.DataFrame(), today=date(2026, 6, 1))
    assert result is None


# ── load_category_budgets ──────────────────────────────────────────────────


def test_load_category_budgets_not_configured_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("CATEGORY_BUDGETS", raising=False)

    budgets, error = load_category_budgets()

    assert budgets is None
    assert error is None


def test_load_category_budgets_not_configured_when_env_var_empty(monkeypatch):
    monkeypatch.setenv("CATEGORY_BUDGETS", "")

    budgets, error = load_category_budgets()

    assert budgets is None
    assert error is None


def test_load_category_budgets_parses_json_object():
    budgets, error = load_category_budgets(
        raw_json='{"Food and drink": 800, "Travel": "$1,200.00"}'
    )

    assert error is None
    assert budgets == {"Food and drink": 800.0, "Travel": 1200.0}


def test_load_category_budgets_skips_unparseable_values():
    budgets, error = load_category_budgets(
        raw_json='{"Food and drink": 800, "Bogus": "not a number"}'
    )

    assert error is None
    assert budgets == {"Food and drink": 800.0}


def test_load_category_budgets_invalid_json_returns_error():
    budgets, error = load_category_budgets(raw_json="{not valid json")

    assert budgets is None
    assert "isn't valid JSON" in error


def test_load_category_budgets_non_object_json_returns_error():
    budgets, error = load_category_budgets(raw_json='["Food and drink", 800]')

    assert budgets is None
    assert "must be a JSON object" in error


# ── budget_vs_actual ─────────────────────────────────────────────────────


def test_budget_vs_actual_computes_remaining_and_pct():
    df = make_df(
        [
            {"date": "2026-02-01", "amount": 600.0, "category": "Food"},
            {"date": "2026-02-10", "amount": 100.0, "category": "Food"},
            {"date": "2026-01-01", "amount": 999.0, "category": "Food"},
        ]
    )

    result = budget_vs_actual(df, {"Food": 800.0})

    row = result[result["category"] == "Food"].iloc[0]
    assert row["budget"] == 800.0
    assert row["actual"] == 700.0
    assert row["remaining"] == 100.0
    assert row["pct_used"] == pytest.approx(87.5)


def test_budget_vs_actual_includes_actual_only_category_with_no_budget():
    df = make_df(
        [
            {"date": "2026-02-01", "amount": 50.0, "category": "Food"},
            {"date": "2026-02-02", "amount": 200.0, "category": "Surprise"},
        ]
    )

    result = budget_vs_actual(df, {"Food": 100.0})

    surprise = result[result["category"] == "Surprise"].iloc[0]
    assert pd.isna(surprise["budget"])
    assert surprise["actual"] == 200.0
    assert pd.isna(surprise["pct_used"])
    # Categories with no budget target sort last (undefined pct_used).
    assert result.iloc[-1]["category"] == "Surprise"


def test_budget_vs_actual_budgeted_category_with_no_spend_shows_zero_actual():
    df = make_df([{"date": "2026-02-01", "amount": 50.0, "category": "Food"}])

    result = budget_vs_actual(df, {"Food": 100.0, "Travel": 300.0})

    travel = result[result["category"] == "Travel"].iloc[0]
    assert travel["actual"] == 0.0
    assert travel["pct_used"] == 0.0


def test_budget_vs_actual_matches_case_insensitively():
    df = make_df([{"date": "2026-02-01", "amount": 50.0, "category": "Food and drink"}])

    result = budget_vs_actual(df, {"food AND drink": 100.0})

    row = result.iloc[0]
    # Real transaction category's own casing wins for display.
    assert row["category"] == "Food and drink"
    assert row["budget"] == 100.0
    assert row["actual"] == 50.0


def test_budget_vs_actual_matches_whitespace_tolerantly():
    df = make_df([{"date": "2026-02-01", "amount": 50.0, "category": "Travel"}])

    result = budget_vs_actual(df, {" Travel  ": 300.0})

    row = result.iloc[0]
    assert row["category"] == "Travel"
    assert row["budget"] == 300.0
    assert row["actual"] == 50.0


def test_budget_vs_actual_typo_budget_falls_back_to_budget_dict_casing():
    df = make_df([{"date": "2026-02-01", "amount": 50.0, "category": "Food"}])

    result = budget_vs_actual(df, {"Fod": 100.0})

    # No real category matches "Fod" - it shows up under its own (typo'd)
    # spelling with $0 actual, rather than silently vanishing.
    typo_row = result[result["category"] == "Fod"].iloc[0]
    assert typo_row["actual"] == 0.0
    assert typo_row["budget"] == 100.0


def test_budget_vs_actual_empty_when_no_budgets():
    df = make_df([{"date": "2026-02-01", "amount": 50.0, "category": "Food"}])
    result = budget_vs_actual(df, None)
    assert result.empty


def test_budget_vs_actual_empty_df():
    result = budget_vs_actual(pd.DataFrame(), {"Food": 100.0})
    assert result.empty
    assert list(result.columns) == [
        "category",
        "budget",
        "actual",
        "remaining",
        "pct_used",
    ]


# ── recent_years_range ──────────────────────────────────────────────────────


def test_recent_years_range_spans_years_back_through_today():
    start, end = recent_years_range(years_back=3, today=date(2026, 6, 15))

    assert start == "2024-01-01"
    assert end == "2026-06-15"


def test_recent_years_range_single_year():
    start, end = recent_years_range(years_back=1, today=date(2026, 6, 15))

    assert start == "2026-01-01"
    assert end == "2026-06-15"


# ── sync_recent_years_if_on_render ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_render_sync_cache():
    """sync_recent_years_if_on_render caches its result at module scope for
    the process lifetime (see its docstring) - reset that state before and
    after every test so tests don't leak into each other.
    """
    import src.analytics.spending_analytics as sa

    sa._render_sync_done = False
    sa._render_sync_result = None
    yield
    sa._render_sync_done = False
    sa._render_sync_result = None


def test_sync_recent_years_if_on_render_noop_when_not_on_render(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)

    result = sync_recent_years_if_on_render()

    assert result is None


def test_sync_recent_years_if_on_render_calls_sync_when_on_render(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    calls = {}

    def fake_sync(start_date, end_date, dry_run):
        calls["start_date"] = start_date
        calls["end_date"] = end_date
        calls["dry_run"] = dry_run
        return {"updated": 0, "inserted": 0, "marked_deleted": 0}

    monkeypatch.setattr(
        "src.db_sync.sync_from_splitwise.sync_from_splitwise", fake_sync
    )

    result = sync_recent_years_if_on_render(years_back=3)

    assert result is None
    assert calls["dry_run"] is False
    assert calls["start_date"] and calls["end_date"]


def test_sync_recent_years_if_on_render_returns_error_message_on_failure(monkeypatch):
    monkeypatch.setenv("RENDER", "true")

    def failing_sync(**kwargs):
        raise RuntimeError("Splitwise API unavailable")

    monkeypatch.setattr(
        "src.db_sync.sync_from_splitwise.sync_from_splitwise", failing_sync
    )

    result = sync_recent_years_if_on_render()

    assert result is not None
    assert "Splitwise API unavailable" in result


def test_sync_recent_years_if_on_render_caches_within_process(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    call_count = {"n": 0}

    def fake_sync(**kwargs):
        call_count["n"] += 1
        return {"updated": 0, "inserted": 0, "marked_deleted": 0}

    monkeypatch.setattr(
        "src.db_sync.sync_from_splitwise.sync_from_splitwise", fake_sync
    )

    sync_recent_years_if_on_render()
    sync_recent_years_if_on_render()
    sync_recent_years_if_on_render()

    assert call_count["n"] == 1


def test_sync_recent_years_if_on_render_force_bypasses_cache(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    call_count = {"n": 0}

    def fake_sync(**kwargs):
        call_count["n"] += 1
        return {"updated": 0, "inserted": 0, "marked_deleted": 0}

    monkeypatch.setattr(
        "src.db_sync.sync_from_splitwise.sync_from_splitwise", fake_sync
    )

    sync_recent_years_if_on_render()
    sync_recent_years_if_on_render(force=True)

    assert call_count["n"] == 2


# ── Expense Log (Google Sheets) source ────────────────────────────────────


def expense_log(rows):
    """Rows as read_from_sheets(numerize=False) returns them: formatted text."""
    columns = [
        "Date",
        "Amount",
        "Category",
        "Description",
        "Details",
        "Split Type",
        "Participant Names",
        "My Paid",
        "My Owed",
        "My Net",
        "Splitwise ID",
        "Transaction Fingerprint",
    ]
    return pd.DataFrame([dict(zip(columns, row)) for row in rows], columns=columns)


def test_expense_log_spreadsheet_keys(monkeypatch):
    monkeypatch.setenv("EXPENSE_LOG_SPREADSHEET_KEYS", " key2026 , ,key2025")
    assert expense_log_spreadsheet_keys() == ["key2026", "key2025"]
    monkeypatch.delenv("EXPENSE_LOG_SPREADSHEET_KEYS")
    assert expense_log_spreadsheet_keys() == []


def test_expense_log_to_transactions_df_maps_my_owed_and_split_type():
    log = expense_log(
        [
            [
                "2026-03-02",
                "$100.00",
                "Groceries",
                "Safeway",
                "",
                "split",
                "Me, Partner",
                "$100.00",
                "$50.00",
                "$50.00",
                "11",
                "fp1",
            ],
            [
                "2026-03-01",
                "$1,200.00",
                "Rent",
                " Rent ",
                "",
                "self",
                "Me",
                "$1,200.00",
                "$1,200.00",
                "$0.00",
                "12",
                "fp2",
            ],
            [
                "2026-03-03",
                "-$20.00",
                "",
                "Amazon refund",
                "",
                "split",
                "Me, Partner",
                "-$20.00",
                "($10.00)",
                "-$10.00",
                "13",
                "fp3",
            ],
            [
                "2026-03-04",
                "$30.00",
                "General",
                "Settle all balances",
                "",
                "split",
                "",
                "$30.00",
                "$0.00",
                "$30.00",
                "14",
                "fp4",
            ],
            [
                "",
                "$5.00",
                "Dining",
                "Blank date",
                "",
                "self",
                "",
                "$5.00",
                "$5.00",
                "$0.00",
                "15",
                "fp5",
            ],
        ]
    )

    df = expense_log_to_transactions_df(log)

    assert df["merchant"].tolist() == ["Rent", "Safeway", "Amazon refund"]
    assert df["amount"].tolist() == [1200.0, 50.0, -10.0]
    assert df["is_shared"].tolist() == [False, True, True]
    assert df["category"].tolist() == ["Rent", "Groceries", "Uncategorized"]
    assert df["splitwise_id"].tolist() == ["12", "11", "13"]
    assert df["date"].dtype.kind == "M"


def test_expense_log_to_transactions_df_empty():
    assert expense_log_to_transactions_df(None).empty


def test_expense_log_rows_work_with_analytics():
    log = expense_log(
        [
            [
                "2026-01-05",
                "$10.00",
                "Dining",
                "Cafe",
                "",
                "self",
                "",
                "$10.00",
                "$10.00",
                "$0.00",
                "1",
                "",
            ],
            [
                "2026-02-05",
                "$40.00",
                "Dining",
                "Cafe",
                "",
                "split",
                "",
                "$40.00",
                "$20.00",
                "$20.00",
                "2",
                "",
            ],
        ]
    )
    df = expense_log_to_transactions_df(log)

    assert category_breakdown(df)["total"].tolist() == [30.0]
    assert monthly_trend(df)["total"].tolist() == [10.0, 20.0]
    assert shared_vs_personal_breakdown(df)["shared_total"] == 20.0


def test_load_transactions_from_sheets_combines_and_dedupes(monkeypatch):
    sheets = {
        "k2026": expense_log(
            [
                [
                    "2026-01-05",
                    "$10.00",
                    "Dining",
                    "Cafe",
                    "",
                    "self",
                    "",
                    "$10.00",
                    "$10.00",
                    "$0.00",
                    "1",
                    "",
                ]
            ]
        ),
        "k2025": expense_log(
            [
                [
                    "2025-12-30",
                    "$8.00",
                    "Dining",
                    "Bar",
                    "",
                    "self",
                    "",
                    "$8.00",
                    "$8.00",
                    "$0.00",
                    "0",
                    "",
                ],
                [
                    "2026-01-05",
                    "$10.00",
                    "Dining",
                    "Cafe",
                    "",
                    "self",
                    "",
                    "$10.00",
                    "$10.00",
                    "$0.00",
                    "1",
                    "",
                ],
            ]
        ),
    }

    def fake_read(key, worksheet_name, numerize=False):
        assert worksheet_name == "Expense Log"
        if key == "broken":
            raise RuntimeError("no access")
        return sheets[key]

    monkeypatch.setattr("src.common.sheets_sync.read_from_sheets", fake_read)

    df, error = load_transactions_from_sheets(["k2026", "broken", "k2025"])

    assert df["merchant"].tolist() == ["Bar", "Cafe"]
    assert "broken: no access" in error


def test_load_transactions_from_sheets_all_failed(monkeypatch):
    def fake_read(key, worksheet_name, numerize=False):
        raise RuntimeError("offline")

    monkeypatch.setattr("src.common.sheets_sync.read_from_sheets", fake_read)

    df, error = load_transactions_from_sheets(["k"])

    assert df.empty
    assert "offline" in error


def test_load_dashboard_transactions_prefers_sheet(monkeypatch):
    monkeypatch.setenv("EXPENSE_LOG_SPREADSHEET_KEYS", "k")
    monkeypatch.setattr(
        "src.analytics.spending_analytics.load_transactions_from_sheets",
        lambda keys: (pd.DataFrame({"keys": keys}), None),
    )

    def no_sync(**_):
        raise AssertionError("must not sync from Splitwise")

    monkeypatch.setattr(
        "src.analytics.spending_analytics.sync_recent_years_if_on_render", no_sync
    )

    df, error = load_dashboard_transactions()

    assert df["keys"].tolist() == ["k"]
    assert error is None


def test_load_dashboard_transactions_falls_back_to_db(monkeypatch):
    monkeypatch.delenv("EXPENSE_LOG_SPREADSHEET_KEYS", raising=False)
    monkeypatch.setattr(
        "src.analytics.spending_analytics.sync_recent_years_if_on_render",
        lambda force: "sync failed" if force else None,
    )
    monkeypatch.setattr(
        "src.analytics.spending_analytics.load_transactions_df",
        lambda: pd.DataFrame({"x": [1]}),
    )

    df, error = load_dashboard_transactions(force=True)

    assert df["x"].tolist() == [1]
    assert error == "sync failed"


# ── Earlier years in the background (sheet mode) ──────────────────────────


@pytest.fixture
def reset_history_sync():
    """start_history_sync() runs once per process (see its docstring)."""
    import threading

    import src.analytics.spending_analytics as sa

    def reset():
        sa._history_done = threading.Event()
        sa._history_started = False
        sa._history_error = None

    reset()
    yield
    reset()


def test_history_years_range():
    assert history_years_range(years_back=3, today=date(2026, 6, 15)) == (
        "2024-01-01",
        "2025-12-31",
    )
    assert history_years_range(years_back=1, today=date(2026, 6, 15)) is None


def test_start_history_sync_skips_sync_locally(monkeypatch, reset_history_sync):
    monkeypatch.delenv("RENDER", raising=False)

    def no_sync(**_):
        raise AssertionError("must not sync locally")

    monkeypatch.setattr("src.db_sync.sync_from_splitwise.sync_from_splitwise", no_sync)

    assert start_history_sync().is_set()


def test_start_history_sync_syncs_earlier_years_once(monkeypatch, reset_history_sync):
    monkeypatch.setenv("RENDER", "true")
    calls = []
    monkeypatch.setattr(
        "src.db_sync.sync_from_splitwise.sync_from_splitwise",
        lambda **kwargs: calls.append(kwargs),
    )

    done = start_history_sync(years_back=2)
    assert done.wait(timeout=5)
    assert start_history_sync(years_back=2) is done

    year = date.today().year
    assert calls == [
        {
            "start_date": f"{year - 1}-01-01",
            "end_date": f"{year - 1}-12-31",
            "dry_run": False,
        }
    ]


def test_start_history_sync_failure_reported_by_load_history_df(
    monkeypatch, reset_history_sync
):
    monkeypatch.setenv("RENDER", "true")

    def failing_sync(**_):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(
        "src.db_sync.sync_from_splitwise.sync_from_splitwise", failing_sync
    )
    monkeypatch.setattr(
        "src.analytics.spending_analytics.load_transactions_df",
        lambda **_: pd.DataFrame(),
    )

    assert start_history_sync(years_back=2).wait(timeout=5)
    df, error = load_history_df(years_back=2)

    assert df.empty
    assert "rate limited" in error


def test_load_history_df_reads_earlier_years(monkeypatch, reset_history_sync):
    seen = {}

    def fake_load(**kwargs):
        seen.update(kwargs)
        return pd.DataFrame({"x": [1]})

    monkeypatch.setattr(
        "src.analytics.spending_analytics.load_transactions_df", fake_load
    )

    df, error = load_history_df(years_back=2, today=date(2026, 6, 15))

    assert seen == {"start_date": "2025-01-01", "end_date": "2025-12-31"}
    assert df["x"].tolist() == [1]
    assert error is None


def test_combine_with_history_keeps_sheet_rows_and_earlier_history():
    sheet = expense_log_to_transactions_df(
        expense_log(
            [
                [
                    "2026-01-02",
                    "$10.00",
                    "Dining",
                    "Cafe",
                    "",
                    "self",
                    "",
                    "$10.00",
                    "$10.00",
                    "$0.00",
                    "3",
                    "",
                ],
            ]
        )
    )
    history = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-12-30", "2026-01-02"]),
            "merchant": ["Bar", "Cafe"],
            "description": ["Bar", "Cafe"],
            "category": ["Dining", "Dining"],
            "amount": [8.0, 10.0],
            "is_shared": [1, 0],
            "splitwise_id": [2.0, 3.0],
            "notes": ["x", "y"],
        }
    )

    df = combine_with_history(sheet, history)

    assert df["merchant"].tolist() == ["Bar", "Cafe"]
    assert df["is_shared"].tolist() == [True, False]
    assert df["splitwise_id"].tolist() == ["2", "3"]
    assert list(df.columns) == list(sheet.columns)


def test_combine_with_history_without_history():
    sheet = expense_log_to_transactions_df(None)
    assert combine_with_history(sheet, pd.DataFrame()) is sheet
