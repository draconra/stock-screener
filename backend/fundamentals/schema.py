"""Pinned column set for the fundamentals store.

This is the single source of truth for what a fundamentals row contains, what
unit each field is in, whether it's required, and whether it belongs in the
per-ticker trend file. Every other module (normalize, validate, writer,
store, screen) derives from this — nobody hardcodes a field name elsewhere.

Measured facts encoded here (2026-09-22, from live yfinance 0.2.65 .info):
  - dividendYield is ALREADY PERCENT (BBCA info.dividendYield == 6.12, and
    381/6225*100 == 6.12 computed independently). Do not scale it.
  - returnOnEquity, payoutRatio, returnOnAssets are FRACTIONS (0.21818 == 21.8%).
  - Banks (sector == "Financial Services") return None for debtToEquity,
    freeCashflow, currentRatio. This is correct accounting, not missing data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = 1

Kind = Literal["str", "int", "float", "bool"]
Required = Literal["always", "unless_financial", "no"]


@dataclass(frozen=True)
class FieldSpec:
    name: str  # our canonical column name
    source: str | None  # the yfinance .info key; None = derived, not from .info
    kind: Kind
    precision: int | None = None  # decimals on write; keeps CSV output deterministic
    required: Required = "no"
    unit: str = ""  # "IDR" | "percent" | "fraction" | "ratio(x)" | "years" | ""
    trend: bool = False  # include in data/by_ticker/<TICKER>.csv


FIELDS: tuple[FieldSpec, ...] = (
    # Identity / provenance — always present, never derived from a rounded ratio
    FieldSpec("as_of", None, "str", required="always", trend=True),
    FieldSpec("ticker", None, "str", required="always", trend=True),
    FieldSpec("name", "longName", "str"),
    FieldSpec("sector", "sector", "str", required="always", trend=True),
    FieldSpec("industry", "industry", "str", required="always"),
    FieldSpec("currency", "currency", "str", required="always"),
    FieldSpec("quote_type", "quoteType", "str"),
    # Price / size
    FieldSpec("price", "currentPrice", "float", 2, "always", "IDR", trend=True),
    FieldSpec("market_cap", "marketCap", "int", None, "always", "IDR", trend=True),
    FieldSpec("shares_outstanding", "sharesOutstanding", "int"),
    # Valuation
    FieldSpec("pe_trailing", "trailingPE", "float", 4, unit="x", trend=True),
    FieldSpec("pe_forward", "forwardPE", "float", 4, unit="x"),
    FieldSpec("pbv", "priceToBook", "float", 4, unit="x", trend=True),
    FieldSpec("eps_ttm", "trailingEps", "float", 2, unit="IDR", trend=True),
    FieldSpec("book_value_per_share", "bookValue", "float", 2, unit="IDR"),
    # Profitability — fractions (0.15 == 15%)
    FieldSpec("roe", "returnOnEquity", "float", 6, unit="fraction", trend=True),
    FieldSpec("roa", "returnOnAssets", "float", 6, unit="fraction", trend=True),
    FieldSpec("profit_margin", "profitMargins", "float", 6, unit="fraction"),
    FieldSpec("operating_margin", "operatingMargins", "float", 6, unit="fraction"),
    FieldSpec("earnings_growth", "earningsGrowth", "float", 6, unit="fraction"),
    FieldSpec("revenue_growth", "revenueGrowth", "float", 6, unit="fraction"),
    # Solvency — None for financials is CORRECT, not missing (see REQUIRED_UNLESS_FINANCIAL)
    FieldSpec(
        "debt_to_equity",
        "debtToEquity",
        "float",
        4,
        required="unless_financial",
        unit="ratio_pct",  # yfinance reports this as e.g. 59.98, i.e. 59.98%, not 0.5998
        trend=True,
    ),
    FieldSpec("current_ratio", "currentRatio", "float", 4, required="unless_financial", unit="x"),
    FieldSpec("free_cashflow", "freeCashflow", "int", None, "unless_financial", "IDR"),
    FieldSpec("total_cash", "totalCash", "int", None, "no", "IDR"),
    FieldSpec("total_debt", "totalDebt", "int", None, "no", "IDR"),
    # Dividends — dividendYield is ALREADY PERCENT. See module docstring.
    FieldSpec("dividend_yield", "dividendYield", "float", 4, unit="percent", trend=True),
    FieldSpec("payout_ratio", "payoutRatio", "float", 6, unit="fraction", trend=True),
    FieldSpec("five_year_avg_dividend_yield", "fiveYearAvgDividendYield", "float", 4, unit="percent"),
    # Provenance — every row carries where it came from and under what rules
    FieldSpec("provider", None, "str", required="always"),
    FieldSpec("provider_version", None, "str", required="always"),
    FieldSpec("schema_version", None, "int", required="always"),
)

FIELDS_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in FIELDS}
TREND_FIELDS: tuple[FieldSpec, ...] = tuple(f for f in FIELDS if f.trend)

# Fields required on every row, regardless of sector.
REQUIRED_ALWAYS: tuple[str, ...] = tuple(f.name for f in FIELDS if f.required == "always")

# Fields required UNLESS the row's sector is a financial sector (see sector_rules.py).
# BBCA/BBRI/BMRI/BRIS all measured with debtToEquity=None, freeCashflow=None,
# currentRatio=None — correct accounting for a deposit-funded institution, not a
# fetch failure. Treating these as globally required silently drops every bank.
REQUIRED_UNLESS_FINANCIAL: tuple[str, ...] = tuple(
    f.name for f in FIELDS if f.required == "unless_financial"
)

_KNOWN_INFO_KEYS_PATH = Path(__file__).parent / "known_info_keys.json"


def known_info_keys() -> frozenset[str]:
    """Snapshot of yfinance 0.2.65 .info keys, captured 2026-09-22 across 5 IDX
    tickers (bank + non-financial + small cap + extreme valuation). Drift against
    this set is measured and logged in validate.py, not silently absorbed."""
    return frozenset(json.loads(_KNOWN_INFO_KEYS_PATH.read_text()))


def csv_fieldnames() -> list[str]:
    """Column order for full snapshot files. Fixed order is required for the
    determinism invariant: two runs on identical input must produce byte-identical
    CSV, or git diffs turn into column-reordering noise."""
    return [f.name for f in FIELDS]


def trend_fieldnames() -> list[str]:
    return [f.name for f in TREND_FIELDS]
