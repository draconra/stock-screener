"""Regression test against the measured bug in
~/Downloads/IDX_Potential_Stock_Screener.xlsx: `Screener_Pass = Value_OK &
Growth_OK & Tech_OK & Vol_OK & Sentiment_OK` ANDs five gates, two of them
day-state facts (RSI band, relative volume >= 1.5) rather than company facts.
Measured on the xlsx's own 11-row sample: 0/11 pass, because blue-chip
relative volume there is 1.04-1.25, never >=1.5.

This test reproduces that structure against our fixtures to prove the bug is
real and structural (not a one-off data problem), then proves the new
gate+score model in score.py returns a non-empty, sensibly-ordered result on
the same companies.
"""
from fundamentals.normalize import extract_dividends, extract_statements, normalize_info
from fundamentals.providers.fixture_provider import fetch_one
from fundamentals.score import build_report

FIXTURE_TICKERS = ["bbca", "bbri", "tlkm", "cbdk", "mlpt"]


def _legacy_xlsx_screen_pass(row: dict, rel_volume: float, rsi: float, above_mas: bool) -> bool:
    """Faithful reproduction of the xlsx's Screener_Pass formula."""
    pbv = row.get("pbv") or 999
    roe = row.get("roe") or 0
    eps = row.get("eps_ttm") or 0
    value_ok = pbv < 2 or (2 <= pbv <= 4)
    growth_ok = roe >= 0.12 and eps > 0
    tech_ok = (30 <= rsi <= 45 or 50 <= rsi <= 60) and above_mas
    vol_ok = rel_volume >= 1.5
    sentiment_ok = True  # LQ45 & not UMA -- assume true, gives the xlsx its best case
    return value_ok and growth_ok and tech_ok and vol_ok and sentiment_ok


def test_legacy_xlsx_rule_returns_zero_rows_at_measured_relative_volume():
    """Measured: blue-chip relative volume on a normal day is 1.04-1.25.
    Even granting every other gate a pass, Vol_OK alone zeroes the result."""
    passed = []
    for name in FIXTURE_TICKERS:
        outcome = fetch_one(name.upper())
        row = normalize_info(outcome)
        # Best-case assumptions for every criterion the xlsx can't get from
        # fundamentals: RSI in the sweet spot, above MAs -- only rel_volume
        # is held at the measured realistic value.
        ok = _legacy_xlsx_screen_pass(row, rel_volume=1.15, rsi=55, above_mas=True)
        if ok:
            passed.append(name)
    assert passed == [], f"Expected zero passes (reproducing the measured bug), got: {passed}"


def test_new_model_returns_nonzero_on_the_same_universe():
    reports = []
    for name in FIXTURE_TICKERS:
        outcome = fetch_one(name.upper())
        row = normalize_info(outcome)
        stmts = extract_statements(outcome)
        divs = extract_dividends(outcome)
        reports.append(build_report(row, stmts, divs))
    passing = [r for r in reports if r.gates_passed]
    assert len(passing) >= 1, "New model reproduced the xlsx's zero-row bug"


def test_mlpt_fails_valuation_sanity_gate():
    """Measured: MLPT has PBV 73.3, PER 143 -- the specific failure mode the
    xlsx's PBV<2 rule was blind to on the value side but which our sanity
    ceiling (PBV<=6) correctly rejects."""
    outcome = fetch_one("MLPT")
    row = normalize_info(outcome)
    stmts = extract_statements(outcome)
    divs = extract_dividends(outcome)
    report = build_report(row, stmts, divs)
    assert not report.gates_passed
    assert "valuation_sanity_pbv" in report.failed_gates


def test_cbdk_passes_despite_being_a_2025_ipo():
    """Measured: CBDK (IPO Jan 2025) has PER 8.1, PBV 1.9, ROE 20.9% --
    exactly the kind of quality-at-a-reasonable-price name a working screener
    should surface."""
    outcome = fetch_one("CBDK")
    row = normalize_info(outcome)
    stmts = extract_statements(outcome)
    divs = extract_dividends(outcome)
    report = build_report(row, stmts, divs)
    assert report.gates_passed, report.failed_gates
