"""The serverless read path. stdlib only -- no pandas, no pyarrow, no duckdb.

Fundamentals data is immutable for the lifetime of a container (the file only
changes via a redeploy, which spins up a new container), so a module-level
cache here is strictly correct and never stale. This replaces the existing
TTL `_cache` pattern in api.py for this feature only -- that pattern exists
because scalper data is live and the cache dies on cold start anyway; this
data doesn't need a TTL because it can't go stale mid-container.
"""
from __future__ import annotations

import functools
import json
from datetime import date
from pathlib import Path

from . import writer
from .universe import load_aliases

DATA_DIR = Path(__file__).resolve().parents[2] / "data"  # backend/fundamentals -> repo root/data
STALE_AFTER_DAYS = 45


def _meta_path() -> Path:
    return DATA_DIR / "_meta" / "latest.json"


def has_data() -> bool:
    return _meta_path().exists()


@functools.lru_cache(maxsize=1)
def meta() -> dict:
    return json.loads(_meta_path().read_text())


@functools.lru_cache(maxsize=1)
def _quarantined_dates() -> frozenset[str]:
    path = DATA_DIR / "_meta" / "quarantine.json"
    if not path.exists():
        return frozenset()
    return frozenset(json.loads(path.read_text()))


@functools.lru_cache(maxsize=1)
def latest_rows() -> tuple[dict, ...]:
    """~240 KB, ~900 rows. Parsed once per cold start, reused for the
    container's life via lru_cache."""
    m = meta()
    as_of = m["as_of"]
    if as_of in _quarantined_dates():
        raise RuntimeError(f"latest snapshot {as_of} is quarantined -- see data/_meta/quarantine.json")
    rows = writer.read_snapshot_csv(DATA_DIR / m["file"])
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    return load_aliases(DATA_DIR / "universe" / "aliases.json")


def _resolve_alias(ticker: str) -> str:
    aliases = _aliases()
    return aliases.get(ticker, ticker)


def trend(ticker: str) -> list[dict]:
    """O(one small file) -- no full-history scan. ~150 B/row; even at 10
    years monthly this is ~18 KB, read fresh each call (not cached, since a
    different ticker is requested each time and the working set could be all
    ~900 tickers over a session -- caching everything would defeat the point
    of per-ticker files)."""
    t = _resolve_alias(ticker.upper())
    path = DATA_DIR / "by_ticker" / f"{t}.csv"
    if not path.exists():
        return []
    return _read_trend_csv(path)


def _read_trend_csv(path: Path) -> list[dict]:
    import csv

    from . import schema

    with path.open(newline="", encoding="utf-8") as f:
        rows = []
        for raw in csv.DictReader(f):
            row = {}
            for fname in schema.trend_fieldnames():
                v = raw.get(fname, "")
                row[fname] = None if v == "" else v
            rows.append(row)
        return rows


def statements_for(ticker: str) -> tuple[dict, list[dict]]:
    t = _resolve_alias(ticker.upper())
    return writer.read_statements(DATA_DIR / "statements", t)


def health() -> dict:
    if not has_data():
        return {"as_of": None, "data_age_days": None, "stale": True, "rows": 0, "error": "no data yet"}
    m = meta()
    age = (date.today() - date.fromisoformat(m["as_of"])).days
    return {**m, "data_age_days": age, "stale": age > STALE_AFTER_DAYS}


def clear_cache() -> None:
    """Test-only: lru_cache is process-global, so tests that swap DATA_DIR via
    monkeypatch must clear it between cases."""
    meta.cache_clear()
    latest_rows.cache_clear()
    _aliases.cache_clear()
    _quarantined_dates.cache_clear()
