"""
Dynamic price-range calibration.

Static multipliers derived from 1-year backtest (1247 signals, 50 IDX stocks).
At startup `auto_calibrate()` re-runs a lighter backtest on the top-20 most
liquid stocks and updates the multipliers if the new data shifts the p50/p75
ATR percentiles by more than 10 %.  The result is that buy-zone depth and
sell-target reach automatically adapt to current market conditions (e.g. a
high-vol regime widens the ranges).
"""

from __future__ import annotations
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from services.indicators import compute_indicators, classify_candle

log = logging.getLogger(__name__)

# ── Backtested defaults (derived from research) ─────────────────
# Keys: (signal, vol_tier)  vol_tier = 'low' | 'med' | 'high'
_DEFAULT_TABLE: dict[tuple[str, str], dict] = {
    # STRONG BUY
    ('STRONG BUY', 'low'):  {'buy_depth': 0.75, 'target_lo': 1.5,  'target_hi': 3.0},
    ('STRONG BUY', 'med'):  {'buy_depth': 0.75, 'target_lo': 2.0,  'target_hi': 3.5},
    ('STRONG BUY', 'high'): {'buy_depth': 0.60, 'target_lo': 2.5,  'target_hi': 5.0},
    # BUY
    ('BUY', 'low'):         {'buy_depth': 1.0,  'target_lo': 1.0,  'target_hi': 2.0},
    ('BUY', 'med'):         {'buy_depth': 0.9,  'target_lo': 1.3,  'target_hi': 2.7},
    ('BUY', 'high'):        {'buy_depth': 0.70, 'target_lo': 2.0,  'target_hi': 5.0},
    # SELL (targets are ATR below close)
    ('SELL', 'low'):        {'buy_depth': 0.0,  'target_lo': 1.2,  'target_hi': 2.5},
    ('SELL', 'med'):        {'buy_depth': 0.0,  'target_lo': 1.3,  'target_hi': 2.6},
    ('SELL', 'high'):       {'buy_depth': 0.0,  'target_lo': 1.5,  'target_hi': 3.3},
    # WATCH — fallback
    ('WATCH', 'low'):       {'buy_depth': 1.0,  'target_lo': 1.0,  'target_hi': 1.8},
    ('WATCH', 'med'):       {'buy_depth': 0.9,  'target_lo': 1.2,  'target_hi': 2.2},
    ('WATCH', 'high'):      {'buy_depth': 0.8,  'target_lo': 1.5,  'target_hi': 3.0},
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
            # Target is below close (take-profit for shorts / exit zone)
            sell_low  = int(round(close - target_hi * atr))
            sell_high = int(round(close - target_lo * atr))
        else:
            sell_low  = int(round(close + target_lo * atr))
            sell_high = int(round(close + target_hi * atr))
            # Cap at monthly pivot R1 if it's a meaningful resistance
            if 0 < pivot_r1 < sell_high and pivot_r1 > sell_low:
                sell_high = int(round(pivot_r1))

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
                highs  = [float(df.iloc[i+d]['High']) for d in range(1, 11)]
                lows   = [float(df.iloc[i+d]['Low'])  for d in range(1, 11)]
                if sig['text'] in ('STRONG BUY', 'BUY'):
                    mfe = (max(highs) - close) / atr_v
                    mae = (close - min(lows))  / atr_v
                else:
                    mfe = (close - min(lows))  / atr_v
                    mae = (max(highs) - close) / atr_v
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
            updated['target_lo'] = max(new_target_lo, 0.5)  # floor
        if _shifted(new_target_hi, old.get('target_hi', 0)):
            updated['target_hi'] = max(new_target_hi, updated['target_lo'] + 0.3)

        cal.table[key] = updated

    cal.calibrated = True
    log.info('Calibration complete. Updated table: %s',
             {k: v for k, v in cal.table.items() if v != _DEFAULT_TABLE.get(k)})


# Module-level singleton
calibrator = Calibrator()
