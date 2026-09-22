#!/usr/bin/env python3
"""
IDX Scalping Simulation — 10-iteration parameter sweep.

Usage:  python3 simulate.py
Run from backend/ directory.

Each iteration varies one or more key parameters.  The final iteration
combines the best settings found. Results are printed as a comparison table
so the algorithm can be updated with evidence-based values.
"""

from __future__ import annotations
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np

sys.path.insert(0, '.')
from services.indicators import (
    compute_indicators,
    STRONG_BUY_RSI, STRONG_BUY_VOL,
    BUY_RSI, BUY_VOL,
    SCALP_RSI, SCALP_VOL, SCALP_EMA_PROXIMITY,
    REVERSAL_RSI, REVERSAL_VOL, REVERSAL_BB,
)
from services.signal_engine import classify_signal, SignalInputs, SignalThresholds

COMMISSION   = 0.0044   # 0.44% round-trip (Buy: 0.15% + Sell: 0.25% + Levy: 0.04%)
DATA_PERIOD  = '12mo'   # 12-month history

# IDX's Auto Reject Atas/Bawah (ARA/ARB) price-limit bands changed three
# times in recent history: a pandemic-era asymmetric regime (35% up / 7%
# down) ran until ~May 2023, a 15%/15% transition from 5 Jun 2023, then the
# current symmetric bands (Rp50-200: ±35%, >200-5,000: ±25%, >5,000: ±20%)
# took effect 4 Sep 2023. A backtest spanning the older regimes mixes ATR
# and Bollinger-width distributions from three different volatility ceilings.
# DATA_PERIOD='12mo' run from "today" stays entirely inside the current
# regime, so this is a guard for future callers who might widen the window,
# not a behavior change today.
ARA_ARB_REGIME_CHANGE_DATE = pd.Timestamp('2023-09-04', tz=None)

# 30 most liquid IDX names across sectors
IDX_TICKERS = [
    'BBCA.JK', 'BBRI.JK', 'BMRI.JK', 'TLKM.JK', 'ASII.JK',
    'GOTO.JK', 'BELI.JK', 'ADRO.JK', 'PTBA.JK', 'HRUM.JK',
    'ANTM.JK', 'INCO.JK', 'MDKA.JK', 'BRPT.JK', 'TPIA.JK',
    'INDF.JK', 'MYOR.JK', 'KLBF.JK', 'CPIN.JK', 'PGAS.JK',
    'BRIS.JK', 'ACES.JK', 'UNVR.JK', 'ICBP.JK', 'SMGR.JK',
    'BSDE.JK', 'SIDO.JK', 'MEDC.JK', 'JPFA.JK', 'TBIG.JK',
]


# ── Trade config ────────────────────────────────────────────────

@dataclass
class Config:
    label: str = 'Baseline'

    # ── Entry filters
    min_rvol:      float = 1.5
    min_atr_pct:   float = 0.008   # 0.8% minimum ATR/price
    require_ema_up: bool = True     # only long when EMA9 > EMA21

    # ── Signal thresholds
    # Defaults match indicators.py's canonical constants -- the same values
    # screener_service.py and classify_candle() use via signal_engine
    # .classify_signal(). Previously this Config had its own independent
    # defaults (scalp_rsi=(40,60), scalp_ema_prx=0.015) that didn't match
    # either of the other two implementations, so "baseline" backtest
    # results didn't describe what was actually live.
    scalp_rsi:     tuple = SCALP_RSI
    scalp_ema_prx: float = SCALP_EMA_PROXIMITY
    scalp_vol:     float = SCALP_VOL

    reversal_rsi:  float = REVERSAL_RSI
    reversal_bb:   float = REVERSAL_BB
    reversal_vol:  float = REVERSAL_VOL

    buy_rsi:       tuple = BUY_RSI
    buy_vol:       float = BUY_VOL
    buy_pullback:  tuple = (1, 3)  # consecutive down days

    strong_buy_rsi: tuple = STRONG_BUY_RSI
    strong_buy_vol: float = STRONG_BUY_VOL
    strong_buy_pb:  tuple = (2, 3)

    # ── ATR multipliers for targets  (lo = p50, hi = p75 MFE / ATR)
    scalp_tgt:     tuple = (1.0, 1.8)
    buy_tgt:       tuple = (1.4, 2.4)
    strong_buy_tgt: tuple = (1.8, 3.0)
    reversal_tgt:  tuple = (1.8, 3.0)

    # ── Stop loss
    stop_atr_mult:  float = 1.0    # entry - N * ATR
    hard_stop_pct:  float = 0.030  # never more than 3% below entry

    # ── Holding periods (sessions after entry)
    scalp_hold:      int = 1
    buy_hold:        int = 2
    strong_buy_hold: int = 3
    reversal_hold:   int = 3

    # ── Target floor  (sell_high must be at least floor% above entry)
    target_floor:  float = 0.030   # 3% floor


# ── Signal detection ────────────────────────────────────────────
# Delegates to services.signal_engine.classify_signal() -- the same
# function screener_service._signal() and indicators.classify_candle() use.
# Previously this was a third, independent if/elif chain with its own
# condition ordering (REVERSAL, then SCALP, then STRONG BUY, then BUY --
# different from both other implementations) and no TREND-BUY / SELL
# branches at all, so this backtest measured a signal definition that
# didn't match what was actually served to users. `vol >= X` here (vs `>`
# in the other two) is preserved via `>` in classify_signal -- close enough
# not to matter at float precision, not worth a fourth threshold operator.

def detect_signal(row: pd.Series, cfg: Config) -> Optional[str]:
    close = float(row['Close'])
    atr   = float(row['ATR'])
    if close <= 0 or atr <= 0:
        return None
    atr_pct = atr / close
    if float(row['Vol_ratio']) < cfg.min_rvol or atr_pct < cfg.min_atr_pct:
        return None

    ema9  = float(row['EMA9'])
    ema21 = float(row['EMA21'])
    ema50 = float(row['EMA50']) if 'EMA50' in row.index else None
    stoch = float(row['Stoch_K']) if 'Stoch_K' in row.index else None

    ind: SignalInputs = {
        'rsi': float(row['RSI']),
        'vol_ratio': float(row['Vol_ratio']),
        'bb_pct': float(row['BB_pct']),
        'close': close,
        'ema21': ema21,
        'ema_up': ema9 > ema21,
        'ema_stack': (ema9 > ema21 > ema50) if ema50 is not None else None,
        'consec_down': int(row['consec_down']),
        'stoch_k': stoch,
    }
    thresholds = SignalThresholds(
        strong_buy_rsi=cfg.strong_buy_rsi, strong_buy_vol=cfg.strong_buy_vol,
        strong_buy_pullback=cfg.strong_buy_pb,
        buy_rsi=cfg.buy_rsi, buy_vol=cfg.buy_vol, buy_pullback=cfg.buy_pullback,
        scalp_rsi=cfg.scalp_rsi, scalp_vol=cfg.scalp_vol, scalp_ema_proximity=cfg.scalp_ema_prx,
        reversal_rsi=cfg.reversal_rsi, reversal_vol=cfg.reversal_vol, reversal_bb=cfg.reversal_bb,
        require_ema_up=cfg.require_ema_up,
    )
    sig = classify_signal(ind, thresholds)
    # This backtester only models long entries (see simulate() below) -- it
    # has no short/exit trade model, so SELL and WATCH both mean "no trade"
    # here, same as the original contract (this function always returned
    # None for anything but the four long signal types).
    return sig if sig in ('STRONG BUY', 'BUY', 'SCALP', 'REVERSAL') else None


# ── Trade record ────────────────────────────────────────────────

@dataclass
class Trade:
    ticker:      str
    signal:      str
    entry_date:  pd.Timestamp   # needed to build a chronological equity curve in analyze()
    entry_price: float
    stop_price:  float
    target_lo:   float
    target_hi:   float
    exit_price:  float
    exit_reason: str    # 'target' | 'stop' | 'timeout'
    hold_days:   int
    pnl_pct:     float


# ── Simulation engine ───────────────────────────────────────────

def simulate(cfg: Config, data: dict[str, pd.DataFrame]) -> list[Trade]:
    trades: list[Trade] = []
    hold_map = {
        'SCALP':      cfg.scalp_hold,
        'BUY':        cfg.buy_hold,
        'STRONG BUY': cfg.strong_buy_hold,
        'REVERSAL':   cfg.reversal_hold,
    }
    tgt_map = {
        'SCALP':      cfg.scalp_tgt,
        'BUY':        cfg.buy_tgt,
        'STRONG BUY': cfg.strong_buy_tgt,
        'REVERSAL':   cfg.reversal_tgt,
    }

    for ticker, df in data.items():
        n = len(df)
        for i in range(n - 6):
            row = df.iloc[i]
            sig = detect_signal(row, cfg)
            if sig is None:
                continue

            close = float(row['Close'])
            atr   = float(row['ATR'])

            # Entry: next day open; skip if gap-up > 1.5% above close
            next_row    = df.iloc[i + 1]
            entry_date  = df.index[i + 1]
            entry_price = float(next_row['Open'])
            if entry_price > close * 1.015:
                continue
            if entry_price <= 0:
                continue

            # Stop loss
            stop_raw   = entry_price - cfg.stop_atr_mult * atr
            hard_stop  = entry_price * (1 - cfg.hard_stop_pct)
            stop_price = max(stop_raw, hard_stop)

            # Targets relative to entry
            lo_mult, hi_mult = tgt_map[sig]
            target_lo = entry_price + lo_mult * atr
            target_hi = entry_price + hi_mult * atr
            # Apply floor guarantee
            target_lo = max(target_lo, entry_price * (1 + cfg.target_floor * 0.67))
            target_hi = max(target_hi, entry_price * (1 + cfg.target_floor))

            # Simulate forward
            max_hold = hold_map[sig]
            exit_price  = None
            exit_reason = None
            hold_actual = 0

            # Check entry day itself (intraday range after open)
            for j in range(max_hold + 1):
                fwd_idx = i + 1 + j
                if fwd_idx >= n:
                    break
                fwd     = df.iloc[fwd_idx]
                fwd_hi  = float(fwd['High'])
                fwd_lo  = float(fwd['Low'])
                hold_actual = j

                # Stop fires before target (conservative)
                if fwd_lo <= stop_price:
                    exit_price  = stop_price
                    exit_reason = 'stop'
                    break

                if fwd_hi >= target_lo:
                    # Fill at target_lo exactly -- this is what a real limit
                    # sell order does: it fills at its limit price the
                    # instant that price is touched, not at some fraction
                    # of the bar's eventual high. The previous formula
                    # (`min(max(fwd_hi * 0.995, target_lo), target_hi)`)
                    # used the bar's OWN high to set the exit price, which
                    # is lookahead -- that high isn't known until the bar
                    # closes, after the fill would have already happened.
                    # This was the single largest source of optimism in the
                    # backtest (inflating avg_win/expect/rr/pf together);
                    # removing it is a reduction in complexity, not an
                    # addition, and the resulting numbers are expected to be
                    # lower than before -- that's the bias coming out, not a
                    # new bug.
                    exit_price  = target_lo
                    exit_reason = 'target'
                    break

            if exit_reason is None:
                # Timeout: exit at close of last hold day
                last_idx = min(i + 1 + max_hold, n - 1)
                exit_price  = float(df.iloc[last_idx]['Close'])
                exit_reason = 'timeout'
                hold_actual = max_hold

            pnl = (exit_price / entry_price - 1) * 100 - COMMISSION * 100
            trades.append(Trade(
                ticker=ticker, signal=sig, entry_date=entry_date,
                entry_price=entry_price, stop_price=stop_price,
                target_lo=target_lo, target_hi=target_hi,
                exit_price=exit_price, exit_reason=exit_reason,
                hold_days=hold_actual, pnl_pct=pnl,
            ))

    return trades


# ── Analytics ───────────────────────────────────────────────────

def analyze(trades: list[Trade]) -> dict:
    if not trades:
        return {}
    df = pd.DataFrame([t.__dict__ for t in trades])
    df['win'] = df['pnl_pct'] > 0

    wins   = df[df['win']]['pnl_pct']
    losses = df[~df['win']]['pnl_pct']

    # Expectancy: probability-weighted average PnL
    wr       = df['win'].mean()
    avg_win  = wins.mean()  if len(wins)  > 0 else 0.0
    avg_loss = losses.mean() if len(losses) > 0 else 0.0
    expect   = df['pnl_pct'].mean()

    # Risk-reward ratio (positive number: avg_win / abs(avg_loss))
    rr = abs(avg_win / avg_loss) if avg_loss < 0 else float('inf')

    # Annualised Sharpe. Previously used a fixed `sqrt(252/2)` with a
    # comment claiming "assume avg ~1.5 trades/week" -- but 252/2 = 126
    # trades/year implies ~2.4/week, not 1.5; the comment and the formula
    # disagreed with each other. Deriving the annualization factor from the
    # actual observed trade frequency in this run removes the need to
    # guess, and keeps the number honest about what was actually simulated.
    # Caveat this doesn't fix: trades across the 30 tickers overlap in time,
    # so they aren't independent draws the way a clean annualization
    # assumes -- treat this Sharpe as indicative, not a rigorous one.
    sharpe = 0.0
    if df['pnl_pct'].std() > 0 and 'entry_date' in df.columns and len(df) > 1:
        span_days = (df['entry_date'].max() - df['entry_date'].min()).days
        trades_per_year = len(df) / max(span_days, 1) * 365.25
        sharpe = expect / df['pnl_pct'].std() * np.sqrt(trades_per_year)

    # Max drawdown via a CHRONOLOGICAL equity curve. Previously `df` (and
    # therefore `equity`) was in insertion order from simulate(), which
    # loops ticker-outer / time-inner -- i.e. all of the first ticker's
    # trades, then all of the second ticker's, etc. That is not an order
    # any trader could have experienced, and the resulting "drawdown" was
    # meaningless. Sorting by entry_date first makes it an actual
    # chronological equity curve (still ignoring that trades can overlap
    # across tickers -- see the Sharpe caveat above).
    chrono      = df.sort_values('entry_date') if 'entry_date' in df.columns else df
    equity      = (1 + chrono['pnl_pct'] / 100).cumprod()
    rolling_max = equity.cummax()
    max_dd      = ((equity - rolling_max) / rolling_max).min() * 100

    # Profit factor
    gross_win  = wins.sum()  if len(wins)  > 0 else 0
    gross_loss = losses.sum() if len(losses) > 0 else 0
    pf = abs(gross_win / gross_loss) if gross_loss < 0 else float('inf')

    out = {
        'n':          len(df),
        'win_rate':   wr * 100,
        'avg_win':    avg_win,
        'avg_loss':   avg_loss,
        'expect':     expect,
        'rr':         rr,
        'sharpe':     sharpe,
        'max_dd':     max_dd,
        'pf':         pf,
        'pct_target': (df['exit_reason'] == 'target').mean() * 100,
        'pct_stop':   (df['exit_reason'] == 'stop').mean()   * 100,
        'pct_timeout':(df['exit_reason'] == 'timeout').mean()* 100,
    }
    # Per-signal breakdown
    for sig in ('SCALP', 'BUY', 'STRONG BUY', 'REVERSAL'):
        sg = df[df['signal'] == sig]
        if len(sg) == 0:
            continue
        out[f'{sig}_n']  = len(sg)
        out[f'{sig}_wr'] = sg['win'].mean() * 100
        out[f'{sig}_avg']= sg['pnl_pct'].mean()
    return out


def print_summary(label: str, r: dict):
    sep = '─' * 64
    print(f'\n{sep}')
    print(f'  {label}')
    print(sep)
    if not r:
        print('  No trades.')
        return
    print(f"  Trades: {r['n']:>5}   Win rate: {r['win_rate']:>5.1f}%   "
          f"Expect: {r['expect']:>+6.2f}%/trade")
    print(f"  Avg win: {r['avg_win']:>+6.2f}%   Avg loss: {r['avg_loss']:>+6.2f}%   "
          f"R:R {r['rr']:>4.2f}x")
    print(f"  Sharpe: {r['sharpe']:>5.2f}   Max DD: {r['max_dd']:>6.2f}%   "
          f"Profit factor: {r['pf']:>5.2f}")
    print(f"  Exits → target {r['pct_target']:>5.1f}%  "
          f"stop {r['pct_stop']:>5.1f}%  timeout {r['pct_timeout']:>5.1f}%")
    for sig in ('SCALP', 'BUY', 'STRONG BUY', 'REVERSAL'):
        k = f'{sig}_n'
        if k in r:
            print(f"  {sig:<12}  n={r[f'{sig}_n']:>3}  "
                  f"WR={r[f'{sig}_wr']:>5.1f}%  avg={r[f'{sig}_avg']:>+5.2f}%")


# ── Data loader ─────────────────────────────────────────────────

def load_data(tickers: list[str]) -> dict[str, pd.DataFrame]:
    print(f'Downloading {len(tickers)} tickers ({DATA_PERIOD}) ...')
    raw = yf.download(
        tickers, period=DATA_PERIOD, interval='1d',
        group_by='ticker', auto_adjust=True, progress=False,
    )
    data: dict[str, pd.DataFrame] = {}
    for sym in tickers:
        try:
            if len(tickers) == 1:
                df = raw.copy()
            else:
                df = raw[sym].copy()
            df.dropna(how='all', inplace=True)
            if len(df) < 60:
                continue
            df = compute_indicators(df).dropna()
            data[sym] = df
        except Exception:
            pass
    print(f'Loaded {len(data)} tickers with sufficient history.')

    # ARA/ARB regime guard: warn (not abort -- this is diagnostic, the
    # sweep should still run) if any loaded history reaches back before the
    # current symmetric price-limit regime took effect. See
    # ARA_ARB_REGIME_CHANGE_DATE's definition above for why this matters.
    earliest = min((df.index.min() for df in data.values() if len(df)), default=None)
    if earliest is not None:
        earliest_ts = earliest.tz_localize(None) if earliest.tzinfo else earliest
        if earliest_ts < ARA_ARB_REGIME_CHANGE_DATE:
            print(
                f'WARNING: data reaches back to {earliest_ts.date()}, before the '
                f'{ARA_ARB_REGIME_CHANGE_DATE.date()} ARA/ARB regime change. ATR and '
                f'Bollinger-width distributions in this window mix at least two '
                f'different price-limit regimes -- treat results with that in mind.'
            )
    return data


# ── 10 iteration configs ────────────────────────────────────────

def build_iterations() -> list[Config]:
    # Baseline
    c0 = Config(label='1. Baseline (current defaults)')
    c0.scalp_rsi = (45, 55)
    c0.scalp_ema_prx = 0.010
    c0.scalp_hold = 2
    c0.buy_hold = 3
    c0.strong_buy_hold = 5
    c0.reversal_hold = 5

    # 2. Tighter RVOL filter — require stronger volume confirmation
    c1 = Config(label='2. Tighter RVOL (≥2.0)')
    c1.min_rvol     = 2.0
    c1.scalp_vol    = 2.0
    c1.buy_vol      = 2.0
    c1.reversal_vol = 2.5

    # 3. Higher ATR floor — skip low-volatility stocks
    c2 = Config(label='3. Higher ATR floor (≥1.2%)')
    c2.min_atr_pct  = 0.012

    # 4. Tighter SCALP RSI band — narrower, higher-probability window
    c3 = Config(label='4. Tight SCALP RSI (45–55)')
    c3.scalp_rsi    = (45, 55)
    c3.scalp_ema_prx= 0.010   # within 1% of EMA21 (tighter)

    # 5. Tight stop — 0.6x ATR (quick cut, higher trade frequency)
    c4 = Config(label='5. Tight stop (0.6x ATR)')
    c4.stop_atr_mult = 0.6
    c4.hard_stop_pct = 0.020   # 2% hard stop

    # 6. Wide stop — 1.5x ATR (give trade room to breathe)
    c5 = Config(label='6. Wide stop (1.5x ATR)')
    c5.stop_atr_mult = 1.5
    c5.hard_stop_pct = 0.040

    # 7. Shorter holds — exit faster, more turns
    c6 = Config(label='7. Shorter holds (scalp=1 buy=1 sbuy=2 rev=2)')
    c6.scalp_hold       = 1
    c6.buy_hold         = 1
    c6.strong_buy_hold  = 2
    c6.reversal_hold    = 2

    # 8. Longer holds — let winners run
    c7 = Config(label='8. Longer holds (scalp=2 buy=3 sbuy=5 rev=5)')
    c7.scalp_hold       = 2
    c7.buy_hold         = 3
    c7.strong_buy_hold  = 5
    c7.reversal_hold    = 5

    # 9. Only REVERSAL + SCALP (high-contrast signals, skip BUY noise)
    #    Achieve by making BUY/STRONG BUY impossible to trigger
    c8 = Config(label='9. REVERSAL+SCALP only (exclude BUY signals)')
    c8.buy_pullback      = (99, 100)   # impossible — never triggers
    c8.strong_buy_pb     = (99, 100)   # impossible

    # 10. Best-of combination (assembled after reviewing iterations 1-9)
    #     Hypothesis: tighter RVOL + higher ATR + tighter stop + moderate holds
    c9 = Config(label='10. Best combo (RVOL≥2, ATR≥1%, stop=0.8x, tight SCALP)')
    c9.min_rvol         = 2.0
    c9.scalp_vol        = 2.0
    c9.buy_vol          = 2.0
    c9.reversal_vol     = 2.5
    c9.min_atr_pct      = 0.010
    c9.stop_atr_mult    = 0.8
    c9.hard_stop_pct    = 0.025
    c9.scalp_rsi        = (43, 57)
    c9.scalp_ema_prx    = 0.012
    c9.scalp_hold       = 1
    c9.buy_hold         = 2
    c9.strong_buy_hold  = 3
    c9.reversal_hold    = 3

    # 11. Max Win Rate (tiny targets, wide stop, long holds)
    c10 = Config(label='11. Max Win Rate (quick exit, wide stop)')
    c10.scalp_tgt = (0.5, 1.0)
    c10.buy_tgt = (0.5, 1.0)
    c10.strong_buy_tgt = (0.5, 1.0)
    c10.reversal_tgt = (0.5, 1.0)
    c10.target_floor = 0.015 # 1.5% minimum profit
    c10.stop_atr_mult = 3.0
    c10.hard_stop_pct = 0.08
    c10.scalp_hold = 5
    c10.buy_hold = 5
    c10.strong_buy_hold = 5
    c10.reversal_hold = 5
    
    # 12. Extremely Max Win Rate (80% target)
    c11 = Config(label='12. Push for >80% Win Rate')
    c11.scalp_tgt = (0.3, 0.7)
    c11.buy_tgt = (0.3, 0.7)
    c11.strong_buy_tgt = (0.3, 0.7)
    c11.reversal_tgt = (0.3, 0.7)
    c11.target_floor = 0.015 # 1.5% minimum profit to cover 0.44% fees safely + buffer
    c11.stop_atr_mult = 5.0
    c11.hard_stop_pct = 0.15
    c11.scalp_hold = 10
    c11.buy_hold = 10
    c11.strong_buy_hold = 10
    c11.reversal_hold = 10
    
    # 13. Target 2-3% Net Profit Per Trade
    c12 = Config(label='13. Target 2-3% Net Profit (Floor 3.5%)')
    c12.scalp_tgt = (1.2, 2.0)
    c12.buy_tgt = (1.5, 2.5)
    c12.strong_buy_tgt = (1.8, 3.0)
    c12.reversal_tgt = (1.8, 3.0)
    # To net 2-3% after 0.44% fee, we need a floor of around 3.0% - 3.5%
    c12.target_floor = 0.035 
    c12.stop_atr_mult = 2.0
    c12.hard_stop_pct = 0.06
    c12.scalp_hold = 3
    c12.buy_hold = 5
    c12.strong_buy_hold = 5
    c12.reversal_hold = 5
    
    return [c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12]


# ── Main ────────────────────────────────────────────────────────

def main():
    data = load_data(IDX_TICKERS)
    if not data:
        print('ERROR: no data loaded')
        sys.exit(1)

    configs = build_iterations()
    all_results: list[tuple[str, dict]] = []

    for cfg in configs:
        print(f'\nRunning: {cfg.label} ...', end='', flush=True)
        t0     = time.time()
        trades = simulate(cfg, data)
        r      = analyze(trades)
        elapsed= time.time() - t0
        print(f' {len(trades)} trades ({elapsed:.1f}s)')
        print_summary(cfg.label, r)
        all_results.append((cfg.label, r))

    # ── Comparison table
    print('\n\n' + '═' * 100)
    print('  COMPARISON TABLE')
    print('═' * 100)
    hdr = (f"{'Iteration':<44} {'N':>5} {'WR%':>6} {'Expect':>7} "
           f"{'R:R':>5} {'Sharpe':>7} {'MaxDD':>7} {'PF':>5}")
    print(hdr)
    print('─' * 100)
    best_expect = max(
        (r.get('expect', -999) for _, r in all_results if r),
        default=-999
    )
    for label, r in all_results:
        if not r:
            print(f'  {label:<44}  (no trades)')
            continue
        marker = ' ★' if abs(r['expect'] - best_expect) < 0.001 else ''
        print(f"  {label:<44} {r['n']:>5} {r['win_rate']:>5.1f}% "
              f"{r['expect']:>+6.2f}% {r['rr']:>5.2f}x {r['sharpe']:>7.2f} "
              f"{r['max_dd']:>6.2f}% {r['pf']:>5.2f}{marker}")

    # ── Per-signal comparison
    print('\n' + '─' * 100)
    print('  PER-SIGNAL BREAKDOWN (Win Rate % / Avg PnL %)')
    print('─' * 100)
    sigs = ('SCALP', 'BUY', 'STRONG BUY', 'REVERSAL')
    sig_hdr = f"  {'Iteration':<44}"
    for s in sigs:
        sig_hdr += f"  {s:<18}"
    print(sig_hdr)
    print('─' * 100)
    for label, r in all_results:
        row = f'  {label:<44}'
        for s in sigs:
            if f'{s}_n' in r:
                row += f"  n={r[f'{s}_n']:<3} WR={r[f'{s}_wr']:>4.0f}% avg={r[f'{s}_avg']:>+5.2f}%"
            else:
                row += f"  {'—':<18}"
        print(row)

    print('\n★ = best expected value per trade\n')


if __name__ == '__main__':
    main()
