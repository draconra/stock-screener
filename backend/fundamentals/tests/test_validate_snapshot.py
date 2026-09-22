from fundamentals.validate import validate_snapshot


def _rows(n: int, market_cap: float = 2e12, div_yield: float = 5.0) -> list[dict]:
    return [
        {
            "ticker": f"T{i:04d}", "sector": "Technology", "price": 1000.0,
            "market_cap": market_cap, "pe_trailing": 15.0, "roe": 0.15,
            "dividend_yield": div_yield, "debt_to_equity": 50.0, "currency": "IDR",
            "industry": "Software",
        }
        for i in range(n)
    ]


def test_coverage_below_minimum_fails():
    v = validate_snapshot(rows=_rows(40), universe_size=100, as_of="2026-10-01")
    assert not v.ok
    assert any("coverage" in f for f in v.failures)


def test_coverage_above_minimum_passes():
    v = validate_snapshot(rows=_rows(90), universe_size=100, as_of="2026-10-01")
    assert v.ok


def test_isolated_big_movers_pass_real_idx_volatility():
    prev = _rows(200, market_cap=1e12)
    curr = _rows(200, market_cap=1e12)
    # 5 tickers (2.5%) move 60% -- realistic for IDX small caps, must not fail
    for i in range(5):
        curr[i]["market_cap"] = 1.6e12
    v = validate_snapshot(rows=curr, universe_size=200, as_of="2026-10-01", prev_rows=prev, prev_universe_size=200)
    assert v.ok, v.failures


def test_widespread_big_movers_fail_as_corruption():
    prev = _rows(200, market_cap=1e12)
    curr = _rows(200, market_cap=1e12)
    # 200/200 move 60% -- this is a scale/currency bug, not real volatility
    for row in curr:
        row["market_cap"] = 1.6e12
    v = validate_snapshot(rows=curr, universe_size=200, as_of="2026-10-01", prev_rows=prev, prev_universe_size=200)
    assert not v.ok
    assert any("moved >50%" in f or "median market cap" in f for f in v.failures)


def test_dividend_yield_p90_in_fraction_range_fails_as_unit_flip():
    """The percent<->fraction canary at snapshot level: if p90 lands near
    0.06 instead of 6, the whole universe's yield field silently flipped
    convention upstream."""
    rows = _rows(30, div_yield=0.05)  # fraction-shaped values, not percent
    v = validate_snapshot(rows=rows, universe_size=30, as_of="2026-10-01")
    assert not v.ok
    assert any("p90" in f for f in v.failures)


def test_dividend_yield_p90_in_percent_range_passes():
    rows = _rows(30, div_yield=5.0)
    v = validate_snapshot(rows=rows, universe_size=30, as_of="2026-10-01")
    assert v.ok


def test_universe_size_shrinking_a_lot_fails():
    v = validate_snapshot(rows=_rows(90), universe_size=100, as_of="2026-10-01", prev_universe_size=900)
    assert not v.ok
    assert any("universe size" in f for f in v.failures)
