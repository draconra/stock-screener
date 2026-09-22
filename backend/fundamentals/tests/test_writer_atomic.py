"""The single most valuable test in this suite: it proves a refresh that
fails validation cannot destroy years of accumulated history. If this test
ever fails, the core promise of the whole data-layer design is broken.
"""
import json

from fundamentals.validate import validate_snapshot
from fundamentals.writer import promote


def _good_rows(n: int = 90) -> list[dict]:
    return [
        {
            "ticker": f"T{i:04d}", "as_of": "2026-10-01", "sector": "Technology",
            "industry": "Software", "currency": "IDR", "price": 1000.0,
            "market_cap": 2e12, "pe_trailing": 15.0, "roe": 0.15,
            "dividend_yield": 3.0, "debt_to_equity": 50.0,
            "provider": "yfinance", "provider_version": "0.2.65", "schema_version": 1,
        }
        for i in range(n)
    ]


def test_failed_validation_never_touches_data_dir(tmp_path):
    repo_root = tmp_path
    data_dir = repo_root / "data"

    # Seed a prior "good" snapshot to prove it survives untouched.
    good_rows = _good_rows(90)
    v_good = validate_snapshot(rows=good_rows, universe_size=100, as_of="2026-09-01")
    exit_code = promote(repo_root, "2026-09-01", good_rows, {}, v_good, "yfinance", "0.2.65")
    assert exit_code == 0
    prior_snapshot_path = data_dir / "snapshots" / "2026-09-01.csv"
    assert prior_snapshot_path.exists()
    prior_bytes = prior_snapshot_path.read_bytes()
    prior_latest = json.loads((data_dir / "_meta" / "latest.json").read_text())
    prior_by_ticker_files = sorted((data_dir / "by_ticker").glob("*.csv"))
    assert len(prior_by_ticker_files) == 90

    # Now attempt a BAD refresh: coverage collapses to 20%.
    bad_rows = _good_rows(20)
    v_bad = validate_snapshot(rows=bad_rows, universe_size=100, as_of="2026-10-01")
    assert not v_bad.ok

    exit_code_bad = promote(repo_root, "2026-10-01", bad_rows, {}, v_bad, "yfinance", "0.2.65")
    assert exit_code_bad == 1

    # Nothing under data/ changed: no new snapshot file, latest.json untouched,
    # by_ticker files untouched, byte-for-byte.
    assert not (data_dir / "snapshots" / "2026-10-01.csv").exists()
    assert prior_snapshot_path.read_bytes() == prior_bytes
    assert json.loads((data_dir / "_meta" / "latest.json").read_text()) == prior_latest
    assert sorted((data_dir / "by_ticker").glob("*.csv")) == prior_by_ticker_files
    for f in prior_by_ticker_files:
        # each file still has exactly 1 data row (no line appended from the bad run)
        assert len(f.read_text().splitlines()) == 2  # header + 1 row


def test_dry_run_never_writes_even_on_success(tmp_path):
    rows = _good_rows(90)
    v = validate_snapshot(rows=rows, universe_size=100, as_of="2026-09-01")
    assert v.ok
    exit_code = promote(tmp_path, "2026-09-01", rows, {}, v, "yfinance", "0.2.65", dry_run=True)
    assert exit_code == 0
    assert not (tmp_path / "data" / "snapshots").exists()
    assert not (tmp_path / "data" / "_meta" / "latest.json").exists()


def test_run_log_appended_on_both_success_and_failure(tmp_path):
    rows = _good_rows(90)
    v_ok = validate_snapshot(rows=rows, universe_size=100, as_of="2026-09-01")
    promote(tmp_path, "2026-09-01", rows, {}, v_ok, "yfinance", "0.2.65")

    bad_rows = _good_rows(10)
    v_bad = validate_snapshot(rows=bad_rows, universe_size=100, as_of="2026-10-01")
    promote(tmp_path, "2026-10-01", bad_rows, {}, v_bad, "yfinance", "0.2.65")

    runs_path = tmp_path / "data" / "_meta" / "runs.jsonl"
    lines = runs_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["ok"] is True
    assert json.loads(lines[1])["ok"] is False
