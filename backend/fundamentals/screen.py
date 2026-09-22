"""Orchestrates the full screen: load stored rows, score each one, group by
sector, apply post-filter views, and report a funnel diagnostic so a
zero-result run is debuggable in seconds instead of a mystery (the failure
mode that made the original xlsx spec useless).

`is_syariah_fn` is injected rather than imported directly from
`backend.services.syariah` -- that module starts a background network thread
on import (fetches the KSEI PDF), which would violate this package's
"fully testable offline" property the moment anything here imported it at
module scope. The real function is wired in by the API layer.
"""
from __future__ import annotations

from typing import Callable

from .models import FundamentalReport
from .score import build_report

IsSyariahFn = Callable[[str], bool]


def _default_is_syariah(_ticker: str) -> bool:
    return False


def score_all(
    rows: list[dict],
    statements_fn: Callable[[str], tuple[dict, list[dict]]],
    is_syariah_fn: IsSyariahFn = _default_is_syariah,
) -> list[FundamentalReport]:
    reports = []
    for row in rows:
        ticker = row["ticker"]
        statements, dividends = statements_fn(ticker)
        report = build_report(row, statements, dividends, is_syariah=is_syariah_fn(ticker))
        reports.append(report)
    return reports


def build_funnel(rows: list[dict], universe_size: int, reports: list[FundamentalReport]) -> list[dict]:
    funnel = [
        {"stage": "universe", "remaining": universe_size},
        {"stage": "fetched_ok", "remaining": len(rows)},
    ]
    remaining = list(reports)
    gate_order = ["liquidity", "profitability", "valuation_sanity_per", "valuation_sanity_pbv", "solvency"]
    seen_gate_labels = {
        "liquidity": "gate: likuiditas",
        "profitability": "gate: profitabilitas",
        "valuation_sanity_per": "gate: kewarasan PER",
        "valuation_sanity_pbv": "gate: kewarasan PBV",
        "solvency": "gate: solvabilitas",
    }
    for gate_id in gate_order:
        skipped = sum(1 for r in remaining if gate_id in [c.id for c in r.criteria if c.status == "skipped"])
        remaining = [r for r in remaining if gate_id not in r.failed_gates]
        label = seen_gate_labels[gate_id]
        if skipped:
            label = f"{label} ({skipped} dilewati: sektor keuangan)"
        funnel.append({"stage": label, "remaining": len(remaining)})
    remaining = [r for r in remaining if r.verdict != "DATA_KURANG"]
    funnel.append({"stage": "data_quality >= ambang", "remaining": len(remaining)})
    return funnel


def apply_filters(
    reports: list[FundamentalReport],
    *,
    min_score: int = 0,
    syariah_only: bool = False,
    sector: str = "",
    max_per: float | None = None,
    min_yield: float | None = None,
    include_failed: bool = False,
) -> list[FundamentalReport]:
    out = []
    for r in reports:
        if not include_failed and not r.gates_passed:
            continue
        if r.score < min_score:
            continue
        if syariah_only and not r.is_syariah:
            continue
        if sector and r.sector != sector:
            continue
        if max_per is not None and (r.per is None or r.per > max_per):
            continue
        if min_yield is not None and (r.dividend["yield_pct"] or 0) < min_yield:
            continue
        out.append(r)
    return out


def group_by_sector(reports: list[FundamentalReport]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for r in sorted(reports, key=lambda x: (-x.score,)):
        grouped.setdefault(r.sector or "Other", []).append(r.as_dict())
    return grouped


def failed_summary(reports: list[FundamentalReport]) -> list[dict]:
    out = []
    for r in reports:
        if r.gates_passed:
            continue
        reasons = [c.explain for c in r.criteria if c.id in r.failed_gates]
        out.append({"ticker": r.ticker, "name": r.name, "failed_gates": r.failed_gates, "explain": "; ".join(reasons)})
    return out
