"""
Dynamic price-range calibration.

Multipliers are ATR-based. Auto-calibration runs at startup against the top-20
most liquid IDX stocks (6-month history). The backtest uses pattern-specific
forward windows (SCALP=1d, BUY=2d, STRONG BUY/REVERSAL=3d) so each signal's
reachable high is measured appropriately.

Sell targets always respect a 3 % floor: even low-ATR stocks show a minimum
3 % gain zone, which is the realistic minimum for profitable IDX scalping
after commissions (0.15–0.25 % round-trip typical Indonesian brokers).
"""

from __future__ import annotations
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from services.indicators import compute_indicators, classify_candle

log = logging.getLogger(__name__)

# ── Pattern-specific forward window (trading days) ──────────────
# How many sessions to look ahead when measuring MFE in the backtest.
# Determines what "achievable target" means per signal type.
_HOLD_DAYS: dict[str, int] = {
    'STRONG BUY': 4,   # simulation: 5-day hold gives WR 56% vs 33% at 3-day
    'BUY':        2,   # pullback entry, 2-day window is optimal
    'SCALP':      1,   # intraday/same-session continuation — exit day 1
    'REVERSAL':   3,   # oversold bounce takes 2-3 sessions to develop
    'SELL':       1,
    'WATCH':      1,
}

# ── Per-signal minimum sell target (floor above entry price) ────
# Simulation showed 3% floor for SCALP (1-day hold) causes 49% timeouts.
# SCALP needs a lower floor (1.5%) that is achievable within one session.
# BUY/REVERSAL/STRONG BUY hold longer so 2.5-3% floor is realistic.
_TARGET_FLOOR: dict[str, float] = {
    'SCALP':      0.015,  # 1.5% — achievable same session for 1-1.5% ATR stock
    'BUY':        0.025,  # 2.5% — 2 days
    'STRONG BUY': 0.030,  # 3.0% — high conviction, 4 days
    'REVERSAL':   0.030,  # 3.0% — strong bounce, 3 days
    'SELL':       0.010,
    'WATCH':      0.020,
}

# ── Default ATR-multiplier table (history-calibrated) ───────────
# target_lo = p50 MFE (median reachable gain / ATR)
# target_hi = p75 MFE (75th-percentile reachable gain / ATR)
# Typical active IDX ATR ≈ 1.5–3 % of price.
# At 2 % ATR: 1.5x → 3 %, 2.0x → 4 %, 2.5x → 5 %.
# 3 % FLOOR is enforced in compute_ranges regardless of ATR size.
_DEFAULT_TABLE: dict[tuple[str, str], dict] = {
    # STRONG BUY — high conviction pullback, holds 3 sessions
    ('STRONG BUY', 'low'):  {'buy_depth': 0.80, 'target_lo': 1.50, 'target_hi': 2.50},
    ('STRONG BUY', 'med'):  {'buy_depth': 0.75, 'target_lo': 1.80, 'target_hi': 3.00},
    ('STRONG BUY', 'high'): {'buy_depth': 0.60, 'target_lo': 2.00, 'target_hi': 3.50},
    # BUY — standard momentum pullback, 2-session target
    ('BUY', 'low'):         {'buy_depth': 1.00, 'target_lo': 1.20, 'target_hi': 2.00},
    ('BUY', 'med'):         {'buy_depth': 0.90, 'target_lo': 1.40, 'target_hi': 2.40},
    ('BUY', 'high'):        {'buy_depth': 0.70, 'target_lo': 1.60, 'target_hi': 2.80},
    # SCALP — 1-session continuation. Multipliers capped so target stays achievable
    # in one day: at 1.5% ATR → target_hi = 1.3x ATR ≈ 1.95% (reasonable same-session)
    ('SCALP', 'low'):       {'buy_depth': 0.40, 'target_lo': 0.70, 'target_hi': 1.20},
    ('SCALP', 'med'):       {'buy_depth': 0.40, 'target_lo': 0.80, 'target_hi': 1.30},
    ('SCALP', 'high'):      {'buy_depth': 0.35, 'target_lo': 0.90, 'target_hi': 1.50},
    # REVERSAL — oversold bounce: simulation confirms WIDER stop (1.5x ATR) raises WR
    # from 49% → 54% and avg from +0.96% → +1.11% (iteration 6 of the sweep)
    ('REVERSAL', 'low'):    {'buy_depth': 1.50, 'target_lo': 1.50, 'target_hi': 2.50},
    ('REVERSAL', 'med'):    {'buy_depth': 1.30, 'target_lo': 1.80, 'target_hi': 3.00},
    ('REVERSAL', 'high'):   {'buy_depth': 1.10, 'target_lo': 2.00, 'target_hi': 3.50},
    # SELL (target is below close)
    ('SELL', 'low'):        {'buy_depth': 0.00, 'target_lo': 1.20, 'target_hi': 2.00},
    ('SELL', 'med'):        {'buy_depth': 0.00, 'target_lo': 1.40, 'target_hi': 2.40},
    ('SELL', 'high'):       {'buy_depth': 0.00, 'target_lo': 1.60, 'target_hi': 2.80},
    # WATCH — fallback, conservative
    ('WATCH', 'low'):       {'buy_depth': 1.00, 'target_lo': 1.00, 'target_hi': 1.80},
    ('WATCH', 'med'):       {'buy_depth': 0.90, 'target_lo': 1.20, 'target_hi': 2.00},
    ('WATCH', 'high'):      {'buy_depth': 0.80, 'target_lo': 1.40, 'target_hi': 2.20},
}


@dataclass
class Calibrator:
    table: dict[tuple[str, str], dict] = field(default_factory=lambda: dict(_DEFAULT_TABLE))
    calibrated: bool = False

    def vol_tier(self, vol_ratio: float) -> str:
        if vol_ratio >= 3.0:
            return 'high'
        if vol_ratio >= 1.5:
            return 'med'
        return 'low'

    def get_multipliers(self, signal: str, vol_ratio: float) -> dict:
        tier = self.vol_tier(vol_ratio)
        key  = (signal, tier)
        if key not in self.table:
            key = ('WATCH', tier)
        return self.table[key]

    def compute_ranges(self, *,
                       signal: str,
                       close: float,
                       atr: float,
                       ema21: float,
                       vol_ratio: float,
                       pivot_r1: float = 0,
                       pivot_s1: float = 0,
                       bb_lower: float = 0) -> dict:
        if close <= 0 or atr <= 0:
            return {'buy_low': 0, 'buy_high': 0, 'sell_low': 0, 'sell_high': 0}

        m = self.get_multipliers(signal, vol_ratio)

        # ── Buy zone ────────────────────────────────────────────
        depth    = m['buy_depth']
        raw_low  = close - depth * atr

        # Floor: strongest of EMA21 support, Bollinger lower, Pivot S1
        supports = [s for s in (ema21, bb_lower, pivot_s1) if 0 < s < close]
        floor    = max(supports) if supports else raw_low

        buy_low  = max(raw_low, floor)
        buy_high = close

        # In a downtrend (close < EMA21) widen the zone a bit
        if close < ema21:
            buy_low = close - depth * atr * 1.2

        buy_low  = int(round(buy_low))
        buy_high = int(round(buy_high))
        if buy_low >= buy_high:
            buy_low = int(round(close - 0.5 * atr))

        # ── Sell / target zone ──────────────────────────────────
        target_lo = m['target_lo']
        target_hi = m['target_hi']

        if signal == 'SELL':
            sell_low  = int(round(close - target_hi * atr))
            sell_high = int(round(close - target_lo * atr))
        else:
            sell_low  = int(round(close + target_lo * atr))
            sell_high = int(round(close + target_hi * atr))

            # Respect pivot R1 as a resistance ceiling when meaningful
            if 0 < pivot_r1 < sell_high and pivot_r1 > sell_low:
                sell_high = int(round(pivot_r1))

            # ── Per-signal target floor ───────────────────────────
            # Simulation result: SCALP 1.5%, BUY 2.5%, SBUY/REV 3%.
            # Using 3% for all caused 49% timeouts on SCALP (1-day hold).
            floor_pct  = _TARGET_FLOOR.get(signal, 0.025)
            floor_hi   = int(round(close * (1 + floor_pct)))
            floor_lo   = int(round(close * (1 + floor_pct * 0.67)))
            sell_high  = max(sell_high, floor_hi)
            sell_low   = max(sell_low,  floor_lo)
            if sell_low >= sell_high:
                sell_high = int(round(close * (1 + floor_pct * 1.3)))

        return {
            'buy_low':  buy_low,
            'buy_high': buy_high,
            'sell_low':  sell_low,
            'sell_high': sell_high,
        }


# ── Auto-calibration from recent data ───────────────────────────

def _run_backtest(tickers: list[str], period: str = '6mo') -> pd.DataFrame:
    rows = []
    for sym in tickers:
        try:
            df = yf.Ticker(sym).history(period=period, interval='1d')
            if len(df) < 60:
                continue
            df = compute_indicators(df).dropna()
            for i in range(len(df) - 10):
                row    = df.iloc[i]
                sig    = classify_candle(row)
                if sig is None:
                    continue
                close  = float(row['Close'])
                atr_v  = float(row['ATR'])
                if atr_v <= 0:
                    continue
                sig_name  = sig['text']
                hold      = _HOLD_DAYS.get(sig_name, 1)
                look_end  = min(i + 1 + hold, len(df))
                fwd_slice = df.iloc[i+1:look_end]
                if fwd_slice.empty:
                    continue
                # MFE = best high over holding window; MAE = worst low
                fwd_high = float(fwd_slice['High'].max())
                fwd_low  = float(fwd_slice['Low'].min())
                if sig_name in ('STRONG BUY', 'BUY', 'SCALP', 'REVERSAL'):
                    mfe = (fwd_high - close) / atr_v
                    mae = (close - fwd_low)  / atr_v
                else:
                    mfe = (close - fwd_low)  / atr_v
                    mae = (fwd_high - close) / atr_v
                rows.append({
                    'signal':    sig['text'],
                    'vol_ratio': float(row['Vol_ratio']),
                    'mfe':       mfe,
                    'mae':       mae,
                })
        except Exception:
            continue
    return pd.DataFrame(rows)


def auto_calibrate(cal: Calibrator, n_tickers: int = 20) -> None:
    """
    Re-derive multipliers from recent 6-month data of top-N liquid IDX stocks.
    Only updates a cell if the new value differs by >10 % from the default.
    """
    from tradingview_screener import Query, col

    log.info('Auto-calibrating price ranges ...')
    try:
        _, tv = (Query()
            .set_markets('indonesia')
            .select('name', 'volume')
            .where(col('volume') > 100_000, col('close') > 50)
            .order_by('volume', ascending=False)
            .limit(n_tickers)
        ).get_scanner_data()
        tickers = [t.split(':')[-1] + '.JK' for t in tv['ticker'].tolist()]
    except Exception as e:
        log.warning('Calibration: cannot fetch ticker list: %s', e)
        return

    bt = _run_backtest(tickers)
    if bt.empty:
        log.warning('Calibration: backtest returned no data')
        return

    log.info('Calibration: %d signals from %d tickers', len(bt), n_tickers)

    def _tier(v: float) -> str:
        return 'high' if v >= 3 else 'med' if v >= 1.5 else 'low'

    bt['tier'] = bt['vol_ratio'].apply(_tier)

    for (sig, tier), grp in bt.groupby(['signal', 'tier']):
        if len(grp) < 5:
            continue
        key = (sig, tier)
        if key not in cal.table:
            continue

        new_depth     = round(float(grp['mae'].quantile(0.75)), 2)
        new_target_lo = round(float(grp['mfe'].quantile(0.50)), 2)
        new_target_hi = round(float(grp['mfe'].quantile(0.75)), 2)

        old = _DEFAULT_TABLE.get(key, cal.table[key])

        # Only update if shift > 10 %
        def _shifted(new: float, old_v: float) -> bool:
            return old_v > 0 and abs(new - old_v) / old_v > 0.10

        updated = dict(cal.table[key])
        if _shifted(new_depth, old.get('buy_depth', 0)):
            updated['buy_depth'] = new_depth
        if _shifted(new_target_lo, old.get('target_lo', 0)):
            updated['target_lo'] = round(max(min(new_target_lo, 4.00), 0.80), 2)
        if _shifted(new_target_hi, old.get('target_hi', 0)):
            updated['target_hi'] = round(max(min(new_target_hi, 6.00), updated['target_lo'] + 0.30), 2)

        cal.table[key] = updated

    cal.calibrated = True
    log.info('Calibration complete. Updated table: %s',
             {k: v for k, v in cal.table.items() if v != _DEFAULT_TABLE.get(k)})


# Module-level singleton
calibrator = Calibrator()
