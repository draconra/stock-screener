from fundamentals.normalize import extract_dividends, extract_statements, normalize_info
from fundamentals.providers.fixture_provider import fetch_one
from fundamentals.score import build_report


def _report_for(name: str):
    outcome = fetch_one(name.upper())
    row = normalize_info(outcome)
    stmts = extract_statements(outcome)
    divs = extract_dividends(outcome)
    return build_report(row, stmts, divs)


def test_score_is_bounded_and_deterministic():
    for name in ["bbca", "bbri", "tlkm", "cbdk", "mlpt"]:
        r1 = _report_for(name)
        r2 = _report_for(name)
        assert 0 <= r1.score <= 100
        assert r1.score == r2.score


def test_sparse_data_yields_insufficient_not_a_fabricated_number():
    outcome = fetch_one("SPARSE")
    row = normalize_info(outcome)
    stmts = extract_statements(outcome)
    divs = extract_dividends(outcome)
    report = build_report(row, stmts, divs)
    assert report.verdict == "DATA_KURANG"


def test_cbdk_outranks_mlpt_on_score():
    """Measured: CBDK (PER 8.1, PBV 1.9, ROE 20.9%) is a much better
    long-term candidate than MLPT (PER 143, PBV 73.3). The score must reflect
    that even though both might score points on unrelated pillars."""
    cbdk = _report_for("cbdk")
    mlpt = _report_for("mlpt")
    assert cbdk.score > mlpt.score
    assert cbdk.gates_passed and not mlpt.gates_passed


def test_pillars_sum_to_reported_score_components():
    report = _report_for("bbca")
    pillar_names = {p["name"] for p in report.pillars}
    assert pillar_names == {"valuation", "profitability", "growth", "health", "shareholder"}
    for p in report.pillars:
        assert p["points"] <= p["max_points"] + 0.01


def test_criteria_never_contain_a_bare_pass_on_nan_value():
    import math

    for name in ["bbca", "bbri", "tlkm", "cbdk", "mlpt", "sparse"]:
        report = _report_for(name)
        for c in report.criteria:
            if c.value is not None and isinstance(c.value, float):
                assert not math.isnan(c.value), f"{name}/{c.id} has a NaN value that should have been None"
            if c.status == "pass":
                assert c.value is not None
