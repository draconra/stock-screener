"""Determinism invariant: read(write(rows)) == rows, and writing the same
rows twice produces byte-identical CSV. Without this, git diffs turn into
`0.30000000000000004`-style noise and the whole "CSV is git-friendly"
argument in the plan collapses.
"""
from fundamentals import schema
from fundamentals.writer import coerce_row, format_row_for_csv, write_snapshot_csv


def _sample_row() -> dict:
    row = {f.name: None for f in schema.FIELDS}
    row.update(
        {
            "as_of": "2026-10-01", "ticker": "BBCA", "name": "Bank Central Asia",
            "sector": "Financial Services", "industry": "Banks - Regional",
            "currency": "IDR", "quote_type": "EQUITY", "price": 6200.0,
            "market_cap": 761618833080320, "pe_trailing": 13.139491,
            "pbv": 2.8162463, "roe": 0.21818, "dividend_yield": 6.12,
            "payout_ratio": 0.7542, "debt_to_equity": None, "free_cashflow": None,
            "provider": "yfinance", "provider_version": "0.2.65", "schema_version": 1,
        }
    )
    return row


def test_roundtrip_preserves_values(tmp_path):
    row = _sample_row()
    path = tmp_path / "snap.csv"
    write_snapshot_csv(path, [row])
    with path.open(newline="", encoding="utf-8") as f:
        import csv

        result = coerce_row(next(csv.DictReader(f)))
    assert result["ticker"] == "BBCA"
    assert result["debt_to_equity"] is None  # not coerced to 0 or ""
    assert abs(result["pe_trailing"] - 13.1395) < 0.001  # rounded to schema precision (4dp)
    assert result["dividend_yield"] == 6.12


def test_writing_twice_produces_identical_bytes(tmp_path):
    row = _sample_row()
    p1, p2 = tmp_path / "a.csv", tmp_path / "b.csv"
    write_snapshot_csv(p1, [row])
    write_snapshot_csv(p2, [row])
    assert p1.read_bytes() == p2.read_bytes()


def test_rows_are_sorted_by_ticker_regardless_of_input_order(tmp_path):
    rows = [
        {**{f.name: None for f in schema.FIELDS}, "ticker": "ZZZZ", "as_of": "2026-10-01"},
        {**{f.name: None for f in schema.FIELDS}, "ticker": "AAAA", "as_of": "2026-10-01"},
    ]
    path = tmp_path / "snap.csv"
    write_snapshot_csv(path, rows)
    import csv

    with path.open(newline="", encoding="utf-8") as f:
        tickers = [r["ticker"] for r in csv.DictReader(f)]
    assert tickers == ["AAAA", "ZZZZ"]


def test_none_roundtrips_to_none_not_string_none():
    row = format_row_for_csv({"debt_to_equity": None})
    assert row["debt_to_equity"] == ""
    coerced = coerce_row({"debt_to_equity": ""})
    assert coerced["debt_to_equity"] is None
