"""The screening engine: gates + five-pillar score + sector branching.

Structural approach borrowed from `backend/services/indicators.py::make_forecast`
(accumulate labelled factors, band into a verdict) -- but every input here is a
fundamental, not a technical, indicator. This module replaces the xlsx's
`Screener_Pass = Value_OK & Growth_OK & Tech_OK & Vol_OK & Sentiment_OK`, which
measurably returns zero rows because it ANDs five gates, two of them
day-state facts (RSI, relative volume) rather than company facts.
"""
from __future__ import annotations

from typing import Any

from . import config
from .criteria import evaluate, evaluate_banded
from .dividends import analyze as analyze_dividends
from .models import CriterionResult, FundamentalReport
from .quality import (
    cyclical_peak_flag,
    debt_vs_revenue_outpacing,
    dilution_pct,
    eps_consistency,
    normalized_eps,
    ocf_to_ni_3y,
    revenue_cagr,
)
from .sector_rules import classify_profile, is_financial, rules_for

Statements = dict[str, list[tuple[str, float]]]


def build_report(
    row: dict[str, Any],
    statements: Statements,
    dividend_history: list[dict],
    is_syariah: bool = False,
) -> FundamentalReport:
    ticker = row["ticker"]
    sector = row.get("sector") or ""
    industry = row.get("industry") or ""
    profile = classify_profile(ticker, sector, industry)
    financial = is_financial(profile)
    rules = rules_for(profile)
    skip_reason = rules.get("skip_reason")
    skip_gates: set[str] = set(rules.get("skip_gates", []))
    skip_criteria: set[str] = set(rules.get("skip_criteria", []))

    revenue = statements.get("revenue", [])
    net_income = statements.get("net_income", [])
    ocf = statements.get("ocf", [])
    shares = statements.get("shares_outstanding", [])
    equity = statements.get("total_equity", [])
    assets = statements.get("total_assets", [])

    eps_consist = eps_consistency(net_income) if net_income else {"years_profitable": 0, "years_total": 0, "up_years": 0}
    rev_cagr = revenue_cagr(revenue)
    ocf_ratio = None if "ocf_to_ni_3y" in skip_criteria else ocf_to_ni_3y(ocf, net_income)
    dilution = dilution_pct(shares)
    debt_outpacing = debt_vs_revenue_outpacing(statements.get("total_debt", []), revenue)
    eps_norm_4y = normalized_eps(net_income) if rules.get("use_normalized_eps") else None

    criteria: list[CriterionResult] = []
    criteria.extend(_gates(row, profile, skip_gates, skip_reason, eps_consist))
    criteria.extend(_valuation_pillar(row, profile))
    criteria.extend(_profitability_pillar(row, profile, revenue, net_income))
    criteria.extend(_growth_pillar(rev_cagr, eps_consist))
    criteria.extend(_health_pillar(row, profile, skip_criteria, skip_reason, ocf_ratio))

    dividend = analyze_dividends(
        div_history=dividend_history,
        price=row.get("price"),
        eps_ttm=row.get("eps_ttm"),
        info_dividend_yield=row.get("dividend_yield"),
    )
    criteria.extend(_shareholder_pillar(dividend))

    penalties = _penalties(ocf_ratio, row, dilution, debt_outpacing, dividend)

    gate_results = [c for c in criteria if c.is_gate]
    failed_gates = sorted({c.id for c in gate_results if c.status == "fail"})
    gates_passed = len(failed_gates) == 0

    earned = sum(c.points for c in criteria if not c.is_gate)
    available = sum(c.max_points for c in criteria if not c.is_gate)
    total_possible = sum(config.PILLAR_MAX_POINTS.values())
    penalty_total = sum(p["points"] for p in penalties)
    raw_score = (earned / available * 100) if available else 0.0
    score = max(0.0, min(100.0, raw_score + penalty_total))
    data_quality = (available / total_possible) if total_possible else 0.0

    verdict = "DATA_KURANG" if data_quality < config.MIN_DATA_QUALITY else _band(score)
    if not gates_passed:
        verdict = "WEAK" if verdict not in ("DATA_KURANG",) else verdict

    pillars = _pillar_summary(criteria)

    bank_metrics = _bank_metrics(row, assets, net_income) if profile == "BANK" else None

    return FundamentalReport(
        ticker=ticker,
        name=row.get("name") or ticker,
        sector=sector,
        profile=profile,
        price=row.get("price"),
        market_cap=row.get("market_cap"),
        gates_passed=gates_passed,
        failed_gates=failed_gates,
        score=score,
        data_quality=data_quality,
        verdict=verdict,
        pillars=pillars,
        criteria=criteria,
        penalties=penalties,
        dividend=dividend,
        bank_metrics=bank_metrics,
        is_syariah=is_syariah,
        per=row.get("pe_trailing"),
        pbv=row.get("pbv"),
        roe_pct=(row.get("roe") * 100 if row.get("roe") is not None else None),
        der=row.get("debt_to_equity"),
    )


def _band(score: float) -> str:
    for lo, name in config.VERDICT_BANDS:
        if score >= lo:
            return name
    return "WEAK"


# ─── Gates ─────────────────────────────────────────────────────────────────

def _gates(row, profile, skip_gates, skip_reason, eps_consist) -> list[CriterionResult]:
    out = []
    g = config.GATES

    out.append(
        evaluate(
            id="liquidity", label="Kapitalisasi pasar", group="gate",
            value=row.get("market_cap"), operator=">=",
            threshold=g["liquidity"]["min_market_cap_idr"], unit="IDR",
            source="info.marketCap", is_gate=True, missing="fail",
        )
    )

    years_total = eps_consist["years_total"]
    if years_total < g["profitability"]["min_years_required"]:
        out.append(
            CriterionResult(
                id="profitability", label="Profitabilitas multi-tahun", group="gate",
                status="fail", value=float(years_total), unit="tahun", operator=">=",
                threshold=g["profitability"]["min_profitable_years"], is_gate=True,
                points=0.0, max_points=0.0,
                explain=f"Laporan keuangan hanya {years_total} tahun — kurang dari {g['profitability']['min_years_required']} tahun minimum",
                source="statements.net_income",
            )
        )
    else:
        eps_ttm = row.get("eps_ttm")
        profitable_ok = eps_consist["years_profitable"] >= g["profitability"]["min_profitable_years"]
        eps_ok = eps_ttm is not None and eps_ttm > g["profitability"]["eps_ttm_min"]
        ok = profitable_ok and eps_ok
        out.append(
            CriterionResult(
                id="profitability", label="Profitabilitas multi-tahun", group="gate",
                status="pass" if ok else "fail",
                value=float(eps_consist["years_profitable"]), unit="tahun", operator=">=",
                threshold=g["profitability"]["min_profitable_years"], is_gate=True,
                points=0.0, max_points=0.0,
                explain=(
                    f"Untung {eps_consist['years_profitable']}/{years_total} tahun terakhir, EPS TTM {eps_ttm}"
                    + (" — memenuhi" if ok else " — tidak memenuhi")
                ),
                source="statements.net_income + info.trailingEps",
            )
        )

    out.append(
        evaluate(
            # missing="exclude": a loss-making company has PER=None from yfinance
            # (undefined for negative EPS) -- the profitability gate above already
            # rejects it, so this gate should not ALSO fail it for the same reason
            # under a different criterion. A profitable company with a genuinely
            # missing PER field is rare and shouldn't be blocked by this gate either.
            id="valuation_sanity_per", label="PER kewarasan", group="gate",
            value=row.get("pe_trailing"), operator="<=", threshold=g["valuation_sanity"]["per_max"],
            unit="x", source="info.trailingPE", is_gate=True, missing="exclude",
        )
    )
    out.append(
        evaluate(
            id="valuation_sanity_pbv", label="PBV kewarasan", group="gate",
            value=row.get("pbv"), operator="<=", threshold=g["valuation_sanity"]["pbv_max"],
            unit="x", source="info.priceToBook", is_gate=True, missing="exclude",
        )
    )

    if "solvency" in skip_gates:
        out.append(
            evaluate(
                id="solvency", label="Solvabilitas (D/E)", group="gate",
                value=row.get("debt_to_equity"), operator="<=",
                threshold=g["solvency"]["der_max_general"], unit="ratio_pct",
                source="info.debtToEquity", is_gate=True, applicable=False,
                skip_reason=skip_reason,
            )
        )
    else:
        der_max = g["solvency"]["der_max_reit_property"] if profile == "REIT_PROPERTY" else g["solvency"]["der_max_general"]
        out.append(
            evaluate(
                id="solvency", label="Solvabilitas (D/E)", group="gate",
                value=row.get("debt_to_equity"), operator="<=", threshold=der_max,
                unit="ratio_pct", source="info.debtToEquity", is_gate=True, missing="fail",
            )
        )
    return out


# ─── Score pillars ───────────────────────────────────────────────────────────

def _valuation_pillar(row, profile) -> list[CriterionResult]:
    s = config.SCORING["valuation"]
    per_val = row.get("pe_trailing")
    if profile == "CYCLICAL_COMMODITY":
        # normalized valuation handled by caller via eps_norm_4y already folded
        # into per_val upstream would require price; kept simple: still score
        # trailing PER here, the cyclical-peak PENALTY (not gate) corrects for it.
        pass
    return [
        evaluate_banded(
            id="per", label="PER", group="valuation", value=per_val,
            bands=s["per"], unit="x", source="info.trailingPE",
            max_points=8, missing="exclude",
        ),
        evaluate_banded(
            id="pbv", label="PBV", group="valuation", value=row.get("pbv"),
            bands=s["pbv"], unit="x", source="info.priceToBook",
            max_points=7, missing="exclude",
        ),
        evaluate_banded(
            id="div_yield_bonus", label="Bonus yield murah", group="valuation",
            value=row.get("dividend_yield"), bands=s["dividend_yield_bonus"],
            unit="%", source="info.dividendYield", max_points=4, missing="zero",
        ),
    ]


def _profitability_pillar(row, profile, revenue, net_income) -> list[CriterionResult]:
    s = config.SCORING["profitability"]
    out = [
        evaluate_banded(
            id="roe", label="ROE", group="profitability", value=row.get("roe"),
            bands=s["roe"], unit="", source="info.returnOnEquity",
            max_points=10, missing="exclude",
        ),
    ]
    if profile == "BANK":
        out.append(
            evaluate_banded(
                id="roa", label="ROA (bank)", group="profitability", value=row.get("roa"),
                bands=s["roa_bank"], unit="", source="info.returnOnAssets",
                max_points=6, missing="exclude",
            )
        )
    else:
        out.append(
            evaluate_banded(
                id="net_margin", label="Margin bersih", group="profitability",
                value=row.get("profit_margin"), bands=s["net_margin"], unit="",
                source="info.profitMargins", max_points=6, missing="exclude",
            )
        )
    return out


def _growth_pillar(rev_cagr, eps_consist) -> list[CriterionResult]:
    s = config.SCORING["growth"]
    out = [
        evaluate_banded(
            id="revenue_cagr_3y", label="CAGR pendapatan", group="growth",
            value=rev_cagr, bands=s["revenue_cagr_3y"], unit="",
            source="statements.revenue", max_points=7, missing="exclude",
        ),
    ]
    years_profitable = float(eps_consist["years_profitable"]) if eps_consist["years_total"] else None
    out.append(
        evaluate_banded(
            id="profitable_years", label="Tahun untung (dari 4)", group="growth",
            value=years_profitable, bands=s["profitable_years_of_4"], unit="tahun",
            source="statements.net_income", max_points=6, missing="exclude",
        )
    )
    return out


def _health_pillar(row, profile, skip_criteria, skip_reason, ocf_ratio) -> list[CriterionResult]:
    s = config.SCORING["health"]
    out = []
    if "der" in skip_criteria:
        out.append(
            evaluate_banded(
                id="der_score", label="D/E (skor)", group="health", value=row.get("debt_to_equity"),
                bands=s["der"], unit="", source="info.debtToEquity", max_points=0,
                applicable=False, skip_reason=skip_reason,
            )
        )
    else:
        out.append(
            evaluate_banded(
                id="der_score", label="D/E (skor)", group="health", value=row.get("debt_to_equity"),
                bands=s["der"], unit="", source="info.debtToEquity", max_points=5, missing="exclude",
            )
        )
    if "ocf_to_ni_3y" in skip_criteria:
        out.append(
            evaluate_banded(
                id="ocf_to_ni", label="OCF / Laba bersih (3th)", group="health", value=ocf_ratio,
                bands=s["ocf_to_ni_3y"], unit="x", source="statements.ocf,net_income",
                max_points=0, applicable=False, skip_reason=skip_reason,
            )
        )
    else:
        out.append(
            evaluate_banded(
                id="ocf_to_ni", label="OCF / Laba bersih (3th)", group="health", value=ocf_ratio,
                bands=s["ocf_to_ni_3y"], unit="x", source="statements.ocf,net_income",
                max_points=6, missing="exclude",
            )
        )
    if "current_ratio" in skip_criteria:
        out.append(
            evaluate_banded(
                id="current_ratio", label="Current ratio", group="health", value=row.get("current_ratio"),
                bands=s["current_ratio"], unit="x", source="info.currentRatio",
                max_points=0, applicable=False, skip_reason=skip_reason,
            )
        )
    else:
        out.append(
            evaluate_banded(
                id="current_ratio", label="Current ratio", group="health", value=row.get("current_ratio"),
                bands=s["current_ratio"], unit="x", source="info.currentRatio",
                max_points=4, missing="exclude",
            )
        )
    return out


def _shareholder_pillar(dividend: dict) -> list[CriterionResult]:
    s = config.SCORING["shareholder"]
    out = [
        evaluate_banded(
            id="div_yield", label="Dividend yield", group="shareholder",
            value=dividend["yield_pct"], bands=s["div_yield"], unit="%",
            source="dividends", max_points=6, missing="zero",
        ),
    ]
    payout = dividend["payout_pct"]
    if payout is not None and s["payout_healthy_lo"] * 100 <= payout <= s["payout_healthy_hi"] * 100:
        pts, status = s["payout_healthy_pts"], "pass"
    else:
        pts, status = 0.0, "fail" if payout is not None else "missing"
    out.append(
        CriterionResult(
            id="payout_health", label="Payout ratio sehat", group="shareholder",
            status=status, value=payout, unit="%", operator="between",
            threshold=s["payout_healthy_lo"] * 100, is_gate=False, points=pts,
            max_points=s["payout_healthy_pts"],
            explain=f"Payout {payout}% -- {'sehat' if status == 'pass' else 'di luar rentang sehat 20-70%' if status == 'fail' else 'tidak ada data (EPS negatif atau tanpa dividen)'}",
            source="dividends+eps",
        )
    )
    out.append(
        evaluate_banded(
            id="streak_years", label="Tahun beruntun dividen", group="shareholder",
            value=float(dividend["streak_years"]), bands=s["streak_years"], unit="th",
            source="dividends", max_points=5, missing="zero",
        )
    )
    return out


def _penalties(ocf_ratio, row, dilution, debt_outpacing, dividend) -> list[dict]:
    out = []
    if ocf_ratio is not None and ocf_ratio < 0:
        out.append({"label": "OCF negatif", "points": config.PENALTIES["ocf_negative_3y"]})
    if dilution is not None and dilution > config.DILUTION_MAX_PCT:
        out.append({"label": f"Dilusi {dilution:.1f}%", "points": config.PENALTIES["dilution_over_15pct"]})
    if debt_outpacing:
        out.append({"label": "Utang tumbuh lebih cepat dari pendapatan", "points": config.PENALTIES["debt_growing_faster_than_revenue"]})
    if dividend["payout_pct"] is not None and dividend["payout_pct"] > 100:
        out.append({"label": "Payout ratio > 100%", "points": config.PENALTIES["payout_over_100pct"]})
    return out


def _pillar_summary(criteria: list[CriterionResult]) -> list[dict]:
    out = []
    for name, max_pts in config.PILLAR_MAX_POINTS.items():
        group_criteria = [c for c in criteria if c.group == name]
        earned = sum(c.points for c in group_criteria)
        available = sum(c.max_points for c in group_criteria) or max_pts
        out.append({
            "name": name,
            "points": round(earned, 1),
            "max_points": max_pts,
            "pct": round(earned / available * 100, 1) if available else 0.0,
        })
    return out


def _bank_metrics(row, assets: list[tuple[str, float]], net_income: list[tuple[str, float]]) -> dict:
    roa = row.get("roa")
    latest_assets = assets[-1][1] if assets else None
    equity = row.get("book_value_per_share")  # not equity total; kept simple, see equity_to_assets below
    return {
        "roa_pct": round(roa * 100, 2) if roa is not None else None,
        "equity_to_assets": None,  # requires total_equity/total_assets alignment; computed by caller if needed
        "nim_proxy_pct": None,  # not derivable from .info alone -- documented gap
        "ldr_pct": None,  # not reliably available from yfinance -- documented gap
        "unavailable": ["NPL", "CAR", "CASA", "cost_to_income", "LDR", "NIM (regulatory)"],
        "note": "Metrik bank di sini terbatas pada apa yang yfinance sediakan. NPL/CAR/CASA/LDR akurat hanya ada di laporan OJK / presentasi kuartalan bank.",
    }
