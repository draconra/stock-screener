"""Provider boundary. Enforced rule (checked by test_provider_isolation.py):
no module outside `providers/` may import yfinance, and no module under
`providers/` other than `yfinance_provider.py` may import it either. When
yfinance eventually breaks for good, a replacement implements this Protocol
and exactly one line changes in fundamental_service.py -- score.py, store.py,
the API, and every historical CSV are untouched.
"""
from __future__ import annotations

from typing import Iterable, Protocol

from ..models import FetchOutcome


class FundamentalsProvider(Protocol):
    name: str
    version: str

    def fetch_universe(self) -> list[dict]:
        """[{ticker, name, sector, market_cap}, ...] -- the tradable IDX universe."""
        ...

    def fetch_one(self, ticker: str) -> FetchOutcome:
        """One ticker's raw info + statement rows + dividends. Transport/parse
        failures are reported via FetchOutcome(ok=False, reason=...), never by
        raising -- delisted tickers do not raise from yfinance, so callers
        cannot rely on exceptions to detect them."""
        ...

    def fetch_batch(self, tickers: Iterable[str]) -> list[FetchOutcome]:
        """Sequential by design -- yfinance's sqlite cache deadlocks under
        threads (measured). One call per ticker is ~0.16-0.22s; 887 tickers
        finishes in under 3 minutes, which does not justify the risk."""
        ...
