"""Test-only provider: reads the committed JSON fixtures under tests/fixtures/
instead of calling yfinance. Every test in this package uses this, never the
real network -- see conftest.py's `no_network` autouse fixture, which makes
any accidental yfinance/tradingview call a hard failure.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..models import FetchOutcome

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

NAME = "fixture"
VERSION = "test"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name.lower()}.json").read_text())


def _statements_to_rows(statements: dict) -> dict:
    """Fixtures store statements as {"revenue": {date: val}, ...} (flat, one
    label already resolved). yfinance_provider stores {label: {date: val}}
    per-statement-type. Wrap so normalize.resolve_series's key-matching still
    works: put each series under a single synthetic label."""
    out = {"income_stmt": {}, "balance_sheet": {}, "cashflow": {}}
    mapping = {
        "revenue": ("income_stmt", "Total Revenue"),
        "net_income": ("income_stmt", "Net Income"),
        "ocf": ("cashflow", "Operating Cash Flow"),
        "shares_outstanding": ("balance_sheet", "Ordinary Shares Number"),
        "total_equity": ("balance_sheet", "Stockholders Equity"),
        "total_assets": ("balance_sheet", "Total Assets"),
    }
    for field, (stmt, label) in mapping.items():
        series = statements.get(field, {})
        if series:
            out[stmt][label] = series
    return out


def fetch_one(ticker: str) -> FetchOutcome:
    try:
        data = load_fixture(ticker)
    except FileNotFoundError:
        return FetchOutcome(ticker=ticker, ok=False, raw={}, reason="fixture_not_found", fetched_at=_now())

    info = data.get("info", {})
    if len(info) < 5 or (info.get("currentPrice") is None and info.get("regularMarketPrice") is None):
        return FetchOutcome(ticker=ticker, ok=False, raw={"info": info}, reason="empty_info", fetched_at=_now())

    raw = {
        "info": info,
        "statements": _statements_to_rows(data.get("statements", {})),
        "dividends": data.get("dividends", []),
    }
    return FetchOutcome(ticker=ticker, ok=True, raw=raw, reason=None, fetched_at=_now())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FixtureProvider:
    name = NAME
    version = VERSION

    def fetch_universe(self) -> list[dict]:
        return [
            {"ticker": p.stem.upper(), "name": p.stem.upper(), "sector": "", "market_cap": None}
            for p in FIXTURES_DIR.glob("*.json")
        ]

    def fetch_one(self, ticker: str) -> FetchOutcome:
        return fetch_one(ticker)

    def fetch_batch(self, tickers) -> list[FetchOutcome]:
        return [fetch_one(t) for t in tickers]
