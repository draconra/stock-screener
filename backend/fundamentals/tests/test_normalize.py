"""Unit-semantics lock. This is the test that stops future-you from "fixing"
the dividend yield by multiplying by 100 -- it encodes the measured fact and
fails loudly if normalize.py ever drifts from it.
"""
from fundamentals.normalize import extract_dividends, extract_statements, normalize_info
from fundamentals.providers.fixture_provider import fetch_one


def test_bbca_dividend_yield_is_percent_not_fraction():
    outcome = fetch_one("bbca")
    row = normalize_info(outcome)
    # Measured 2026-09-22: BBCA info.dividendYield == 6.12, and independently
    # 381 (TTM dividends) / 6225 (price) * 100 == 6.12. Not 612, not 0.0612.
    assert row["dividend_yield"] is not None
    assert 5.0 < row["dividend_yield"] < 8.0


def test_roe_stays_a_fraction():
    outcome = fetch_one("bbca")
    row = normalize_info(outcome)
    # Measured: BBCA returnOnEquity == 0.21818 (21.8%), not 21.818.
    assert 0.0 < row["roe"] < 1.0


def test_bank_debt_to_equity_and_free_cashflow_are_none_not_zero():
    """The xlsx's cardinal sin: it wrote Debt_to_Equity=0 for every bank,
    turning "unknown" into "perfect". normalize.py must never do that --
    None must stay None all the way through."""
    outcome = fetch_one("bbca")
    row = normalize_info(outcome)
    assert row["debt_to_equity"] is None
    assert row["free_cashflow"] is None
    assert row["current_ratio"] is None


def test_delisted_ticker_normalizes_to_none():
    outcome = fetch_one("zzzz")
    assert outcome.ok is False
    assert normalize_info(outcome) is None


def test_ocf_resolves_via_fallback_label():
    outcome = fetch_one("tlkm")
    hits: dict = {}
    stmts = extract_statements(outcome, hit_counter=hits)
    assert len(stmts["ocf"]) >= 3
    assert "ocf" in hits


def test_dividends_are_ordered_oldest_first():
    outcome = fetch_one("tlkm")
    divs = extract_dividends(outcome)
    dates = [d["date"] for d in divs]
    assert dates == sorted(dates)
    assert len(divs) >= 20  # measured: 29 entries
