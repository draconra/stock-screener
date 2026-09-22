"""Data-quality gates. Three tiers: per-row (drop the row), per-snapshot
(abort the whole run), and promotion (writer.py -- a failed snapshot never
touches data/). This module implements the first two; see writer.py for the
third.

The central design property: a bad refresh cannot overwrite a good one
because it never reaches these gates' caller's write path. Everything here
returns a verdict; nothing here mutates disk.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

from . import schema
from .models import SnapshotValidation
from .sector_rules import FINANCIAL_SECTORS

# ─── Tier 1: per-row ──────────────────────────────────────────────────────────

MIN_MARKET_CAP = 1  # sanity floor only; the real liquidity gate lives in config.py
MAX_ABS_PE = 1000.0
MAX_ABS_ROE = 10.0  # roe is a fraction; 10 == 1000%, already absurd
DIV_YIELD_RANGE = (0.0, 100.0)  # percent, per measured convention


def _is_missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def validate_row(row: dict) -> tuple[bool, list[str]]:
    """Returns (ok, reasons). A row that fails ANY check here is dropped from
    the snapshot entirely (not written), and counted against snapshot coverage."""
    reasons = []
    sector = row.get("sector") or ""
    is_financial_sector = sector in FINANCIAL_SECTORS

    for field in schema.REQUIRED_ALWAYS:
        if _is_missing(row.get(field)) or row.get(field) == "":
            reasons.append(f"missing_required:{field}")

    if not is_financial_sector:
        for field in schema.REQUIRED_UNLESS_FINANCIAL:
            if _is_missing(row.get(field)):
                reasons.append(f"missing_required_nonfinancial:{field}")

    currency = row.get("currency")
    if currency and currency != "IDR":
        reasons.append(f"wrong_currency:{currency}")

    price = row.get("price")
    if price is not None and price <= 0:
        reasons.append("nonpositive_price")

    market_cap = row.get("market_cap")
    if market_cap is not None and market_cap <= 0:
        reasons.append("nonpositive_market_cap")

    per = row.get("pe_trailing")
    if per is not None and abs(per) > MAX_ABS_PE:
        reasons.append(f"per_out_of_range:{per}")

    roe = row.get("roe")
    if roe is not None and abs(roe) > MAX_ABS_ROE:
        reasons.append(f"roe_out_of_range:{roe}")

    div_yield = row.get("dividend_yield")
    if div_yield is not None and not (DIV_YIELD_RANGE[0] <= div_yield <= DIV_YIELD_RANGE[1]):
        # THE percent<->fraction canary at row level. If yfinance ever flips
        # the convention, values land in [0,1] and every row trips this.
        reasons.append(f"dividend_yield_out_of_range:{div_yield}")

    return (len(reasons) == 0, reasons)


# ─── Tier 2: per-snapshot ─────────────────────────────────────────────────────

MIN_COVERAGE = 0.85
MAX_FIELD_COVERAGE_DROP_PP = 20.0
MAX_UNIVERSE_SIZE_CHANGE_PCT = 0.15
MAX_MEDIAN_MARKET_CAP_CHANGE_PCT = 0.10
MAX_BIG_MOVER_SHARE = 0.05  # share of universe allowed to move >50% in market cap
BIG_MOVE_THRESHOLD = 0.50
DIV_YIELD_P90_RANGE = (1.0, 20.0)  # sanity band for the percent-convention canary
ANOMALY_PRICE_MOVE_THRESHOLD = 0.80  # flagged, never fatal -- real corporate actions happen


def _field_coverage(rows: list[dict]) -> dict[str, float]:
    if not rows:
        return {f.name: 0.0 for f in schema.FIELDS}
    n = len(rows)
    return {
        f.name: sum(1 for r in rows if not _is_missing(r.get(f.name))) / n
        for f in schema.FIELDS
    }


def validate_snapshot(
    rows: list[dict],
    universe_size: int,
    as_of: str,
    prev_rows: list[dict] | None = None,
    prev_universe_size: int | None = None,
) -> SnapshotValidation:
    failures: list[str] = []
    warnings: list[str] = []
    anomalies: list[dict] = []

    coverage = (len(rows) / universe_size) if universe_size else 0.0
    if coverage < MIN_COVERAGE:
        failures.append(f"coverage {coverage:.2%} below minimum {MIN_COVERAGE:.0%} ({len(rows)}/{universe_size})")

    field_coverage = _field_coverage(rows)

    if prev_rows is not None and prev_rows:
        prev_coverage = _field_coverage(prev_rows)
        for field, cov in field_coverage.items():
            prev_cov = prev_coverage.get(field, 0.0)
            drop_pp = (prev_cov - cov) * 100
            if drop_pp > MAX_FIELD_COVERAGE_DROP_PP:
                failures.append(f"field '{field}' coverage dropped {drop_pp:.1f}pp ({prev_cov:.1%} -> {cov:.1%})")

    if prev_universe_size:
        change = abs(universe_size - prev_universe_size) / prev_universe_size
        if change > MAX_UNIVERSE_SIZE_CHANGE_PCT:
            failures.append(f"universe size changed {change:.1%} ({prev_universe_size} -> {universe_size})")

    if prev_rows:
        prev_by_ticker = {r["ticker"]: r for r in prev_rows}
        movers_pct = []
        big_movers = 0
        price_moves = []
        for r in rows:
            prev = prev_by_ticker.get(r["ticker"])
            if not prev:
                continue
            mc, prev_mc = r.get("market_cap"), prev.get("market_cap")
            if mc and prev_mc and prev_mc > 0:
                delta = abs(mc - prev_mc) / prev_mc
                movers_pct.append(delta)
                if delta > BIG_MOVE_THRESHOLD:
                    big_movers += 1
            price, prev_price = r.get("price"), prev.get("price")
            if price and prev_price and prev_price > 0:
                price_delta = abs(price - prev_price) / prev_price
                if price_delta > ANOMALY_PRICE_MOVE_THRESHOLD:
                    anomalies.append({"ticker": r["ticker"], "type": "price_move", "pct": round(price_delta * 100, 1)})

        if movers_pct:
            median_move = statistics.median(movers_pct)
            if median_move > MAX_MEDIAN_MARKET_CAP_CHANGE_PCT:
                failures.append(f"median market cap change {median_move:.1%} exceeds {MAX_MEDIAN_MARKET_CAP_CHANGE_PCT:.0%}")
            big_mover_share = big_movers / len(movers_pct)
            if big_mover_share > MAX_BIG_MOVER_SHARE:
                failures.append(f"{big_movers}/{len(movers_pct)} tickers ({big_mover_share:.1%}) moved >50% in market cap -- exceeds {MAX_BIG_MOVER_SHARE:.0%} rate limit")

    div_yields = [r["dividend_yield"] for r in rows if not _is_missing(r.get("dividend_yield"))]
    if len(div_yields) >= 20:
        sorted_yields = sorted(div_yields)
        p90 = sorted_yields[int(len(sorted_yields) * 0.9)]
        if not (DIV_YIELD_P90_RANGE[0] <= p90 <= DIV_YIELD_P90_RANGE[1]):
            failures.append(
                f"dividend_yield p90 = {p90:.3f}, outside sanity band {DIV_YIELD_P90_RANGE} "
                "-- possible percent<->fraction unit flip upstream"
            )

    return SnapshotValidation(
        ok=len(failures) == 0,
        as_of=as_of,
        universe_size=universe_size,
        rows_passed=len(rows),
        coverage=coverage,
        failures=failures,
        warnings=warnings,
        field_coverage=field_coverage,
        anomalies=anomalies,
    )
