"""The ONLY module in this codebase allowed to `import yfinance`.
Enforced by test_provider_isolation.py (an ast-based grep test).

Transport only: this module does not interpret meaning (it does not know that
dividendYield is a percent, or that a bank's debtToEquity is legitimately
None) -- that all lives in normalize.py and score.py. Its one job is turning
network calls into FetchOutcome objects that never raise.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Iterable

import yfinance as yf
from tradingview_screener import Query, col

from ..models import FetchOutcome

NAME = "yfinance"
VERSION = "0.2.65"

# Measured: a healthy IDX ticker's .info has ~140-170 keys. A delisted/invalid
# ticker's .info comes back with as little as 1 key (observed: {"trailingPegRatio": None}
# for a nonexistent ticker). yfinance does NOT raise for this case -- try/except
# will not catch it. The check below is the actual detection mechanism.
_MIN_INFO_KEYS = 40
_PAUSE_EVERY = 50
_PAUSE_SECONDS = 2.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_scalar(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def fetch_universe(min_market_cap: float = 1_000_000_000_000, limit: int = 2000) -> list[dict]:
    """Full tradable IDX universe via tradingview-screener -- already a pinned
    dependency of the scalper feature, no new dependency introduced. Measured:
    returns 887 IDX tickers with sector + market cap, no API key required."""
    q = (
        Query()
        .set_markets("indonesia")
        .select("name", "close", "market_cap_basic", "sector")
        .where(col("market_cap_basic") > min_market_cap)
        .limit(limit)
    )
    _, df = q.get_scanner_data()
    out = []
    for _, row in df.iterrows():
        out.append(
            {
                "ticker": str(row["name"]),
                "name": str(row["name"]),
                "sector": str(row.get("sector") or ""),
                "market_cap": float(row["market_cap_basic"]) if row.get("market_cap_basic") == row.get("market_cap_basic") else None,
            }
        )
    return out


def _dataframe_to_rows(df) -> dict[str, dict[str, float]]:
    """yfinance statement DataFrame (rows=line items, cols=period-end dates)
    -> {line_item_label: {iso_date: value}}, skipping NaN."""
    if df is None or df.empty:
        return {}
    out: dict[str, dict[str, float]] = {}
    for label in df.index:
        series = {}
        for col_date, val in df.loc[label].items():
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            try:
                d = col_date.date().isoformat()
            except AttributeError:
                d = str(col_date)
            series[d] = float(val)
        out[str(label)] = series
    return out


def fetch_one(ticker: str) -> FetchOutcome:
    fetched_at = _now()
    symbol = f"{ticker}.JK"
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
    except Exception as e:
        return FetchOutcome(ticker=ticker, ok=False, raw={}, reason=f"exception:{type(e).__name__}", fetched_at=fetched_at)

    if len(info) < _MIN_INFO_KEYS:
        return FetchOutcome(ticker=ticker, ok=False, raw={"info": info}, reason="empty_info", fetched_at=fetched_at)
    if info.get("currentPrice") is None and info.get("regularMarketPrice") is None:
        return FetchOutcome(ticker=ticker, ok=False, raw={"info": info}, reason="no_price", fetched_at=fetched_at)

    clean_info = {k: _clean_scalar(v) for k, v in info.items()}

    try:
        statements = {
            "income_stmt": _dataframe_to_rows(t.income_stmt),
            "balance_sheet": _dataframe_to_rows(t.balance_sheet),
            "cashflow": _dataframe_to_rows(t.cashflow),
        }
    except Exception as e:
        statements = {"income_stmt": {}, "balance_sheet": {}, "cashflow": {}}
        clean_info["_statements_error"] = f"{type(e).__name__}: {e}"

    try:
        div_series = t.dividends
        dividends = [
            {"date": idx.date().isoformat(), "amount": float(v)}
            for idx, v in div_series.items()
        ]
    except Exception:
        dividends = []

    raw = {"info": clean_info, "statements": statements, "dividends": dividends}
    return FetchOutcome(ticker=ticker, ok=True, raw=raw, reason=None, fetched_at=fetched_at)


def fetch_batch(tickers: Iterable[str], progress_every: int = 25) -> list[FetchOutcome]:
    """Sequential, with a periodic pause. Measured: yfinance's sqlite response
    cache deadlocks ("database is locked") under a ThreadPoolExecutor. At
    ~0.16-0.22s/ticker for .info alone (more with statements+dividends), 887
    tickers finishes in a few minutes sequentially -- parallelizing does not
    buy enough to justify the risk.

    Progress is printed periodically (not just at the end) because a run
    with statements+dividends takes minutes, and a silent multi-minute
    process is indistinguishable from a hung or killed one -- this was
    learned the hard way running the first real snapshot."""
    import sys

    out = []
    total = list(tickers)
    for i, ticker in enumerate(total):
        out.append(fetch_one(ticker))
        if (i + 1) % progress_every == 0 or (i + 1) == len(total):
            ok_count = sum(1 for o in out if o.ok)
            print(f"  ... {i + 1}/{len(total)} fetched ({ok_count} ok)", file=sys.stderr, flush=True)
        if (i + 1) % _PAUSE_EVERY == 0:
            time.sleep(_PAUSE_SECONDS)
    return out


class YFinanceProvider:
    name = NAME
    version = VERSION

    def fetch_universe(self) -> list[dict]:
        return fetch_universe()

    def fetch_one(self, ticker: str) -> FetchOutcome:
        return fetch_one(ticker)

    def fetch_batch(self, tickers: Iterable[str]) -> list[FetchOutcome]:
        return fetch_batch(tickers)
