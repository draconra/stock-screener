from fundamentals import schema


def test_field_names_are_unique():
    names = [f.name for f in schema.FIELDS]
    assert len(names) == len(set(names))


def test_required_unless_financial_fields_have_no_source_conflicts():
    # debtToEquity/freeCashflow/currentRatio must be the ones exempted for banks
    assert "debt_to_equity" in schema.REQUIRED_UNLESS_FINANCIAL
    assert "free_cashflow" in schema.REQUIRED_UNLESS_FINANCIAL
    assert "current_ratio" in schema.REQUIRED_UNLESS_FINANCIAL


def test_trend_fields_are_a_subset_of_all_fields():
    all_names = {f.name for f in schema.FIELDS}
    trend_names = {f.name for f in schema.TREND_FIELDS}
    assert trend_names <= all_names


def test_dividend_yield_and_roe_have_distinct_documented_units():
    assert schema.FIELDS_BY_NAME["dividend_yield"].unit == "percent"
    assert schema.FIELDS_BY_NAME["roe"].unit == "fraction"


def test_known_info_keys_loads_and_is_nonempty():
    keys = schema.known_info_keys()
    assert len(keys) > 100
    assert "dividendYield" in keys
    assert "returnOnEquity" in keys
