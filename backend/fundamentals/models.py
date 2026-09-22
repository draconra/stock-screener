"""Data types shared across the fundamentals pipeline. Stdlib only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["pass", "fail", "warn", "skipped", "missing"]
MissingPolicy = Literal["exclude", "fail", "zero"]


@dataclass(frozen=True)
class FetchOutcome:
    """One provider fetch attempt for one ticker. Providers never raise for a
    normal failure (delisted ticker, network hiccup) — they report it here."""

    ticker: str
    ok: bool
    raw: dict[str, Any]  # provider-native keys, completely untouched
    reason: str | None = None  # "empty_info" | "no_price" | "exception:<Type>" | ...
    fetched_at: str = ""  # ISO-8601 UTC


@dataclass(frozen=True)
class CriterionResult:
    """One evaluated criterion (a gate or a scored line item). The `explain`
    string is what the UI shows verbatim — it must never be a bare number."""

    id: str
    label: str
    group: str  # pillar name, or "gate"
    status: Status
    value: float | None
    unit: str
    operator: str
    threshold: float | None
    is_gate: bool
    points: float
    max_points: float  # 0 when excluded from the denominator
    explain: str
    source: str = ""
    skip_reason: str | None = None
    missing_policy: MissingPolicy | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "group": self.group,
            "status": self.status,
            "value": self.value,
            "unit": self.unit,
            "operator": self.operator,
            "threshold": self.threshold,
            "is_gate": self.is_gate,
            "points": round(self.points, 2),
            "max_points": round(self.max_points, 2),
            "explain": self.explain,
            "source": self.source,
            "skip_reason": self.skip_reason,
            "missing_policy": self.missing_policy,
        }


@dataclass
class FundamentalReport:
    """Full per-ticker screening result. This is what the API serializes."""

    ticker: str
    name: str
    sector: str
    profile: str
    price: float | None
    market_cap: float | None
    gates_passed: bool
    failed_gates: list[str]
    score: float
    data_quality: float
    verdict: str
    pillars: list[dict]
    criteria: list[CriterionResult]
    penalties: list[dict]
    dividend: dict
    bank_metrics: dict | None
    is_syariah: bool
    per: float | None = None
    pbv: float | None = None
    roe_pct: float | None = None
    der: float | None = None

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "profile": self.profile,
            "price": self.price,
            "market_cap": self.market_cap,
            "gates_passed": self.gates_passed,
            "failed_gates": self.failed_gates,
            "score": round(self.score, 1),
            "data_quality": round(self.data_quality, 3),
            "verdict": self.verdict,
            "pillars": self.pillars,
            "criteria": [c.as_dict() for c in self.criteria],
            "penalties": self.penalties,
            "dividend": self.dividend,
            "bank_metrics": self.bank_metrics,
            "is_syariah": self.is_syariah,
            "per": self.per,
            "pbv": self.pbv,
            "roe_pct": self.roe_pct,
            "der": self.der,
        }


@dataclass
class SnapshotValidation:
    ok: bool
    as_of: str
    universe_size: int
    rows_passed: int
    coverage: float
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    field_coverage: dict[str, float] = field(default_factory=dict)
    anomalies: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "as_of": self.as_of,
            "universe_size": self.universe_size,
            "rows_passed": self.rows_passed,
            "coverage": round(self.coverage, 4),
            "failures": self.failures,
            "warnings": self.warnings,
            "field_coverage": {k: round(v, 4) for k, v in self.field_coverage.items()},
            "anomalies": self.anomalies,
        }
