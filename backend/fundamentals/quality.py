"""Multi-year trend checks -- the part that distinguishes a long-term screen
from a point-in-time ratio snapshot. All functions take oldest-to-newest
(date, value) lists (as `normalize.ordered_years()` produces) and return
`None` when there isn't enough data to compute an honest answer, never a
default that looks like a real number.
"""
from __future__ import annotations

from . import config


def _values(series: list[tuple[str, float]]) -> list[float]:
    return [v for _, v in series]


def revenue_cagr(annual_revenue: list[tuple[str, float]]) -> float | None:
    """Oldest -> newest. None if fewer than 3 points or the base year is <= 0
    (a CAGR from zero or negative revenue is not a meaningful number)."""
    if len(annual_revenue) < 3:
        return None
    vals = _values(annual_revenue)
    base, latest = vals[0], vals[-1]
    years = len(vals) - 1
    if base <= 0 or years <= 0:
        return None
    return (latest / base) ** (1 / years) - 1


def eps_consistency(annual_eps: list[tuple[str, float]]) -> dict:
    """{'years_profitable', 'years_total', 'up_years'} -- feeds both the
    profitability GATE and the growth pillar SCORE."""
    vals = _values(annual_eps)
    years_total = len(vals)
    years_profitable = sum(1 for v in vals if v > 0)
    up_years = sum(1 for i in range(1, len(vals)) if vals[i] > vals[i - 1])
    return {"years_profitable": years_profitable, "years_total": years_total, "up_years": up_years}


def ocf_to_ni_3y(ocf: list[tuple[str, float]], ni: list[tuple[str, float]]) -> float | None:
    """mean(OCF last 3y) / mean(NI last 3y). None if fewer than 2 usable
    matched years or mean(NI) <= 0 (ratio against a loss is not meaningful).
    Caller is responsible for skipping this entirely for BANK/FINANCIAL_NONBANK
    profiles -- deposit flows dominate bank OCF and the ratio is noise there,
    not signal."""
    ocf_by_date = dict(ocf)
    ni_by_date = dict(ni)
    common = sorted(set(ocf_by_date) & set(ni_by_date))[-3:]
    if len(common) < 2:
        return None
    mean_ocf = sum(ocf_by_date[d] for d in common) / len(common)
    mean_ni = sum(ni_by_date[d] for d in common) / len(common)
    if mean_ni <= 0:
        return None
    return mean_ocf / mean_ni


def roe_stability_cv(annual_ni: list[tuple[str, float]], annual_equity: list[tuple[str, float]]) -> float | None:
    """Coefficient of variation of yearly ROE (stdev/mean). Lower is more
    stable. None if fewer than 3 matched years or any equity <= 0."""
    ni_by_date = dict(annual_ni)
    eq_by_date = dict(annual_equity)
    common = sorted(set(ni_by_date) & set(eq_by_date))
    if len(common) < 3:
        return None
    roes = []
    for d in common:
        if eq_by_date[d] <= 0:
            return None
        roes.append(ni_by_date[d] / eq_by_date[d])
    mean = sum(roes) / len(roes)
    if mean == 0:
        return None
    variance = sum((r - mean) ** 2 for r in roes) / len(roes)
    return (variance ** 0.5) / abs(mean)


def dilution_pct(shares_series: list[tuple[str, float]]) -> float | None:
    """Cumulative share-count growth oldest -> newest, as a percent. IDX small
    caps rights-issue constantly; >15% over the observed window is a real
    long-term drag on a per-share holder, not noise."""
    vals = _values(shares_series)
    if len(vals) < 2 or vals[0] <= 0:
        return None
    return (vals[-1] / vals[0] - 1) * 100


def debt_vs_revenue_outpacing(
    debt_series: list[tuple[str, float]], revenue_series: list[tuple[str, float]]
) -> bool | None:
    """True when debt grew faster than revenue over the observed window (a
    company borrowing to stand still, or worse). None if either series is
    too short or the base values are non-positive."""
    d_cagr = revenue_cagr(debt_series)  # same CAGR math applies to any series
    r_cagr = revenue_cagr(revenue_series)
    if d_cagr is None or r_cagr is None:
        return None
    return d_cagr > r_cagr + 0.05  # 5pp margin so noise doesn't trigger the penalty


def normalized_eps(annual_eps: list[tuple[str, float]], n: int = 4) -> float | None:
    """Mean EPS over the most recent n years. Used for CYCLICAL_COMMODITY
    valuation (price / this) instead of price/EPS_ttm, so a coal miner at a
    cycle peak doesn't screen as 'PER 3, buy'."""
    vals = _values(annual_eps)[-n:]
    if not vals:
        return None
    return sum(vals) / len(vals)


def cyclical_peak_flag(eps_ttm: float | None, eps_norm_4y: float | None) -> bool:
    if eps_ttm is None or eps_norm_4y is None or eps_norm_4y <= 0:
        return False
    return eps_ttm > config.CYCLICAL_PEAK_RATIO * eps_norm_4y
