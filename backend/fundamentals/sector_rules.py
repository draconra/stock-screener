"""Sector -> profile classification, and per-profile gate/criteria overrides.

Measured (2026-09-22): yfinance reports IDX banks under sector "Financial
Services"; TradingView's own `sector` field (used for the scalper universe)
calls the same group "Finance". Both spellings are matched here — a filter
that only recognizes one will silently misclassify banks fetched through the
other source into GENERAL, where the solvency gate then fails them for having
no debtToEquity. That is the single most expensive bug this module prevents.

`industry` from yfinance is sometimes None even for real banks, so a
hardcoded ticker set is the primary path, not a fallback — string matching
alone is not trusted here.
"""
from __future__ import annotations

from typing import Literal

Profile = Literal["BANK", "FINANCIAL_NONBANK", "REIT_PROPERTY", "CYCLICAL_COMMODITY", "GENERAL"]

FINANCIAL_SECTORS = {"Financial Services", "Finance", "Financials"}

# IDX-listed banks (Papan Utama + Papan Pengembangan), by ticker code. Verified
# against the "Banks" sub-industry on IDX; kept as a static set rather than an
# auto-detected one deliberately — see aliases.json note in the writer for the
# same philosophy (detecting this automatically is cleverness we're avoiding).
IDX_BANKS: frozenset[str] = frozenset(
    {
        "BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS", "BDMN", "BNGA", "NISP",
        "BNII", "PNBN", "BJBR", "BJTM", "MEGA", "BTPN", "BTPS", "ARTO", "BBYB",
        "BBHI", "AGRO", "BANK", "BNBA", "BVIC", "BSIM", "MAYA", "BGTG", "BABP",
        "AMAR", "BINA", "SDRA", "BCIC", "BEKS", "NOBU", "DNAR", "MCOR", "BKSW",
        "BBSI", "BBMD", "PNBS", "BNBA", "BACA", "AGRS", "BRIS", "BSWD",
    }
)

IDX_INSURANCE_MULTIFINANCE: frozenset[str] = frozenset(
    {"BFIN", "ADMF", "CFIN", "MREI", "AMAG", "ASRM", "PNLF", "PNIN", "LIFE", "TUGU", "ASBI", "BPFI", "WOMF", "TIFA"}
)

_REIT_INDUSTRY_HINTS = ("reit", "real estate")
_CYCLICAL_INDUSTRY_HINTS = ("coal", "metal", "mining", "oil", "gas", "palm", "agricultural")
_CYCLICAL_SECTORS = {"Energy", "Basic Materials"}


def classify_profile(ticker: str, sector: str | None, industry: str | None) -> Profile:
    t = ticker.upper().replace(".JK", "")
    if t in IDX_BANKS:
        return "BANK"
    if t in IDX_INSURANCE_MULTIFINANCE:
        return "FINANCIAL_NONBANK"

    ind = (industry or "").lower()
    if "bank" in ind:
        return "BANK"
    if (sector or "") in FINANCIAL_SECTORS:
        return "FINANCIAL_NONBANK"
    if any(hint in ind for hint in _REIT_INDUSTRY_HINTS):
        return "REIT_PROPERTY"
    if (sector or "") in _CYCLICAL_SECTORS or any(hint in ind for hint in _CYCLICAL_INDUSTRY_HINTS):
        return "CYCLICAL_COMMODITY"
    return "GENERAL"


def is_financial(profile: Profile) -> bool:
    return profile in ("BANK", "FINANCIAL_NONBANK")


# Per-profile overrides. `skip_gates`/`skip_criteria` entries must produce a
# "skipped" CriterionResult (never "fail") in criteria.py — a skipped gate can
# never cause a ticker to be excluded from the results.
PROFILE_RULES: dict[Profile, dict] = {
    "BANK": {
        "skip_gates": ["solvency"],
        "skip_criteria": ["der", "ocf_to_ni_3y", "current_ratio", "free_cashflow_yield"],
        "skip_reason": "Bank mendanai lewat simpanan nasabah — D/E dan arus kas operasi konvensional tidak bermakna untuk model bisnis ini",
    },
    "FINANCIAL_NONBANK": {
        "skip_gates": ["solvency"],
        "skip_criteria": ["der", "ocf_to_ni_3y"],
        "skip_reason": "Perusahaan pembiayaan/asuransi — leverage tinggi adalah model bisnisnya, bukan tanda risiko",
    },
    "REIT_PROPERTY": {
        "der_max_override": 2.5,
        "skip_reason": None,
    },
    "CYCLICAL_COMMODITY": {
        "use_normalized_eps": True,
        "skip_reason": None,
    },
    "GENERAL": {},
}


def rules_for(profile: Profile) -> dict:
    return PROFILE_RULES.get(profile, {})
