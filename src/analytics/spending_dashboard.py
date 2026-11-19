import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def __():
    import marimo as mo
    import pandas as pd

    try:
        # Normal local/CI usage: repo root is on sys.path.
        from src.analytics.spending_analytics import (
            category_breakdown,
            merchant_breakdown,
            monthly_trend,
            weekly_trend,
            detect_recurring_charges,
            spend_concentration,
            load_dashboard_transactions,
            expense_log_spreadsheet_keys,
            start_history_sync,
            load_history_df,
            combine_with_history,
            biggest_transactions,
            shared_vs_personal_breakdown,
            category_month_over_month_movers,
            spending_pace_projection,
            load_category_budgets,
            budget_vs_actual,
        )
    except ModuleNotFoundError:
        # marimo's html-wasm export bundles each notebook-local import as its
        # own top-level wheel rooted at src/'s *contents*, not "src" itself
        # (see marimo's local_modules.py) - so under Pyodide these are
        # importable without the "src." prefix instead.
        from analytics.spending_analytics import (
            category_breakdown,
            merchant_breakdown,
            monthly_trend,
            weekly_trend,
            detect_recurring_charges,
            spend_concentration,
            load_dashboard_transactions,
            expense_log_spreadsheet_keys,
            start_history_sync,
            load_history_df,
            combine_with_history,
            biggest_transactions,
            shared_vs_personal_breakdown,
            category_month_over_month_movers,
            spending_pace_projection,
            load_category_budgets,
            budget_vs_actual,
        )

    return (
        mo,
        pd,
        category_breakdown,
        merchant_breakdown,
        monthly_trend,
        weekly_trend,
        detect_recurring_charges,
        spend_concentration,
        load_dashboard_transactions,
        expense_log_spreadsheet_keys,
        start_history_sync,
        load_history_df,
        combine_with_history,
        biggest_transactions,
        shared_vs_personal_breakdown,
        category_month_over_month_movers,
        spending_pace_projection,
        load_category_budgets,
        budget_vs_actual,
    )


@app.cell
def __(mo):
    # ── Styles scoped to .terminal wrapper ──────────────────────────────────
    mo.Html("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap');

      /* Each section is its own separate .terminal div (marimo mounts each
         cell's output independently), so the page background shows through
         in the gaps between them - matching it here makes those gaps read
         as dark instead of as white breaks in the page. */
      body { background: #0a0c0f; }

      /* marimo's "running" indicator: a ring in the middle of the screen
         instead of its hourglass in the top-left corner. Like the hourglass
         it only appears once cells have run for a second, so a quick
         dropdown change doesn't flash it. */
      [data-testid="loading-indicator"] {
        position: fixed;
        top: 50%;
        left: 50%;
        width: 44px;
        height: 44px;
        margin: -22px 0 0 -22px;
        border-radius: 50%;
        border: 3px solid #1e2330;
        border-top-color: #00d17a;
        box-shadow: 0 0 0 10px rgba(10, 12, 15, 0.85);
        background: rgba(10, 12, 15, 0.85);
        animation: t-spin 0.8s linear infinite, t-appear 0.2s ease-out 1s both;
      }
      [data-testid="loading-indicator"] .running-app-icon { display: none; }
      @keyframes t-spin { to { transform: rotate(360deg); } }
      @keyframes t-appear { from { opacity: 0; } to { opacity: 1; } }

      .terminal {
        background: #0a0c0f;
        color: #c8d0e0;
        font-family: 'IBM Plex Sans', sans-serif;
        min-height: 100vh;
        width: 100%;
        box-sizing: border-box;
      }
      .terminal * { box-sizing: border-box; }

      .t-header {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        padding: 2rem 2.5rem 1.5rem;
        border-bottom: 1px solid #1e2330;
        flex-wrap: wrap;
        gap: 0.6rem;
      }
      .t-title {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.3rem;
        font-weight: 500;
        color: #e8edf5;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .t-subtitle {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.9rem;
        color: #E8890C;
        letter-spacing: 0.12em;
        margin-top: 0.3rem;
      }
      .t-badge {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.82rem;
        letter-spacing: 0.1em;
        color: #00d17a;
        border: 1px solid #00412a;
        background: rgba(0,209,122,0.05);
        padding: 0.25rem 0.6rem;
        border-radius: 2px;
      }
      .t-badge.warn {
        color: #ff4d6a;
        border: 1px solid #4d0f18;
        background: rgba(255,77,106,0.08);
      }

      /* marimo's own UI widgets (dropdown/multiselect/button) render inside
         a closed shadow root, so their internal label text/border colors
         can't be recolored from here - they're styled by marimo's own
         light/dark theme instead (see .marimo.toml, theme = "dark"), which
         is why this row can be dark too instead of a mismatched light bar. */
      .t-filter-row {
        padding: 1rem 1.8rem;
        border-bottom: 1px solid #1e2330;
        background: #13161d;
        display: flex;
        align-items: center;
        gap: 1.5rem;
        flex-wrap: wrap;
      }

      .t-kpis {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 1px;
        background: #1e2330;
        border-bottom: 1px solid #1e2330;
      }
      .t-kpi { background: #111318; padding: 1.4rem 1.6rem; position: relative; }
      .t-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
      .t-kpi.pos::before { background: #00d17a; }
      .t-kpi.neg::before { background: #ff4d6a; }
      .t-kpi.amb::before { background: #f5a623; }
      .t-kpi.hi::before  { background: #E8890C; }

      .t-kpi-label {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem;
        letter-spacing: 0.14em;
        color: #E8890C;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
      }
      .t-kpi-value {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 1.7rem;
        font-weight: 600;
        line-height: 1;
        color: #e8edf5;
      }
      .t-kpi-value.pos { color: #00d17a; }
      .t-kpi-value.neg { color: #ff4d6a; }
      .t-kpi-sub {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
        color: #7a8296;
        margin-top: 0.45rem;
      }

      .t-section {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.82rem;
        letter-spacing: 0.16em;
        color: #E8890C;
        text-transform: uppercase;
        padding: 1.4rem 1.8rem 0.7rem;
        border-top: 1px solid #1e2330;
        background: #13161d;
        border-bottom: 1px solid #1e2330;
      }

      .t-table { width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: 0.9rem; }
      .t-table th {
        text-align: left; font-size: 0.76rem; font-weight: 500; letter-spacing: 0.1em;
        text-transform: uppercase; color: #E8890C; padding: 0.6rem 1.8rem;
        border-bottom: 1px solid #1e2330; background: #0a0c0f;
      }
      .t-table td { padding: 0.7rem 1.8rem; border-bottom: 1px solid #1a1e28; color: #c8d0e0; }
      .t-table tr:last-child td { border-bottom: none; }
      .t-table tr:hover td { background: rgba(255,255,255,0.018); }
      .t-table td.tk  { font-weight: 600; color: #e8edf5; }
      .t-table td.pos { color: #00d17a; }
      .t-table td.neg { color: #ff4d6a; }
      .t-table td.amb { color: #f5a623; }
      .t-table td.dim { color: #7a8296; }
      .t-table-wrap { overflow-x: auto; }

      /* A <details>/<summary> pair needs no JS for expand/collapse - the
         summary line stays visible (and gives an at-a-glance figure) while
         the full row-by-row table underneath only renders open on click. */
      .t-collapsible summary {
        cursor: pointer;
        list-style: none;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.9rem 1.8rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.85rem;
        color: #c8d0e0;
      }
      .t-collapsible summary::-webkit-details-marker { display: none; }
      .t-collapsible summary::marker { content: ""; }
      .t-collapsible summary:hover { background: rgba(255,255,255,0.02); }
      .t-collapsible summary::after {
        content: '▸';
        color: #E8890C;
        font-size: 0.8rem;
        flex-shrink: 0;
        transition: transform 0.15s ease;
      }
      .t-collapsible[open] summary::after { transform: rotate(90deg); }
      .t-collapsible-hint { color: #7a8296; }
      .t-collapsible summary .pos { color: #00d17a; }
      .t-collapsible summary .neg { color: #ff4d6a; }
      .t-collapsible summary .amb { color: #f5a623; }

      .bar-row { display: flex; align-items: center; gap: 0.9rem; padding: 0.55rem 1.8rem; }
      .bar-label {
        font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem; color: #c8d0e0;
        width: 190px; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .bar-track { flex: 1; height: 14px; background: #1a1e28; border-radius: 2px; overflow: hidden; }
      .bar-fill { height: 100%; border-radius: 2px; }
      .bar-value {
        font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem; color: #e8edf5;
        width: 130px; text-align: right; flex-shrink: 0;
      }

      .t-empty {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        min-height: 30vh; gap: 0.6rem; border-top: 1px solid #1e2330;
        font-family: 'IBM Plex Mono', monospace; color: #E8890C; letter-spacing: 0.1em;
      }

      @media (max-width: 640px) {
        .t-header { padding: 1.4rem 1.2rem 1rem; }
        .t-kpis { grid-template-columns: repeat(2, 1fr); }
        .t-kpi { padding: 1rem 1.1rem; }
        .t-kpi-value { font-size: 1.3rem; }
        .t-section { padding: 1.1rem 1.2rem 0.6rem; }
        .t-table th, .t-table td { padding: 0.55rem 1rem; }
        .t-table { font-size: 0.8rem; }
        .bar-label { width: 110px; }
        .bar-value { width: 90px; }
      }
    </style>
    """)
    return


@app.cell
def __(mo):
    # ── Reload control ───────────────────────────────────────────────────────
    # value/on_click make .value an explicit click counter (0 until clicked)
    # so the load cell below can tell "first load" apart from "clicked".
    reload_button = mo.ui.button(
        label="Reload data",
        kind="neutral",
        value=0,
        on_click=lambda count: count + 1,
    )
    return (reload_button,)


@app.cell
def __(
    expense_log_spreadsheet_keys,
    load_category_budgets,
    load_dashboard_transactions,
    mo,
    reload_button,
    start_history_sync,
):
    # ── Load all transactions (re-runs when the reload button fires) ────────
    # From the budget spreadsheet's Expense Log tab when
    # EXPENSE_LOG_SPREADSHEET_KEYS is set (a few seconds, as fresh as the
    # daily export). Otherwise from the local DB, which on Render first does
    # a bounded live resync since the free-tier container's disk resets on
    # every idle-timeout wake - see sync_recent_years_if_on_render's
    # docstring. Reload re-reads the sheet, or re-syncs (force=True).
    # The Expense Log only holds this year, so in sheet mode the earlier
    # years are synced from Splitwise in the background (start_history_sync)
    # and added by the cells below once they arrive, without blocking this.
    from_sheet = bool(expense_log_spreadsheet_keys())
    with mo.status.spinner(
        title="Loading spending data...",
        subtitle=(
            "Reading the Expense Log from Google Sheets."
            if from_sheet
            else "On first load this can take a few minutes on Render's free tier while it resyncs from Splitwise in the background."
        ),
    ):
        loaded_txns, sync_error = load_dashboard_transactions(
            force=bool(reload_button.value)
        )
        history_done = start_history_sync() if from_sheet else None
        # Optional: silently absent unless the CATEGORY_BUDGETS env var is
        # set - see load_category_budgets()'s docstring. Reload also
        # re-reads it, so editing the env var picks up on "Reload" (once
        # the process restarts to pick up the new value).
        budgets, budget_error = load_category_budgets()
    return loaded_txns, from_sheet, history_done, sync_error, budgets, budget_error


@app.cell
def __(history_done, mo):
    # ── Wait for the earlier years without blocking the page ────────────────
    # A marimo thread may set state, which re-runs the cells that read it.
    get_history_ready, _set_history_ready = mo.state(
        history_done is None or history_done.is_set()
    )

    def _wait_for_history():
        history_done.wait()
        _set_history_ready(True)

    if not get_history_ready():
        mo.Thread(target=_wait_for_history, daemon=True).start()
    return (get_history_ready,)


@app.cell
def __(
    combine_with_history,
    from_sheet,
    get_history_ready,
    load_history_df,
    loaded_txns,
):
    # ── This year's Expense Log + earlier years, once synced ────────────────
    history_loading = from_sheet and not get_history_ready()
    if from_sheet and not history_loading:
        _history, history_error = load_history_df()
        all_txns = combine_with_history(loaded_txns, _history)
    else:
        all_txns, history_error = loaded_txns, None
    return all_txns, history_error, history_loading


@app.cell
def __(all_txns, mo, reload_button):
    # ── Year + category filters, built from what's actually in the data ─────
    if all_txns.empty:
        _year_options = ["All time"]
        _category_options = []
    else:
        _years = sorted(all_txns["date"].dt.year.unique().tolist(), reverse=True)
        _year_options = ["All time"] + [str(_y) for _y in _years]
        _category_options = sorted(all_txns["category"].unique().tolist())

    year_select = mo.ui.dropdown(
        options=_year_options, value=_year_options[0], label="Year"
    )
    category_select = mo.ui.multiselect(
        options=_category_options, value=[], label="Categories (empty = all)"
    )
    search_input = mo.ui.text(placeholder="e.g. Amazon", label="Search merchant")

    # Built as one HTML string (via mo.as_html) rather than splitting the
    # <div> open/close tags across separate mo.Html()/vstack items - each
    # mo.Html() call is sanitized independently, so a tag opened in one call
    # and closed in another never actually nests; the widgets would render
    # as siblings outside the styled container instead of inside it.
    mo.Html(f"""
    <div class="t-filter-row">
      {mo.as_html(year_select)}
      {mo.as_html(category_select)}
      {mo.as_html(search_input)}
      {mo.as_html(reload_button)}
    </div>
    """)
    return category_select, search_input, year_select


@app.cell
def __(all_txns, category_select, year_select):
    # ── Apply filters ────────────────────────────────────────────────────────
    df = all_txns

    if not df.empty and year_select.value != "All time":
        df = df[df["date"].dt.year == int(year_select.value)]

    if not df.empty and category_select.value:
        df = df[df["category"].isin(category_select.value)]

    return (df,)


@app.cell
def __(
    all_txns,
    biggest_transactions,
    budget_error,
    budget_vs_actual,
    budgets,
    category_breakdown,
    category_month_over_month_movers,
    df,
    merchant_breakdown,
    mo,
    monthly_trend,
    weekly_trend,
    detect_recurring_charges,
    shared_vs_personal_breakdown,
    spend_concentration,
    spending_pace_projection,
    sync_error,
    from_sheet,
    history_error,
    history_loading,
):
    # ── Header + empty state ─────────────────────────────────────────────────
    if sync_error:
        _badge = f'<div class="t-badge warn" title="{sync_error}">⚠ SYNC FAILED</div>'
    elif budget_error:
        _badge = f'<div class="t-badge warn" title="{budget_error}">⚠ BUDGET CONFIG INVALID</div>'
    elif history_error:
        _badge = (
            f'<div class="t-badge warn" title="{history_error}">⚠ THIS YEAR ONLY</div>'
        )
    elif history_loading:
        _badge = '<div class="t-badge" title="Syncing earlier years from Splitwise; they appear when done.">BUDGET SHEET · LOADING EARLIER YEARS</div>'
    elif from_sheet:
        _badge = '<div class="t-badge">BUDGET SHEET</div>'
    else:
        _badge = '<div class="t-badge">LOCAL DATABASE</div>'
    header_html = f"""
    <div class="t-header">
      <div>
        <div class="t-title">◆ Spending Analytics</div>
        <div class="t-subtitle">Splitwise · Your Share of Spend</div>
      </div>
      {_badge}
    </div>
    """

    if df.empty:
        mo.Html(f"""
        <div class="terminal">
          {header_html}
          <div class="t-empty">
            No transactions match the current filters.<br/>
            Run the sync pipeline first, or widen the year/category filter above.
          </div>
        </div>
        """)
        mo.stop(True)

    cat_bd = category_breakdown(df)
    merch_bd = merchant_breakdown(df, top_n=15)
    monthly = monthly_trend(df)
    weekly = weekly_trend(df).tail(26)
    recurring = detect_recurring_charges(df)
    concentration = spend_concentration(df, by="merchant", top_n=5)
    biggest = biggest_transactions(df, top_n=10)
    shared_split = shared_vs_personal_breakdown(df)
    movers = category_month_over_month_movers(df, top_n=5)
    # Pace projection is always "this year to date", off the unfiltered
    # data - a year/category filter shouldn't hide or distort it.
    pace = spending_pace_projection(all_txns)
    budget_actual = budget_vs_actual(df, budgets)

    return (
        header_html,
        cat_bd,
        merch_bd,
        monthly,
        weekly,
        recurring,
        concentration,
        biggest,
        shared_split,
        movers,
        pace,
        budget_actual,
    )


@app.cell
def __(cat_bd, concentration, df, header_html, mo, monthly, pace, recurring):
    # ── KPI strip ─────────────────────────────────────────────────────────────
    _total_spend = df["amount"].sum()
    _txn_count = len(df)
    _n_months = df["date"].dt.to_period("M").nunique()
    _avg_monthly = _total_spend / _n_months if _n_months else 0.0
    _top_category = cat_bd.iloc[0]["category"] if not cat_bd.empty else "—"
    _top_category_pct = cat_bd.iloc[0]["pct_of_total"] if not cat_bd.empty else 0.0
    _est_subscriptions = (
        recurring["estimated_monthly_cost"].sum() if not recurring.empty else 0.0
    )

    # Most recent month with a known year-over-year comparison (needs the
    # same calendar month a year earlier to also be in range).
    _yoy_rows = monthly[monthly["yoy_pct"].notna()] if not monthly.empty else monthly
    _yoy_kpi = ""
    if not _yoy_rows.empty:
        _latest_yoy = _yoy_rows.iloc[-1]
        _yoy_pct = _latest_yoy["yoy_pct"]
        _yoy_cls = "neg" if _yoy_pct > 0 else "pos"
        _yoy_kpi = f"""
      <div class="t-kpi {_yoy_cls}">
        <div class="t-kpi-label">{_latest_yoy['year_month'].strftime('%b %Y')} vs Last Year</div>
        <div class="t-kpi-value {_yoy_cls}" style="font-size:1.2rem;">{_yoy_pct:+.1f}%</div>
        <div class="t-kpi-sub">${_latest_yoy['total']:,.2f} this month</div>
      </div>"""

    _pace_kpi = ""
    if pace:
        _pace_kpi = f"""
      <div class="t-kpi amb">
        <div class="t-kpi-label">{pace['year']} Pace</div>
        <div class="t-kpi-value" style="font-size:1.2rem;">${pace['projected_total']:,.0f}</div>
        <div class="t-kpi-sub">projected · ${pace['total_so_far']:,.2f} so far, day {pace['days_elapsed']}/{pace['days_in_year']}</div>
      </div>"""

    _kpis_html = f"""
    <div class="t-kpis">
      <div class="t-kpi hi">
        <div class="t-kpi-label">Total Spend</div>
        <div class="t-kpi-value">${_total_spend:,.2f}</div>
        <div class="t-kpi-sub">{_txn_count} transactions</div>
      </div>
      <div class="t-kpi hi">
        <div class="t-kpi-label">Avg / Month</div>
        <div class="t-kpi-value">${_avg_monthly:,.2f}</div>
        <div class="t-kpi-sub">across {_n_months} month(s)</div>
      </div>
      <div class="t-kpi amb">
        <div class="t-kpi-label">Top Category</div>
        <div class="t-kpi-value" style="font-size:1.2rem;">{_top_category}</div>
        <div class="t-kpi-sub">{_top_category_pct:.1f}% of spend</div>
      </div>
      <div class="t-kpi amb">
        <div class="t-kpi-label">Top 5 Merchants</div>
        <div class="t-kpi-value" style="font-size:1.2rem;">{concentration['pct_of_total']:.1f}%</div>
        <div class="t-kpi-sub">of total spend</div>
      </div>
      <div class="t-kpi neg">
        <div class="t-kpi-label">Est. Recurring / Mo.</div>
        <div class="t-kpi-value neg" style="font-size:1.2rem;">${_est_subscriptions:,.2f}</div>
        <div class="t-kpi-sub">{len(recurring)} likely subscription(s)</div>
      </div>
      {_yoy_kpi}
      {_pace_kpi}
    </div>
    """

    mo.Html(
        f'<div class="terminal" style="min-height:auto">{header_html}{_kpis_html}</div>'
    )
    return


@app.cell
def __(df, mo, search_input):
    # ── Matching transactions (only shown while searching) ──────────────────
    # Searches merchant within the already year/category-filtered `df`, so
    # search composes with the other filters rather than resetting them.
    import html

    _query = search_input.value.strip()
    if not _query:
        mo.Html("")
        mo.stop(True)

    _matches = df[
        df["merchant"].str.contains(_query, case=False, na=False, regex=False)
    ].sort_values("date", ascending=False)

    if _matches.empty:
        _body = f'<div class="t-empty" style="min-height:10vh;">No transactions match "{html.escape(_query)}".</div>'
    else:

        def _txn_row(r):
            return f"""
            <tr>
              <td class="dim">{r.date.strftime('%Y-%m-%d')}</td>
              <td class="tk">{r.merchant}</td>
              <td class="dim">{r.category}</td>
              <td>${r.amount:,.2f}</td>
            </tr>"""

        _rows = "".join(_txn_row(_r) for _, _r in _matches.iterrows())
        _body = f"""
        <div class="t-table-wrap">
          <table class="t-table">
            <thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Amount</th></tr></thead>
            <tbody>{_rows}</tbody>
          </table>
        </div>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Matching Transactions ({len(_matches)}) — "{html.escape(_query)}"</div>
      {_body}
    </div>
    """)
    return


@app.cell
def __(cat_bd, mo):
    # ── Category breakdown (fixed categorical palette, top 8 + Other) ───────
    _categorical = [
        "#2a78d6",
        "#eb6834",
        "#1baf7a",
        "#eda100",
        "#e87ba4",
        "#3fa334",
        "#7c6ce8",
        "#e34948",
    ]

    _cat_rows = cat_bd.head(8).reset_index(drop=True)
    _other_total = cat_bd["total"].iloc[8:].sum() if len(cat_bd) > 8 else 0.0
    _max_total = cat_bd["total"].max() if not cat_bd.empty else 1.0

    def _cat_bar(label, total, pct, color):
        _width = max(total / _max_total * 100, 1.0) if _max_total else 0.0
        return f"""
        <div class="bar-row">
          <div class="bar-label" title="{label}">{label}</div>
          <div class="bar-track"><div class="bar-fill" style="width:{_width:.1f}%;background:{color};"></div></div>
          <div class="bar-value">${total:,.2f} ({pct:.1f}%)</div>
        </div>"""

    _cat_bars = "".join(
        _cat_bar(_r.category, _r.total, _r.pct_of_total, _categorical[_i])
        for _i, _r in _cat_rows.iterrows()
    )
    if _other_total > 0:
        _other_pct = (
            _other_total / cat_bd["total"].sum() * 100 if cat_bd["total"].sum() else 0.0
        )
        _cat_bars += _cat_bar("Other", _other_total, _other_pct, "#4a5064")

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Spend by Category</div>
      {_cat_bars}
    </div>
    """)
    return


@app.cell
def __(merch_bd, mo):
    # ── Merchant breakdown table ─────────────────────────────────────────────
    def _merch_row(r):
        return f"""
        <tr>
          <td class="tk">{r.merchant}</td>
          <td>${r.total:,.2f}</td>
          <td class="dim">{int(r['count'])}</td>
          <td class="dim">${r.avg_amount:,.2f}</td>
        </tr>"""

    _merch_rows = "".join(_merch_row(_r) for _, _r in merch_bd.iterrows())
    _n = len(merch_bd)
    _total = merch_bd["total"].sum()

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Top Merchants</div>
      <details class="t-collapsible">
        <summary>
          <span class="t-collapsible-hint">{_n} merchants</span>
          <span>${_total:,.2f} total spend</span>
        </summary>
        <div class="t-table-wrap">
          <table class="t-table">
            <thead><tr><th>Merchant</th><th>Total</th><th>Count</th><th>Avg</th></tr></thead>
            <tbody>{_merch_rows}</tbody>
          </table>
        </div>
      </details>
    </div>
    """)
    return


@app.cell
def __(monthly, mo, pd):
    # ── Monthly trend bar chart (single series, single axis) ────────────────
    _W, _H = 1200, 260
    _ML, _MR, _MT, _MB = 70, 30, 20, 40
    _PW, _PH = _W - _ML - _MR, _H - _MT - _MB
    _n = max(len(monthly), 1)
    _slot = _PW / _n
    _bar_w = _slot * 0.6
    _baseline_y = _MT + _PH

    _max_total = max(monthly["total"].max(), 1.0) if not monthly.empty else 1.0
    _scale = _PH / _max_total if _max_total else 0.0

    _bars = []
    _labels = []
    for _i, _row in enumerate(monthly.itertuples()):
        _x = _ML + _i * _slot + (_slot - _bar_w) / 2
        _bh = max(_row.total * _scale, 1.0)
        _y = _baseline_y - _bh
        _mom = "" if pd.isna(_row.mom_pct) else f" · MoM {_row.mom_pct:+.0f}%"
        _yoy = "" if pd.isna(_row.yoy_pct) else f" · YoY {_row.yoy_pct:+.0f}%"
        _tooltip = f"{_row.year_month} — ${_row.total:,.2f}{_mom}{_yoy}"
        _bars.append(
            f'<rect x="{_x:.1f}" y="{_y:.1f}" width="{_bar_w:.1f}" height="{_bh:.1f}" '
            f'rx="3" fill="#E8890C" opacity="0.9"><title>{_tooltip}</title></rect>'
        )
        if _i % max(1, _n // 12) == 0:
            _labels.append(
                f'<text x="{_x + _bar_w/2:.1f}" y="{_H - _MB + 16:.1f}" fill="#7a8296" font-size="10.5" '
                f'text-anchor="middle" font-family="IBM Plex Mono, monospace">{_row.year_month.strftime("%b %y")}</text>'
            )

    _chart_svg = f"""
    <svg viewBox="0 0 {_W} {_H}" width="100%" style="height:auto; display:block;">
      <line x1="{_ML}" y1="{_baseline_y:.1f}" x2="{_W - _MR}" y2="{_baseline_y:.1f}" stroke="#1e2330" stroke-width="1"/>
      {"".join(_bars)}
      {"".join(_labels)}
    </svg>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Monthly Spend ({len(monthly)} months)</div>
      <div style="padding:1rem 1.8rem 1.5rem;">{_chart_svg}</div>
    </div>
    """)
    return


@app.cell
def __(mo, weekly):
    # ── Weekly trend, last 26 weeks ──────────────────────────────────────────
    _W, _H = 1200, 200
    _ML, _MR, _MT, _MB = 70, 30, 20, 40
    _PW, _PH = _W - _ML - _MR, _H - _MT - _MB
    _n = max(len(weekly), 1)
    _slot = _PW / _n
    _bar_w = _slot * 0.6
    _baseline_y = _MT + _PH

    _max_total = max(weekly["total"].max(), 1.0) if not weekly.empty else 1.0
    _scale = _PH / _max_total if _max_total else 0.0

    _bars = []
    _labels = []
    for _i, _row in enumerate(weekly.itertuples()):
        _x = _ML + _i * _slot + (_slot - _bar_w) / 2
        _bh = max(_row.total * _scale, 1.0)
        _y = _baseline_y - _bh
        _tooltip = (
            f'Week of {_row.week.start_time.strftime("%Y-%m-%d")} — ${_row.total:,.2f}'
        )
        _bars.append(
            f'<rect x="{_x:.1f}" y="{_y:.1f}" width="{_bar_w:.1f}" height="{_bh:.1f}" '
            f'rx="2" fill="#2a78d6" opacity="0.9"><title>{_tooltip}</title></rect>'
        )
        if _i % max(1, _n // 8) == 0:
            _labels.append(
                f'<text x="{_x + _bar_w/2:.1f}" y="{_H - _MB + 16:.1f}" fill="#7a8296" font-size="10" '
                f'text-anchor="middle" font-family="IBM Plex Mono, monospace">{_row.week.start_time.strftime("%b %d")}</text>'
            )

    _chart_svg = f"""
    <svg viewBox="0 0 {_W} {_H}" width="100%" style="height:auto; display:block;">
      <line x1="{_ML}" y1="{_baseline_y:.1f}" x2="{_W - _MR}" y2="{_baseline_y:.1f}" stroke="#1e2330" stroke-width="1"/>
      {"".join(_bars)}
      {"".join(_labels)}
    </svg>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Weekly Spend (last {len(weekly)} weeks)</div>
      <div style="padding:1rem 1.8rem 1.5rem;">{_chart_svg}</div>
    </div>
    """)
    return


@app.cell
def __(mo, movers, pd):
    # ── What changed: biggest category movers vs. the prior month ───────────
    if movers.empty:
        _body = '<div class="t-empty" style="min-height:10vh;">Need at least two months of data to compare.</div>'
    else:

        def _mover_row(r):
            _cls = "neg" if r.delta > 0 else "pos"
            _pct = "new" if pd.isna(r.delta_pct) else f"{r.delta_pct:+.0f}%"
            return f"""
            <tr>
              <td class="tk">{r.category}</td>
              <td>${r.prior_total:,.2f}</td>
              <td>${r.current_total:,.2f}</td>
              <td class="{_cls}">{r.delta:+,.2f} ({_pct})</td>
            </tr>"""

        _rows = "".join(_mover_row(_r) for _, _r in movers.iterrows())
        _n = len(movers)
        _top = movers.iloc[0]
        _top_cls = "neg" if _top.delta > 0 else "pos"
        _body = f"""
        <details class="t-collapsible">
          <summary>
            <span class="t-collapsible-hint">{_n} categories</span>
            <span>biggest mover: {_top.category}</span>
            <span class="{_top_cls}">{_top.delta:+,.2f}</span>
          </summary>
          <div class="t-table-wrap">
            <table class="t-table">
              <thead><tr><th>Category</th><th>Prior Month</th><th>This Month</th><th>Change</th></tr></thead>
              <tbody>{_rows}</tbody>
            </table>
          </div>
        </details>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">What Changed vs. Last Month</div>
      {_body}
    </div>
    """)
    return


@app.cell
def __(budget_actual, budget_error, mo, pd):
    # ── Budget vs. actual, most recent month in view ─────────────────────────
    if budget_actual.empty:
        _empty_reason = (
            f"Couldn't load budget targets: {budget_error}"
            if budget_error
            else "No budget targets configured. Set the CATEGORY_BUDGETS env "
            "var to a JSON object of category -> monthly $ target, e.g. "
            '\'{"Food and drink": 700, "Travel": 300}\', to see this section.'
        )
        _body = f'<div class="t-empty" style="min-height:10vh;">{_empty_reason}</div>'
    else:

        def _budget_row(r):
            _pct_over_or_dim = pd.isna(r.pct_used)
            if _pct_over_or_dim:
                _cls, _pct_text = "dim", "no budget set"
            elif r.pct_used >= 100:
                _cls, _pct_text = "neg", f"{r.pct_used:.0f}%"
            elif r.pct_used >= 80:
                _cls, _pct_text = "amb", f"{r.pct_used:.0f}%"
            else:
                _cls, _pct_text = "pos", f"{r.pct_used:.0f}%"
            _budget_text = "—" if pd.isna(r.budget) else f"${r.budget:,.2f}"
            _remaining_text = "—" if pd.isna(r.remaining) else f"${r.remaining:,.2f}"
            return f"""
            <tr>
              <td class="tk">{r.category}</td>
              <td class="dim">{_budget_text}</td>
              <td>${r.actual:,.2f}</td>
              <td class="dim">{_remaining_text}</td>
              <td class="{_cls}">{_pct_text}</td>
            </tr>"""

        _rows = "".join(_budget_row(_r) for _, _r in budget_actual.iterrows())
        _n = len(budget_actual)
        _total_budget = budget_actual["budget"].sum()
        _total_actual = budget_actual["actual"].sum()
        _over_count = int((budget_actual["pct_used"] >= 100).sum())
        _over_cls = "neg" if _over_count else "pos"
        _over_text = f"{_over_count} over budget" if _over_count else "all on track"
        _body = f"""
        <details class="t-collapsible">
          <summary>
            <span class="t-collapsible-hint">{_n} categories</span>
            <span>${_total_actual:,.2f} of ${_total_budget:,.2f} this month</span>
            <span class="{_over_cls}">{_over_text}</span>
          </summary>
          <div class="t-table-wrap">
            <table class="t-table">
              <thead><tr><th>Category</th><th>Budget</th><th>Actual</th><th>Remaining</th><th>% Used</th></tr></thead>
              <tbody>{_rows}</tbody>
            </table>
          </div>
        </details>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Budget vs. Actual (This Month)</div>
      {_body}
    </div>
    """)
    return


@app.cell
def __(mo, shared_split):
    # ── Shared vs. personal spend ────────────────────────────────────────────
    _max_total = max(shared_split["shared_total"], shared_split["personal_total"], 1.0)

    def _split_bar(label, total, pct, color):
        _width = max(total / _max_total * 100, 1.0) if total else 0.0
        return f"""
        <div class="bar-row">
          <div class="bar-label" title="{label}">{label}</div>
          <div class="bar-track"><div class="bar-fill" style="width:{_width:.1f}%;background:{color};"></div></div>
          <div class="bar-value">${total:,.2f} ({pct:.1f}%)</div>
        </div>"""

    _bars = _split_bar(
        "Shared (Splitwise)",
        shared_split["shared_total"],
        shared_split["shared_pct"],
        "#2a78d6",
    ) + _split_bar(
        "Personal (solo)",
        shared_split["personal_total"],
        shared_split["personal_pct"],
        "#1baf7a",
    )

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Shared vs. Personal Spend</div>
      {_bars}
    </div>
    """)
    return


@app.cell
def __(biggest, mo):
    # ── Biggest transactions this period ─────────────────────────────────────
    if biggest.empty:
        _body = '<div class="t-empty" style="min-height:10vh;">No transactions in the current filter.</div>'
    else:

        def _big_row(r):
            return f"""
            <tr>
              <td class="dim">{r.date.strftime('%Y-%m-%d')}</td>
              <td class="tk">{r.merchant}</td>
              <td class="dim">{r.category}</td>
              <td>${r.amount:,.2f}</td>
            </tr>"""

        _rows = "".join(_big_row(_r) for _, _r in biggest.iterrows())
        _n = len(biggest)
        _largest = biggest["amount"].max()
        _body = f"""
        <details class="t-collapsible">
          <summary>
            <span class="t-collapsible-hint">{_n} transactions</span>
            <span>largest: ${_largest:,.2f}</span>
          </summary>
          <div class="t-table-wrap">
            <table class="t-table">
              <thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Amount</th></tr></thead>
              <tbody>{_rows}</tbody>
            </table>
          </div>
        </details>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">Biggest Transactions</div>
      {_body}
    </div>
    """)
    return


@app.cell
def __(mo, recurring):
    # ── Recurring / subscription-like charges ────────────────────────────────
    if recurring.empty:
        _body = '<div class="t-empty" style="min-height:10vh;">No recurring charges detected at this cadence/tolerance.</div>'
    else:

        def _rec_row(r):
            return f"""
            <tr>
              <td class="tk">{r.merchant}</td>
              <td class="neg" title="${r.avg_amount:,.2f} per charge">${r.estimated_monthly_cost:,.2f}/mo</td>
              <td class="dim">{int(r.occurrences)}</td>
              <td class="dim">{r.cadence.title()} (~{r.avg_interval_days:.0f}d)</td>
              <td class="dim">{r.first_seen} → {r.last_seen}</td>
            </tr>"""

        _rows = "".join(_rec_row(_r) for _, _r in recurring.iterrows())
        _n = len(recurring)
        _total_monthly = recurring["estimated_monthly_cost"].sum()
        _body = f"""
        <details class="t-collapsible">
          <summary>
            <span class="t-collapsible-hint">{_n} recurring charges</span>
            <span class="neg">${_total_monthly:,.2f}/mo total</span>
          </summary>
          <div class="t-table-wrap">
            <table class="t-table">
              <thead><tr><th>Merchant</th><th>Est. Cost</th><th>Occurrences</th><th>Cadence</th><th>Range</th></tr></thead>
              <tbody>{_rows}</tbody>
            </table>
          </div>
        </details>"""

    mo.Html(f"""
    <div class="terminal" style="min-height:auto">
      <div class="t-section">🔁 Likely Recurring Charges / Subscriptions</div>
      {_body}
    </div>
    """)
    return


if __name__ == "__main__":
    app.run()
