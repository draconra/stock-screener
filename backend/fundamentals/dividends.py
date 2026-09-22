"""Dividend metrics -- the biggest gap in the xlsx spec, which has no dividend
column at all. `div_history` is a list of {"date": "YYYY-MM-DD", "amount": float}
ordered oldest-first (as the provider yields it).

Measured unit fact this module leans on: yfinance's info.dividendYield for IDX
tickers is ALREADY A PERCENT (BBCA: info value 6.12, independently computed
381/6225*100 == 6.12). We compute our own TTM yield from the raw dividend
history rather than trust the upstream field going forward, and use the
upstream value only as a sanity fallback -- see `_sniff_percent`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

PayoutBand = Literal["healthy", "stretched", "unsustainable", "n/a"]


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _sniff_percent(info_yield: float | None, computed: float | None) -> float | None:
    """Defensive fallback only -- prefer `computed`. If upstream ever flips
    convention (fraction vs percent), this keeps a plausible-percent value
    instead of silently returning 0.06 where 6.0 was meant."""
    if computed is not None:
        return computed
    if info_yield is None:
        return None
    return info_yield * 100 if 0 < info_yield < 1 else info_yield


def analyze(
    *,
    div_history: list[dict],
    price: float | None,
    eps_ttm: float | None,
    info_dividend_yield: float | None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    if not div_history:
        return {
            "yield_pct": 0.0,
            "dps_ttm": 0.0,
            "payout_pct": None,
            "payout_band": "n/a",
            "streak_years": 0,
            "paid_in_last_5y": 0,
            "dps_cagr_5y": None,
            "last_payment": None,
            "history": [],
            "source": "no dividend history",
        }

    entries = [(_parse(e["date"]), float(e["amount"])) for e in div_history]
    entries.sort(key=lambda e: e[0])

    one_year_ago = today - timedelta(days=365)
    ttm = sum(amt for d, amt in entries if d > one_year_ago)
    computed_yield = (ttm / price * 100) if price else None
    yield_pct = _sniff_percent(info_dividend_yield, computed_yield)

    by_year: dict[int, float] = {}
    for d, amt in entries:
        by_year[d.year] = by_year.get(d.year, 0.0) + amt

    last_complete_year = today.year - 1
    streak = 0
    y = last_complete_year
    while by_year.get(y, 0) > 0:
        streak += 1
        y -= 1

    paid_in_last_5y = sum(1 for yr in range(today.year - 5, today.year) if by_year.get(yr, 0) > 0)

    payout_pct = (ttm / eps_ttm * 100) if (eps_ttm and eps_ttm > 0) else None
    payout_band = _payout_band(payout_pct)

    years_sorted = sorted(by_year.items())
    dps_cagr_5y = _cagr([v for _, v in years_sorted[-6:]])

    return {
        "yield_pct": round(yield_pct, 2) if yield_pct is not None else None,
        "dps_ttm": round(ttm, 2),
        "payout_pct": round(payout_pct, 1) if payout_pct is not None else None,
        "payout_band": payout_band,
        "streak_years": streak,
        "paid_in_last_5y": paid_in_last_5y,
        "dps_cagr_5y": dps_cagr_5y,
        "last_payment": entries[-1][0].isoformat(),
        "history": [{"year": yr, "dps": round(v, 2)} for yr, v in years_sorted[-10:]],
        "source": "yfinance:dividends",
    }


def _payout_band(payout_pct: float | None) -> PayoutBand:
    if payout_pct is None:
        return "n/a"
    if payout_pct > 100:
        return "unsustainable"
    if payout_pct > 90:
        return "stretched"
    if payout_pct < 0:
        return "n/a"
    return "healthy"


def _cagr(values: list[float]) -> float | None:
    if len(values) < 3 or values[0] <= 0:
        return None
    years = len(values) - 1
    return round(((values[-1] / values[0]) ** (1 / years) - 1) * 100, 2)
