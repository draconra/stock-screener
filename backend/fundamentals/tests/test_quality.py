from fundamentals.quality import (
    cyclical_peak_flag,
    debt_vs_revenue_outpacing,
    dilution_pct,
    eps_consistency,
    normalized_eps,
    ocf_to_ni_3y,
    revenue_cagr,
    roe_stability_cv,
)


def test_revenue_cagr_basic():
    series = [("2022", 100.0), ("2023", 110.0), ("2024", 121.0), ("2025", 133.1)]
    cagr = revenue_cagr(series)
    assert abs(cagr - 0.10) < 0.001


def test_revenue_cagr_none_when_too_short():
    assert revenue_cagr([("2025", 100.0), ("2026", 110.0)]) is None


def test_revenue_cagr_none_when_base_nonpositive():
    assert revenue_cagr([("2023", -10.0), ("2024", 5.0), ("2025", 10.0)]) is None


def test_eps_consistency_counts_profitable_and_up_years():
    series = [("2022", 10.0), ("2023", -5.0), ("2024", 8.0), ("2025", 12.0)]
    result = eps_consistency(series)
    assert result["years_total"] == 4
    assert result["years_profitable"] == 3
    assert result["up_years"] == 2  # 2024>2023 (loss->profit), 2025>2024


def test_ocf_to_ni_3y_measured_bbca_like_ratio():
    """Measured BBCA OCF/NI across 4 years: [1.35, 0.98, 1.19, 0.83] -- all
    healthy. Reproduce with synthetic values in the same ballpark."""
    ni = [("2022", 100.0), ("2023", 110.0), ("2024", 120.0)]
    ocf = [("2022", 135.0), ("2023", 108.0), ("2024", 143.0)]
    ratio = ocf_to_ni_3y(ocf, ni)
    assert ratio is not None and 0.9 < ratio < 1.3


def test_ocf_to_ni_none_when_net_income_negative():
    ni = [("2023", -10.0), ("2024", -5.0)]
    ocf = [("2023", 5.0), ("2024", 5.0)]
    assert ocf_to_ni_3y(ocf, ni) is None


def test_dilution_pct_measures_share_growth():
    series = [("2022", 1_000_000), ("2023", 1_100_000), ("2024", 1_200_000)]
    assert abs(dilution_pct(series) - 20.0) < 0.01


def test_roe_stability_cv_lower_is_more_stable():
    stable_ni = [("2022", 100.0), ("2023", 102.0), ("2024", 101.0)]
    stable_eq = [("2022", 500.0), ("2023", 510.0), ("2024", 505.0)]
    volatile_ni = [("2022", 100.0), ("2023", 20.0), ("2024", 150.0)]
    volatile_eq = [("2022", 500.0), ("2023", 500.0), ("2024", 500.0)]
    stable_cv = roe_stability_cv(stable_ni, stable_eq)
    volatile_cv = roe_stability_cv(volatile_ni, volatile_eq)
    assert stable_cv < volatile_cv


def test_normalized_eps_averages_recent_years():
    series = [("2021", 10.0), ("2022", 12.0), ("2023", 8.0), ("2024", 30.0)]
    assert normalized_eps(series, n=4) == 15.0


def test_cyclical_peak_flag_triggers_above_threshold():
    assert cyclical_peak_flag(eps_ttm=20.0, eps_norm_4y=10.0) is True  # 2.0x > 1.8x
    assert cyclical_peak_flag(eps_ttm=11.0, eps_norm_4y=10.0) is False


def test_debt_outpacing_detected():
    debt = [("2022", 100.0), ("2023", 150.0), ("2024", 250.0)]  # fast growth
    revenue = [("2022", 100.0), ("2023", 105.0), ("2024", 110.0)]  # slow growth
    assert debt_vs_revenue_outpacing(debt, revenue) is True
