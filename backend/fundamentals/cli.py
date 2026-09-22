"""Entry point for the offline refresh. Run as:

    python -m backend.fundamentals.cli refresh [--dry-run] [--limit N]

One command, no CI-specific branches -- the exact same invocation runs in
GitHub Actions and on your laptop as the manual escape hatch when CI can't
reach Yahoo (rate-limited, blocked IP range, etc).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import normalize, validate, writer
from .providers.yfinance_provider import YFinanceProvider
from .universe import append_events, build_universe, load_registry, save_registry

REPO_ROOT = Path(__file__).resolve().parents[2]


def refresh(dry_run: bool = False, limit: int | None = None, provider=None) -> int:
    provider = provider or YFinanceProvider()
    d = writer.data_dir(REPO_ROOT)
    today = date.today()
    as_of = today.isoformat()

    print(f"[{as_of}] fetching universe...", file=sys.stderr)
    live_universe = provider.fetch_universe()
    registry = load_registry(d / "universe" / "registry.csv")
    to_fetch, updated_registry, events = build_universe(live_universe, registry, today=today)
    if limit:
        to_fetch = to_fetch[:limit]

    print(f"[{as_of}] fetching {len(to_fetch)} tickers sequentially...", file=sys.stderr)
    outcomes = provider.fetch_batch(to_fetch)

    hit_counter: dict = {}
    rows: list[dict] = []
    rejects: list[dict] = []
    statements_by_ticker: dict[str, tuple[dict, list[dict]]] = {}

    for outcome in outcomes:
        row = normalize.normalize_info(outcome)
        if row is None:
            rejects.append({"ticker": outcome.ticker, "reason": outcome.reason})
            continue
        row["provider"] = provider.name
        row["provider_version"] = provider.version
        row["schema_version"] = 1
        ok, reasons = validate.validate_row(row)
        if not ok:
            rejects.append({"ticker": outcome.ticker, "reason": ",".join(reasons)})
            continue
        rows.append(row)
        stmts = normalize.extract_statements(outcome, hit_counter)
        divs = normalize.extract_dividends(outcome)
        statements_by_ticker[outcome.ticker] = (stmts, divs)

    prev_meta_path = d / "_meta" / "latest.json"
    prev_rows: list[dict] = []
    prev_universe_size = None
    if prev_meta_path.exists():
        import json

        prev_meta = json.loads(prev_meta_path.read_text())
        prev_rows = writer.read_snapshot_csv(d / prev_meta["file"])
        prev_universe_size = prev_meta.get("universe_size")

    validation = validate.validate_snapshot(
        rows, universe_size=len(to_fetch), as_of=as_of,
        prev_rows=prev_rows or None, prev_universe_size=prev_universe_size,
    )

    print(f"[{as_of}] coverage={validation.coverage:.1%} rows={len(rows)} rejects={len(rejects)}", file=sys.stderr)
    if not validation.ok:
        print(f"[{as_of}] VALIDATION FAILED:", file=sys.stderr)
        for f in validation.failures:
            print(f"  - {f}", file=sys.stderr)

    exit_code = writer.promote(
        REPO_ROOT, as_of, rows, statements_by_ticker, validation,
        provider.name, provider.version, dry_run=dry_run,
    )

    if exit_code == 0 and not dry_run:
        save_registry(d / "universe" / "registry.csv", updated_registry)
        append_events(d / "universe" / "events.jsonl", events)
        import json

        (d / "_meta").mkdir(parents=True, exist_ok=True)
        field_hits_path = d / "_meta" / "field_resolution.json"
        field_hits_path.write_text(json.dumps(hit_counter, indent=2, sort_keys=True))
        rejects_path = d / "_meta" / "rejects.csv"
        _write_rejects(rejects_path, rejects)

    return exit_code


def _write_rejects(path: Path, rejects: list[dict]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "reason"])
        w.writeheader()
        w.writerows(rejects)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fundamentals")
    sub = parser.add_subparsers(dest="command", required=True)
    p_refresh = sub.add_parser("refresh", help="Fetch, validate, and (unless --dry-run) commit a new snapshot")
    p_refresh.add_argument("--dry-run", action="store_true", help="Validate only; never write to data/")
    p_refresh.add_argument("--limit", type=int, default=None, help="Fetch only the first N tickers (testing)")
    args = parser.parse_args(argv)

    if args.command == "refresh":
        return refresh(dry_run=args.dry_run, limit=args.limit)
    return 1


if __name__ == "__main__":
    sys.exit(main())
