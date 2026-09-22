from datetime import date

from fundamentals.dividends import analyze


def test_yfinance_yield_matches_manual_computation_percent_not_fraction():
    """Measured: BBCA TTM dividends 381 / price 6225 * 100 == 6.12, and
    info.dividendYield == 6.12 independently. Neither 612 nor 0.0612."""
    history = [{"date": "2025-10-01", "amount": 190.0}, {"date": "2026-04-01", "amount": 191.0}]
    result = analyze(div_history=history, price=6225.0, eps_ttm=471.86, info_dividend_yield=6.12, today=date(2026, 9, 22))
    assert 5.0 < result["yield_pct"] < 8.0


def test_no_dividend_history_scores_as_zero_not_excluded():
    result = analyze(div_history=[], price=1000.0, eps_ttm=50.0, info_dividend_yield=None)
    assert result["yield_pct"] == 0.0
    assert result["streak_years"] == 0
    assert result["payout_pct"] is None


def test_payout_none_when_eps_negative():
    history = [{"date": "2026-01-01", "amount": 10.0}]
    result = analyze(div_history=history, price=1000.0, eps_ttm=-50.0, info_dividend_yield=1.0, today=date(2026, 9, 22))
    assert result["payout_pct"] is None


def test_tlkm_like_streak_is_multi_year():
    """TLKM fixture measured: 29 dividend entries spanning 2004-2026, paid
    every year recently. Streak should be several years, not 0 or 1."""
    history = [{"date": f"{y}-06-01", "amount": 200.0 + y} for y in range(2018, 2027)]
    result = analyze(div_history=history, price=2490.0, eps_ttm=170.0, info_dividend_yield=8.0, today=date(2026, 9, 22))
    assert result["streak_years"] >= 5


def test_streak_breaks_on_a_skipped_year():
    history = [{"date": "2020-06-01", "amount": 100.0}, {"date": "2021-06-01", "amount": 100.0}]
    # 2022, 2023, 2024, 2025 all skipped -- streak counted from last COMPLETE
    # year (today.year - 1 = 2025) backwards, so this should be 0.
    result = analyze(div_history=history, price=1000.0, eps_ttm=50.0, info_dividend_yield=None, today=date(2026, 9, 22))
    assert result["streak_years"] == 0


def test_payout_bands():
    from fundamentals.dividends import _payout_band

    assert _payout_band(None) == "n/a"
    assert _payout_band(50.0) == "healthy"
    assert _payout_band(95.0) == "stretched"
    assert _payout_band(120.0) == "unsustainable"
