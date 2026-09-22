"""Staging -> promote. A refresh that fails validation never touches
`data/` -- everything happens in `_staging/` first, and only a passing
snapshot gets moved into place. This is the mechanism (not just the intent)
behind "a bad refresh cannot overwrite years of good data."

Two kinds of persisted data, deliberately different shapes:

  - `data/snapshots/*.csv` + `data/by_ticker/*.csv`: OUR OWN monthly history
    of point-in-time ratios (schema.FIELDS). Append-only, one file per month,
    never rewritten -- this is what makes survivorship bias structural rather
    than a policy (a delisted company's rows simply stay in every snapshot it
    was ever part of).

  - `data/statements/<TICKER>.json`: the LATEST fetch of yfinance's own
    trailing ~4-5 year financial statements + full dividend history.
    OVERWRITTEN each refresh, not append-only -- yfinance already returns a
    multi-year trailing window every time, so there is no need to build our
    own history of it. This is what score.py reads for the multi-year quality
    checks (profitable-years gate, OCF/NI, dilution, dividend streak).

Determinism invariant: running the loader twice on identical input produces
byte-identical `snapshots/*.csv`. Fixed column order (schema.csv_fieldnames),
rows sorted by ticker, floats rounded to each field's declared precision,
None written as empty string. Without this, CSV diffs turn into
`0.30000000000000004`-style noise and the git-friendliness argument collapses.
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import schema
from .models import SnapshotValidation

DATA_DIR_NAME = "data"


def data_dir(repo_root: Path) -> Path:
    return repo_root / DATA_DIR_NAME


def _round_value(value: Any, precision: int | None) -> Any:
    if value is None:
        return ""
    if precision is not None and isinstance(value, (int, float)):
        return round(float(value), precision)
    return value


def format_row_for_csv(row: dict) -> dict[str, Any]:
    """Apply schema precision/None handling. Deterministic: same input row ->
    same output dict, every time."""
    out = {}
    for f in schema.FIELDS:
        out[f.name] = _round_value(row.get(f.name), f.precision)
    return out


def write_snapshot_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = schema.csv_fieldnames()
    sorted_rows = sorted(rows, key=lambda r: r["ticker"])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in sorted_rows:
            w.writerow(format_row_for_csv(row))


def read_snapshot_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [coerce_row(r) for r in csv.DictReader(f)]


def coerce_row(raw: dict[str, str]) -> dict[str, Any]:
    """CSV round-trip: "" -> None, numeric strings -> int/float per schema.
    Symmetric with format_row_for_csv so read(write(rows)) == rows."""
    out: dict[str, Any] = {}
    for f in schema.FIELDS:
        v = raw.get(f.name, "")
        if v == "" or v is None:
            out[f.name] = None
        elif f.kind == "int":
            out[f.name] = int(float(v))
        elif f.kind == "float":
            out[f.name] = float(v)
        elif f.kind == "bool":
            out[f.name] = v.lower() in ("true", "1", "yes")
        else:
            out[f.name] = v
    return out


def append_trend_rows(by_ticker_dir: Path, rows: list[dict]) -> None:
    """One line appended per ticker per run. Never rewrites prior lines."""
    by_ticker_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = schema.trend_fieldnames()
    for row in sorted(rows, key=lambda r: r["ticker"]):
        path = by_ticker_dir / f"{row['ticker']}.csv"
        is_new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if is_new:
                w.writeheader()
            trend_row = {k: format_row_for_csv(row)[k] for k in fieldnames}
            w.writerow(trend_row)


def write_statements(statements_dir: Path, ticker: str, statements: dict, dividends: list[dict]) -> None:
    """Overwritten each refresh -- see module docstring for why this is
    correct (yfinance already carries the trailing window; we don't need our
    own accumulation of it)."""
    statements_dir.mkdir(parents=True, exist_ok=True)
    payload = {"statements": statements, "dividends": dividends}
    (statements_dir / f"{ticker}.json").write_text(json.dumps(payload, sort_keys=True))


def read_statements(statements_dir: Path, ticker: str) -> tuple[dict, list[dict]]:
    path = statements_dir / f"{ticker}.json"
    if not path.exists():
        return {}, []
    payload = json.loads(path.read_text())
    return payload.get("statements", {}), payload.get("dividends", [])


def atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    tmp.replace(path)  # atomic on POSIX


def append_run_log(runs_path: Path, entry: dict) -> None:
    """Appended on EVERY attempt, pass or fail -- this is the operational
    history that answers "has this been silently failing for months" when you
    come back after a long absence."""
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    with runs_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def promote(
    repo_root: Path,
    as_of: str,
    rows: list[dict],
    statements_by_ticker: dict[str, tuple[dict, list[dict]]],
    validation: SnapshotValidation,
    provider_name: str,
    provider_version: str,
    dry_run: bool = False,
) -> int:
    """Returns 0 on success, 1 on validation failure (nothing written to
    `data/` in that case) -- matching a CLI exit-code convention so CI can
    fail the job without parsing output."""
    d = data_dir(repo_root)
    staging = d / "_staging"
    staging.mkdir(parents=True, exist_ok=True)

    staged_csv = staging / "snapshot.csv"
    write_snapshot_csv(staged_csv, rows)
    (staging / "report.json").write_text(json.dumps(validation.as_dict(), indent=2, sort_keys=True))

    append_run_log(
        d / "_meta" / "runs.jsonl",
        {
            "as_of": as_of,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": validation.ok,
            "dry_run": dry_run,
            "universe_size": validation.universe_size,
            "rows_passed": validation.rows_passed,
            "coverage": validation.coverage,
            "failures": validation.failures,
        },
    )

    if not validation.ok:
        return 1
    if dry_run:
        return 0

    final_csv = d / "snapshots" / f"{as_of}.csv"
    final_csv.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged_csv), str(final_csv))

    append_trend_rows(d / "by_ticker", rows)

    statements_dir = d / "statements"
    for ticker, (stmts, divs) in statements_by_ticker.items():
        write_statements(statements_dir, ticker, stmts, divs)

    schema_report_path = d / "_meta" / "schema_report.json"
    if schema_report_path.exists():
        shutil.copy(schema_report_path, d / "_meta" / "schema_report_prev.json")
    atomic_write_json(schema_report_path, validation.field_coverage)

    atomic_write_json(
        d / "_meta" / "latest.json",
        {
            "as_of": as_of,
            "file": f"snapshots/{as_of}.csv",
            "rows": len(rows),
            "universe_size": validation.universe_size,
            "coverage": round(validation.coverage, 4),
            "provider": provider_name,
            "provider_version": provider_version,
            "schema_version": schema.SCHEMA_VERSION,
        },
    )
    return 0
