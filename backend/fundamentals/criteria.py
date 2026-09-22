"""The criterion evaluator. This module exists to fix one specific, measured
bug class: pandas silently drops NaN rows on `>=`/`<=` comparisons, which is
exactly how a naive Debt/Equity filter would delete every IDX bank from a
result set with no error and no trace.

Every criterion in this system goes through `evaluate()`, which forces three
explicit, mutually exclusive outcomes for a missing value:

  - "exclude" (default): the criterion is removed from BOTH numerator and
    denominator. Data quality drops, but the company is not punished for a
    hole in the data source.
  - "fail": missing data is treated as a failed gate. Use this only where the
    absence itself is disqualifying (e.g. "must have >=3 years of statements").
  - "zero": the company earns zero points for this criterion but the
    denominator is kept — used where "no data" and "bad data" should score the
    same (e.g. a stock with no dividend history scores like a 0% yield payer).

And a fourth outcome, orthogonal to missing data: "skipped" (`applicable=False`),
for a criterion that plain does not apply to this company's sector (DER for a
bank). Skipped criteria are NEVER a failure and never lower gates_passed.
"""
from __future__ import annotations

import math
from typing import Literal

from .models import CriterionResult, MissingPolicy

Operator = Literal[">=", "<=", ">", "<", "between"]


def _is_missing(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def evaluate(
    *,
    id: str,
    label: str,
    group: str,
    value: float | None,
    operator: Operator,
    threshold: float | None = None,
    threshold_hi: float | None = None,  # only for operator="between"
    unit: str = "",
    source: str = "",
    is_gate: bool = False,
    max_points: float = 0.0,
    points_if_pass: float | None = None,
    missing: MissingPolicy = "exclude",
    applicable: bool = True,
    skip_reason: str | None = None,
) -> CriterionResult:
    if points_if_pass is None:
        points_if_pass = max_points

    if not applicable:
        return CriterionResult(
            id=id, label=label, group=group, status="skipped", value=value, unit=unit,
            operator=operator, threshold=threshold, is_gate=is_gate, points=0.0, max_points=0.0,
            explain=f"{label}: tidak berlaku — {skip_reason or 'tidak relevan untuk profil ini'}",
            source=source, skip_reason=skip_reason,
        )

    if _is_missing(value):
        if missing == "fail":
            return CriterionResult(
                id=id, label=label, group=group, status="fail", value=None, unit=unit,
                operator=operator, threshold=threshold, is_gate=is_gate, points=0.0,
                max_points=max_points, explain=f"{label}: data tidak tersedia — dihitung GUGUR",
                source=source, missing_policy=missing,
            )
        if missing == "zero":
            return CriterionResult(
                id=id, label=label, group=group, status="missing", value=None, unit=unit,
                operator=operator, threshold=threshold, is_gate=is_gate, points=0.0,
                max_points=max_points, explain=f"{label}: data tidak tersedia — skor 0",
                source=source, missing_policy=missing,
            )
        # "exclude": removed from both numerator and denominator
        return CriterionResult(
            id=id, label=label, group=group, status="missing", value=None, unit=unit,
            operator=operator, threshold=threshold, is_gate=is_gate, points=0.0, max_points=0.0,
            explain=f"{label}: data tidak tersedia — dikeluarkan dari skor (penyebut dikurangi)",
            source=source, missing_policy=missing,
        )

    ok = _check(value, operator, threshold, threshold_hi)
    if ok:
        explain = f"{label} {value:.2f}{unit} {_op_label(operator, threshold, threshold_hi)} — memenuhi ambang"
    else:
        explain = f"{label} {value:.2f}{unit} {_op_label(operator, threshold, threshold_hi)} — di bawah ambang"

    return CriterionResult(
        id=id, label=label, group=group, status="pass" if ok else "fail", value=float(value),
        unit=unit, operator=operator, threshold=threshold, is_gate=is_gate,
        points=points_if_pass if ok else 0.0, max_points=max_points, explain=explain, source=source,
    )


def _check(value: float, operator: Operator, threshold: float | None, threshold_hi: float | None) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == "between":
        return threshold <= value <= threshold_hi
    raise ValueError(f"unknown operator: {operator}")


def _op_label(operator: Operator, threshold, threshold_hi) -> str:
    if operator == "between":
        return f"dalam [{threshold}, {threshold_hi}]"
    return f"{operator} {threshold}"


def evaluate_banded(
    *,
    id: str,
    label: str,
    group: str,
    value: float | None,
    bands: list[tuple[float, float, float]],  # (lo, hi, points) ascending or descending by points
    unit: str = "",
    source: str = "",
    max_points: float = 0.0,
    missing: MissingPolicy = "exclude",
    applicable: bool = True,
    skip_reason: str | None = None,
) -> CriterionResult:
    """Graded scoring (not pass/fail): value falls in exactly one band, earns
    that band's points. Used for score pillars where a single hard cutoff would
    recreate the xlsx's all-or-nothing failure mode."""
    if not applicable:
        return CriterionResult(
            id=id, label=label, group=group, status="skipped", value=value, unit=unit,
            operator="band", threshold=None, is_gate=False, points=0.0, max_points=0.0,
            explain=f"{label}: tidak berlaku — {skip_reason or 'tidak relevan untuk profil ini'}",
            source=source, skip_reason=skip_reason,
        )
    if _is_missing(value):
        if missing == "zero":
            return CriterionResult(
                id=id, label=label, group=group, status="missing", value=None, unit=unit,
                operator="band", threshold=None, is_gate=False, points=0.0, max_points=max_points,
                explain=f"{label}: data tidak tersedia — skor 0", source=source, missing_policy=missing,
            )
        return CriterionResult(
            id=id, label=label, group=group, status="missing", value=None, unit=unit,
            operator="band", threshold=None, is_gate=False, points=0.0, max_points=0.0,
            explain=f"{label}: data tidak tersedia — dikeluarkan dari skor (penyebut dikurangi)",
            source=source, missing_policy=missing,
        )
    for lo, hi, pts in bands:
        if lo <= value < hi or (hi == bands[-1][1] and value == hi):
            return CriterionResult(
                id=id, label=label, group=group, status="pass", value=float(value), unit=unit,
                operator="band", threshold=None, is_gate=False, points=pts, max_points=max_points,
                explain=f"{label} {value:.2f}{unit} — {pts:.0f}/{max_points:.0f} poin", source=source,
            )
    # value below the lowest band or above the highest — score 0, denominator kept
    return CriterionResult(
        id=id, label=label, group=group, status="fail", value=float(value), unit=unit,
        operator="band", threshold=None, is_gate=False, points=0.0, max_points=max_points,
        explain=f"{label} {value:.2f}{unit} — di luar semua pita, 0 poin", source=source,
    )
