"""The NaN bug, encoded as tests. pandas silently drops NaN rows on `>=`/`<=`
comparisons -- this is the mechanism that fixes it: every missing value must
take one of three EXPLICIT paths, never a silent pass.
"""
import math

from fundamentals.criteria import evaluate, evaluate_banded


def test_missing_exclude_shrinks_denominator_not_numerator():
    c = evaluate(
        id="fcf", label="FCF yield", group="health", value=None,
        operator=">=", threshold=3.0, max_points=6, missing="exclude",
    )
    assert c.status == "missing"
    assert c.points == 0
    assert c.max_points == 0  # excluded from denominator too


def test_missing_fail_policy_is_explicit():
    c = evaluate(
        id="eps", label="EPS", group="gate", value=float("nan"),
        operator=">", threshold=0.0, max_points=0, is_gate=True, missing="fail",
    )
    assert c.status == "fail"
    assert "GUGUR" in c.explain


def test_missing_zero_keeps_denominator():
    c = evaluate(
        id="div", label="Dividend yield", group="shareholder", value=None,
        operator=">=", threshold=2.0, max_points=6, missing="zero",
    )
    assert c.status == "missing"
    assert c.points == 0
    assert c.max_points == 6  # kept -- "no dividend" scores like a 0% payer


def test_nan_never_silently_passes_under_any_policy():
    for policy in ("exclude", "fail", "zero"):
        c = evaluate(
            id="x", label="x", group="g", value=float("nan"),
            operator=">=", threshold=1.0, max_points=5, missing=policy,
        )
        assert c.status != "pass"


def test_skipped_is_never_a_failure_and_never_scores():
    c = evaluate(
        id="der", label="D/E", group="gate", value=None, operator="<=",
        threshold=2.0, is_gate=True, applicable=False, skip_reason="bank",
    )
    assert c.status == "skipped"
    assert c.points == 0 and c.max_points == 0


def test_banded_missing_zero_vs_exclude():
    bands = [(0, 1, 5), (1, 2, 3)]
    excl = evaluate_banded(id="a", label="a", group="g", value=None, bands=bands, max_points=5, missing="exclude")
    zero = evaluate_banded(id="a", label="a", group="g", value=None, bands=bands, max_points=5, missing="zero")
    assert excl.max_points == 0
    assert zero.max_points == 5
    assert excl.points == 0 and zero.points == 0


def test_banded_value_lands_in_correct_band():
    bands = [(0, 8, 8), (8, 12, 6), (12, 18, 4), (18, 25, 2), (25, 35, 0)]
    c = evaluate_banded(id="per", label="PER", group="valuation", value=13.19, bands=bands, max_points=8)
    assert c.points == 4  # falls in [12,18)


def test_real_isnan_is_caught_not_just_none():
    assert math.isnan(float("nan"))
    c = evaluate(id="x", label="x", group="g", value=float("nan"), operator=">=", threshold=1.0, missing="exclude")
    assert c.status == "missing"
