"""Shared fixtures. `no_network` is autouse: any test that accidentally calls
yfinance or the TradingView scanner fails hard instead of silently hitting
the real network -- this is what keeps the whole suite offline and fast.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _boom(*args, **kwargs):
    raise AssertionError(
        "Network call attempted from a unit test. Use FixtureProvider / "
        "tests/fixtures/*.json instead of the real yfinance/tradingview client."
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr("yfinance.Ticker", _boom)
    try:
        monkeypatch.setattr("tradingview_screener.Query.get_scanner_data", _boom)
    except AttributeError:
        pass


@pytest.fixture
def fixture_json():
    def _load(name: str) -> dict:
        return json.loads((FIXTURES_DIR / f"{name}.json").read_text())

    return _load


@pytest.fixture
def all_fixture_names():
    return ["bbca", "bbri", "tlkm", "cbdk", "mlpt", "sparse"]
