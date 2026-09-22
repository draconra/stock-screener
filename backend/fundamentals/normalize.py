"""Raw provider dict -> canonical row, per schema.FIELDS. Pure, stdlib-only,
fully unit-testable against the committed fixtures. This is where unit
semantics are decided ONCE (dividendYield is percent, roe is a fraction,
debtToEquity is ratio*100) -- nothing downstream re-derives or re-scales them.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from . import schema
from .models import FetchOutcome

# Cash-flow row labels are NOT consistent across IDX issuers. Measured across
# 15 tickers: 12/15 use the flattened XBRL label, only 3/15 use the tidy one.
# Code that matches only "Operating Cash Flow" silently breaks on 80% of IDX.
OCF_KEYS: tuple[str, ...] = (
    "Cash Flowsfromusedin Operating Activities Direct",  # 12/15 measured
    "Operating Cash Flow",  # 3/15 measured
    "Cash Flow From Continuing Operating Activities",
)
NET_INCOME_KEYS: tuple[str, ...] = ("Net Income", "Net Income Common Stockholders")
REVENUE_KEYS: tuple[str, ...] = ("Total Revenue", "Operating Revenue")
SHARES_KEYS: tuple[str, ...] = ("Ordinary Shares Number", "Share Issued")
EQUITY_KEYS: tuple[str, ...] = ("Stockholders Equity",)
ASSETS_KEYS: tuple[str, ...] = ("Total Assets",)

# Populated as a side effect of resolve_series() so a refresh run can report
# which label matched for which logical field -- this is the drift alarm for
# jebakan #2 in the plan (cash-flow label inconsistency getting worse silently).
FieldHitCounter = dict[str, dict[str, int]]


def _is_missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def normalize_info(outcome: FetchOutcome) -> dict[str, Any] | None:
    """Provider dict -> one canonical row dict, keyed by schema.FIELDS names.
    Returns None if the outcome was not ok (caller records the rejection).

    `outcome.raw` is the provider's combined payload: {"info": {...},
    "statements": {...}, "dividends": [...]}. Only the "info" sub-dict feeds
    the flat schema row here; statements/dividends are read separately via
    `extract_statements()` / `extract_dividends()` by the scoring engine.
    """
    if not outcome.ok:
        return None
    info = outcome.raw.get("info", {})
    row: dict[str, Any] = {}
    for f in schema.FIELDS:
        if f.source is None:
            continue  # provenance/derived fields filled in by the writer
        row[f.name] = info.get(f.source)
    row["ticker"] = outcome.ticker
    row["as_of"] = outcome.fetched_at[:10] if outcome.fetched_at else datetime.now(timezone.utc).date().isoformat()
    return row


def extract_statements(outcome: FetchOutcome, hit_counter: FieldHitCounter | None = None) -> dict[str, list[tuple[str, float]]]:
    """Provider payload -> {"revenue": [(date, val), ...], "net_income": [...],
    "ocf": [...], "shares_outstanding": [...], "total_equity": [...],
    "total_assets": [...], "total_debt": [...]}, oldest-first."""
    stmts = outcome.raw.get("statements", {})
    income = stmts.get("income_stmt", {})
    balance = stmts.get("balance_sheet", {})
    cashflow = stmts.get("cashflow", {})

    def series(rows: dict, keys: tuple[str, ...], name: str) -> list[tuple[str, float]]:
        return ordered_years(resolve_series(rows, keys, name, hit_counter))

    return {
        "revenue": series(income, REVENUE_KEYS, "revenue"),
        "net_income": series(income, NET_INCOME_KEYS, "net_income"),
        "ocf": series(cashflow, OCF_KEYS, "ocf"),
        "shares_outstanding": series(balance, SHARES_KEYS, "shares_outstanding"),
        "total_equity": series(balance, EQUITY_KEYS, "total_equity"),
        "total_assets": series(balance, ASSETS_KEYS, "total_assets"),
        "total_debt": series(balance, ("Total Debt",), "total_debt"),
    }


def extract_dividends(outcome: FetchOutcome) -> list[dict]:
    return outcome.raw.get("dividends", [])


def resolve_series(
    statement_rows: dict[str, dict[str, float]],
    keys: tuple[str, ...],
    field_name: str,
    hit_counter: FieldHitCounter | None = None,
) -> dict[str, float]:
    """`statement_rows` is {row_label: {period_date: value}} as produced by a
    provider (e.g. yfinance's .income_stmt.to_dict(orient='index')). Returns the
    first matching row's series, oldest key order preserved from input.

    hit_counter, when given, records which label matched -- committed to the
    schema report each run so a shift in Yahoo's XBRL taxonomy shows up as a
    number moving in a report, not as a screening result quietly going wrong.
    """
    for k in keys:
        if k in statement_rows:
            if hit_counter is not None:
                hit_counter.setdefault(field_name, {})
                hit_counter[field_name][k] = hit_counter[field_name].get(k, 0) + 1
            series = statement_rows[k]
            return {d: v for d, v in series.items() if not _is_missing(v)}
    if hit_counter is not None:
        hit_counter.setdefault(field_name, {})
        hit_counter[field_name]["__MISS__"] = hit_counter[field_name].get("__MISS__", 0) + 1
    return {}


def ordered_years(series: dict[str, float]) -> list[tuple[str, float]]:
    """Sort a {date_str: value} series oldest-first by date string (works for
    ISO 'YYYY-MM-DD' keys as produced by the provider)."""
    return sorted(series.items(), key=lambda kv: kv[0])
