from fundamentals.validate import validate_row


def _base_row(**overrides) -> dict:
    row = {
        "ticker": "TEST", "as_of": "2026-09-22", "name": "Test Co",
        "sector": "Technology", "industry": "Software", "currency": "IDR",
        "price": 1000.0, "market_cap": 2_000_000_000_000, "pe_trailing": 15.0,
        "pbv": 2.0, "roe": 0.15, "debt_to_equity": 50.0, "current_ratio": 1.5,
        "free_cashflow": 100, "dividend_yield": 3.0, "payout_ratio": 0.4,
        "provider": "yfinance", "provider_version": "0.2.65", "schema_version": 1,
    }
    row.update(overrides)
    return row


def test_healthy_nonfinancial_row_passes():
    ok, reasons = validate_row(_base_row())
    assert ok, reasons


def test_nonfinancial_row_with_null_der_fails():
    ok, reasons = validate_row(_base_row(debt_to_equity=None))
    assert not ok
    assert any("debt_to_equity" in r for r in reasons)


def test_financial_sector_row_with_null_der_passes():
    """The measured accounting fact: banks legitimately have no DER. A row
    from the Financial Services sector must NOT be rejected for it."""
    ok, reasons = validate_row(
        _base_row(sector="Financial Services", debt_to_equity=None, free_cashflow=None, current_ratio=None)
    )
    assert ok, reasons


def test_non_idr_currency_rejected():
    ok, reasons = validate_row(_base_row(currency="USD"))
    assert not ok
    assert any("currency" in r for r in reasons)


def test_nonpositive_price_rejected():
    ok, reasons = validate_row(_base_row(price=0))
    assert not ok


def test_dividend_yield_out_of_range_rejected():
    """The percent<->fraction canary at row level: a value like 0.06 (meant
    as 6%) must be caught, not silently accepted as a near-zero yield."""
    ok, reasons = validate_row(_base_row(dividend_yield=150.0))
    assert not ok
    assert any("dividend_yield_out_of_range" in r for r in reasons)


def test_missing_required_always_field_rejected():
    ok, reasons = validate_row(_base_row(sector=""))
    assert not ok
    assert any("missing_required:sector" in r for r in reasons)
