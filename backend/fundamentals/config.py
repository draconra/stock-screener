"""Every threshold, weight, and band for the fundamental screener lives here,
and only here. A year from now the question "did this verdict change because
the company changed, or because I moved a number" must be answerable by
diffing this one file — never by hunting through score.py.

Bump CONFIG_VERSION whenever a number below changes. It is stamped on every
API response and every snapshot's report, so historical verdicts stay
attributable to the ruleset that produced them.

Unit note (measured 2026-09-22): yfinance's `debtToEquity` for IDX tickers is
reported as ratio*100 (TLKM raw value 59.982; total_debt/total_equity computed
independently from the balance sheet == 0.6259 == 62.59 -- same order of
magnitude, Yahoo's own D/E figure differs slightly by definition of "debt" but
confirms the *100 convention). So `der_max_*` below are in that same raw unit:
a threshold of 200.0 means "actual debt/equity ratio <= 2.0".
"""
from __future__ import annotations

CONFIG_VERSION = "2026.09.1"

# ─── Gates: sedikit, dan semuanya fundamental (bukan fakta hari-ini) ──────────

GATES = {
    "liquidity": {
        "min_market_cap_idr": 1_000_000_000_000,  # Rp 1 T
    },
    "profitability": {
        "eps_ttm_min": 0.0,
        "min_profitable_years": 3,  # of last 4 reported fiscal years
        "min_years_required": 3,  # fewer than this -> INSUFFICIENT_DATA, not a fail
    },
    "valuation_sanity": {
        "per_max": 35.0,
        "pbv_max": 6.0,
    },
    "solvency": {
        "der_max_general": 200.0,  # raw yfinance units == actual ratio 2.0
        "der_max_reit_property": 250.0,  # actual ratio 2.5
        # NOT applied to BANK / FINANCIAL_NONBANK profiles — see sector_rules.py
    },
}

# ─── Score: lima pilar, 100 poin ──────────────────────────────────────────────

PILLAR_MAX_POINTS = {
    "valuation": 25,
    "profitability": 25,
    "growth": 20,
    "health": 15,
    "shareholder": 15,
}

# (lo, hi, points) bands, ascending value order. See criteria.evaluate_banded.
SCORING = {
    "valuation": {
        "per": [(0, 8, 8), (8, 12, 6), (12, 18, 4), (18, 25, 2), (25, 35, 0)],
        "pbv": [(0, 1.0, 7), (1.0, 2.0, 6), (2.0, 3.0, 4), (3.0, 4.5, 2), (4.5, 6.0, 0)],
        "dividend_yield_bonus": [(0, 2, 0), (2, 4, 2), (4, 999, 4)],  # cheap AND paying is doubly good
        "max_extra": 6,  # remaining points to reach 25 come from valuation-vs-growth checks in score.py
    },
    "profitability": {
        "roe": [(0.20, 999, 10), (0.15, 0.20, 8), (0.12, 0.15, 6), (0.08, 0.12, 3), (0, 0.08, 0)],
        "net_margin": [(0.20, 999, 6), (0.10, 0.20, 4), (0.05, 0.10, 2), (0, 0.05, 0)],
        "roa_bank": [(0.015, 999, 6), (0.010, 0.015, 4), (0.005, 0.010, 2), (0, 0.005, 0)],
    },
    "growth": {
        "revenue_cagr_3y": [(0.15, 999, 7), (0.08, 0.15, 5), (0.03, 0.08, 3), (0, 0.03, 1), (-999, 0, 0)],
        "profitable_years_of_4": [(4, 5, 6), (3, 4, 4), (2, 3, 2), (0, 2, 0)],
    },
    "health": {
        "der": [(0, 50, 5), (50, 100, 4), (100, 150, 3), (150, 200, 1), (200, 999999, 0)],
        "ocf_to_ni_3y": [(1.0, 999, 6), (0.8, 1.0, 4), (0.6, 0.8, 2), (-999, 0.6, 0)],
        "current_ratio": [(2.0, 999, 4), (1.5, 2.0, 3), (1.0, 1.5, 2), (0, 1.0, 0)],
    },
    "shareholder": {
        "div_yield": [(6, 999, 6), (4, 6, 5), (2, 4, 3), (0.5, 2, 1), (0, 0.5, 0)],
        "payout_healthy_lo": 0.20,
        "payout_healthy_hi": 0.70,
        "payout_healthy_pts": 4,
        "streak_years": [(10, 999, 5), (5, 10, 4), (3, 5, 2), (1, 3, 1), (0, 1, 0)],
    },
}

PENALTIES = {
    "ocf_negative_3y": -12,
    "cyclical_peak_earnings": -6,  # TTM EPS > 1.8x 4y mean -> PER is misleadingly low
    "dilution_over_15pct": -6,
    "debt_growing_faster_than_revenue": -5,
    "payout_over_100pct": -5,
}

VERDICT_BANDS = [(75, "STRONG"), (60, "GOOD"), (45, "FAIR"), (0, "WEAK")]
MIN_DATA_QUALITY = 0.50  # below this, verdict is DATA_KURANG regardless of score

DILUTION_MAX_PCT = 15.0
CYCLICAL_PEAK_RATIO = 1.8  # TTM EPS / 4y-mean EPS above this triggers the penalty
