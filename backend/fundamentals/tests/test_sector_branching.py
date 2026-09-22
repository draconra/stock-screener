"""The single most expensive bug this system prevents: a naive Debt/Equity
filter silently deletes every IDX bank from the results. These tests assert
banks not only survive but survive with the RIGHT status (skipped, not
passed-by-coercion like the xlsx's Debt_to_Equity=0 trick).
"""
from fundamentals.normalize import normalize_info
from fundamentals.providers.fixture_provider import fetch_one
from fundamentals.score import build_report
from fundamentals.sector_rules import classify_profile


def _report_for(name: str):
    outcome = fetch_one(name.upper())
    row = normalize_info(outcome)
    from fundamentals.normalize import extract_dividends, extract_statements

    stmts = extract_statements(outcome)
    divs = extract_dividends(outcome)
    return build_report(row, stmts, divs, is_syariah=False)


def test_bbca_classified_bank_via_ticker_even_if_industry_is_none():
    assert classify_profile("BBCA", "Financial Services", None) == "BANK"
    assert classify_profile("BBCA", None, None) == "BANK"  # ticker-set fallback


def test_finance_spelling_also_maps_to_financial_nonbank_when_not_a_known_bank():
    # A hypothetical non-bank financial ticker under TradingView's "Finance" spelling
    assert classify_profile("ZZZZ", "Finance", "Insurance") == "FINANCIAL_NONBANK"


def test_bank_solvency_gate_is_skipped_not_failed():
    report = _report_for("bbca")
    solvency = next(c for c in report.criteria if c.id == "solvency")
    assert solvency.status == "skipped"
    assert "solvency" not in report.failed_gates
    assert report.gates_passed is True  # BBCA fixture is healthy on every other gate


def test_banks_survive_the_screen():
    bbca = _report_for("bbca")
    bbri = _report_for("bbri")
    assert bbca.ticker == "BBCA" and bbri.ticker == "BBRI"
    for r in (bbca, bbri):
        assert r.profile == "BANK"
        # A bank must not be excluded merely for lacking DER/FCF/current_ratio
        assert "solvency" not in r.failed_gates


def test_bank_unavailable_metrics_are_declared_not_zeroed():
    report = _report_for("bbca")
    assert report.bank_metrics is not None
    assert "NPL" in report.bank_metrics["unavailable"]
    assert "CAR" in report.bank_metrics["unavailable"]
    # der must stay None, never coerced to 0 the way the xlsx does
    assert report.der is None


def test_der_health_criterion_skipped_for_bank_not_scored_as_zero():
    report = _report_for("bbca")
    der_score = next(c for c in report.criteria if c.id == "der_score")
    assert der_score.status == "skipped"
    assert der_score.max_points == 0  # not counted against the bank at all
