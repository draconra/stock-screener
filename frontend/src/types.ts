export interface Stock {
    ticker: string;
    name: string;
    close: number;
    change: number;
    volume: number;
    relative_volume_10d_calc: number;
    RSI: number;
    signal: string;
    sector: string;
    buy_low: number;
    buy_high: number;
    sell_low: number;
    sell_high: number;
    stop_loss: number;
    update_time?: number;
    is_syariah?: boolean;
    hype_score?: number;
}

export interface GroupedStocks {
    [sector: string]: Stock[];
}

// ─── Fundamental (long-term) screener ──────────────────────────────────
// Separate type family from Stock on purpose: these two tabs cover opposite
// horizons (1-5 day scalp vs multi-year hold) and mixing their fields would
// blur that distinction in the code the same way it would in a UI.

export type FundVerdict = 'STRONG' | 'GOOD' | 'FAIR' | 'WEAK' | 'DATA_KURANG';
export type CriterionStatus = 'pass' | 'fail' | 'warn' | 'skipped' | 'missing';
export type SectorProfile = 'BANK' | 'FINANCIAL_NONBANK' | 'REIT_PROPERTY' | 'CYCLICAL_COMMODITY' | 'GENERAL';

export interface Criterion {
    id: string;
    label: string;
    group: string;
    status: CriterionStatus;
    value: number | null;
    unit: string;
    operator: string;
    threshold: number | null;
    is_gate: boolean;
    points: number;
    max_points: number;
    explain: string;
    source: string;
    skip_reason?: string | null;
    missing_policy?: 'exclude' | 'fail' | 'zero' | null;
}

export interface PillarScore {
    name: string;
    points: number;
    max_points: number;
    pct: number;
}

export interface DividendInfo {
    yield_pct: number | null;
    dps_ttm: number | null;
    payout_pct: number | null;
    payout_band: 'healthy' | 'stretched' | 'unsustainable' | 'n/a';
    streak_years: number;
    paid_in_last_5y: number;
    dps_cagr_5y: number | null;
    last_payment: string | null;
    history?: { year: number; dps: number }[];
}

export interface BankMetrics {
    roa_pct: number | null;
    equity_to_assets: number | null;
    nim_proxy_pct: number | null;
    ldr_pct: number | null;
    unavailable: string[];
    note: string;
}

export interface FundamentalStock {
    ticker: string;
    name: string;
    sector: string;
    profile: SectorProfile;
    price: number | null;
    market_cap: number | null;
    gates_passed: boolean;
    failed_gates: string[];
    score: number;
    data_quality: number;
    verdict: FundVerdict;
    pillars: PillarScore[];
    criteria: Criterion[];
    penalties: { label: string; points: number }[];
    dividend: DividendInfo;
    bank_metrics: BankMetrics | null;
    is_syariah: boolean;
    per: number | null;
    pbv: number | null;
    roe_pct: number | null;
    der: number | null;
}

export interface FundamentalGroups {
    [sector: string]: FundamentalStock[];
}

export interface FundamentalScreenResponse {
    as_of: string | null;
    config_version: string;
    funnel: { stage: string; remaining: number }[];
    counts: { evaluated: number; passed: number; failed: number; insufficient_data: number };
    groups: FundamentalGroups;
    failed: { ticker: string; name: string; failed_gates: string[]; explain: string }[];
}

export interface TrendPoint {
    as_of: string;
    price: string | null;
    market_cap: string | null;
    pe_trailing: string | null;
    pbv: string | null;
    roe: string | null;
    dividend_yield: string | null;
    debt_to_equity: string | null;
    eps_ttm: string | null;
}
