#!/usr/bin/env python3
"""Prints a CATEGORY_BUDGETS template: every category currently present in
the local transactions database, as JSON with $0 placeholder values -
paste the output, fill in real numbers, and set it as the CATEGORY_BUDGETS
env var for the spending dashboard's budget-vs-actual section (see
src/analytics/spending_analytics.py's load_category_budgets()).

Uses load_transactions_df(), the same category set (whitespace-stripped,
settlement rows excluded, missing category defaulted to "Uncategorized")
the dashboard itself displays under "Spend by Category" - so every name
printed here is guaranteed to match real data (case/whitespace-tolerant
matching in budget_vs_actual() forgives minor typos from there, but
starting from the real names avoids needing that at all).

Usage:
  python scripts/print_category_budgets_template.py
  python scripts/print_category_budgets_template.py --db-path data/transactions.db
"""

import argparse
import json

from src.analytics.spending_analytics import load_transactions_df


def main():
    parser = argparse.ArgumentParser(
        description="Print a CATEGORY_BUDGETS JSON template from the local DB"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the SQLite DB (default: data/transactions.db)",
    )
    args = parser.parse_args()

    df = load_transactions_df(db_path=args.db_path)
    if df.empty:
        print("No transactions found - run the sync pipeline first.")
        return

    categories = sorted(df["category"].unique())
    template = {category: 0 for category in categories}
    print(json.dumps(template, indent=2))


if __name__ == "__main__":
    main()
