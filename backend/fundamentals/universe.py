"""Ticker universe with a grace period against survivorship bias.

A ticker missing from one live fetch is usually a trading suspension, not a
delisting -- so it is not dropped immediately. Status flips to "delisted" only
after 3 consecutive absences (~3 months at the monthly refresh cadence), and
an event is appended so the reason is auditable later. Renames are the one
case no heuristic catches (a rename looks identical to a simultaneous
delisting + new listing); they are resolved by hand in aliases.json.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CONSECUTIVE_ABSENCES_BEFORE_DELIST = 3
REGISTRY_FIELDS = ["ticker", "first_seen", "last_seen", "status", "name_at_first_seen", "delist_reason", "absences"]


@dataclass
class RegistryEntry:
    ticker: str
    first_seen: str
    last_seen: str
    status: str  # "active" | "delisted"
    name_at_first_seen: str
    delist_reason: str = ""
    absences: int = 0


def load_registry(path: Path) -> dict[str, RegistryEntry]:
    if not path.exists():
        return {}
    out = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["ticker"]] = RegistryEntry(
                ticker=row["ticker"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                status=row["status"],
                name_at_first_seen=row["name_at_first_seen"],
                delist_reason=row.get("delist_reason", ""),
                absences=int(row.get("absences") or 0),
            )
    return out


def save_registry(path: Path, registry: dict[str, RegistryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(registry.values(), key=lambda e: e.ticker)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTRY_FIELDS)
        w.writeheader()
        for e in rows:
            w.writerow(
                {
                    "ticker": e.ticker, "first_seen": e.first_seen, "last_seen": e.last_seen,
                    "status": e.status, "name_at_first_seen": e.name_at_first_seen,
                    "delist_reason": e.delist_reason, "absences": e.absences,
                }
            )


def build_universe(
    live_universe: list[dict],
    registry: dict[str, RegistryEntry],
    today: date | None = None,
) -> tuple[list[str], dict[str, RegistryEntry], list[dict]]:
    """Returns (tickers_to_fetch, updated_registry, events).

    tickers_to_fetch = live tickers this run, UNION recently-vanished tickers
    still inside their grace period (so a suspension doesn't immediately read
    as extinction).
    """
    today = today or date.today()
    today_str = today.isoformat()
    live_by_ticker = {u["ticker"]: u for u in live_universe}
    events: list[dict] = []
    updated = dict(registry)

    for ticker, info in live_by_ticker.items():
        if ticker not in updated:
            updated[ticker] = RegistryEntry(
                ticker=ticker, first_seen=today_str, last_seen=today_str,
                status="active", name_at_first_seen=info.get("name", ticker),
            )
            events.append({"date": today_str, "ticker": ticker, "event": "new_listing"})
        else:
            entry = updated[ticker]
            entry.last_seen = today_str
            entry.absences = 0
            if entry.status == "delisted":
                entry.status = "active"
                events.append({"date": today_str, "ticker": ticker, "event": "relisted_or_false_delist"})

    to_fetch = set(live_by_ticker.keys())
    for ticker, entry in updated.items():
        if ticker in live_by_ticker:
            continue
        if entry.status == "delisted":
            continue  # already confirmed gone, don't keep trying forever
        entry.absences += 1
        if entry.absences >= CONSECUTIVE_ABSENCES_BEFORE_DELIST:
            entry.status = "delisted"
            entry.delist_reason = "vanished_from_universe"
            events.append({"date": today_str, "ticker": ticker, "event": "delisted", "reason": "vanished_from_universe"})
        else:
            to_fetch.add(ticker)  # still inside grace period -- keep trying

    return sorted(to_fetch), updated, events


def append_events(path: Path, events: list[dict]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, sort_keys=True) + "\n")


def load_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())
