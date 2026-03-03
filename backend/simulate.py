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
from services.indicators import compute_indicators

COMMISSION   = 0.0044   # 0.44% round-trip (Buy: 0.15% + Sell: 0.25% + Levy: 0.04%)
DATA_PERIOD  = '12mo'   # 12-month history

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
    scalp_rsi:     tuple = (40, 60)
    scalp_ema_prx: float = 0.015   # within 1.5% of EMA21
    scalp_vol:     float = 1.5

    reversal_rsi:  float = 35.0    # RSI must be below this
    reversal_bb:   float = 0.20    # BB_pct must be below this
    reversal_vol:  float = 2.0

    buy_rsi:       tuple = (30, 55)
    buy_vol:       float = 1.5
    buy_pullback:  tuple = (1, 3)  # consecutive down days

    strong_buy_rsi: tuple = (30, 50)
    strong_buy_vol: float = 2.0
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

def detect_signal(row: pd.Series, cfg: Config) -> Optional[str]:
    rsi       = float(row['RSI'])
    vol       = float(row['Vol_ratio'])
    bb        = float(row['BB_pct'])
    close     = float(row['Close'])
    ema9      = float(row['EMA9'])
    ema21     = float(row['EMA21'])
    atr       = float(row['ATR'])
    pullback  = int(row['consec_down'])
    stoch_k   = float(row.get('Stoch_K', 50))

    if close <= 0 or atr <= 0:
        return None
    atr_pct = atr / close
    ema_up  = ema9 > ema21

    # Pre-filters
    if vol < cfg.min_rvol or atr_pct < cfg.min_atr_pct:
        return None

    # REVERSAL: downtrend oversold bounce with volume spike
    if ((rsi < cfg.reversal_rsi or stoch_k < 20)
            and bb < cfg.reversal_bb
            and vol >= cfg.reversal_vol
            and (not cfg.require_ema_up or not ema_up)):
        return 'REVERSAL'

    # Uptrend required for remaining signals
    if cfg.require_ema_up and not ema_up:
        return None

    # SCALP: price hugging EMA21, moderate RSI, volume confirmation
    ema_proximity = abs(close - ema21) / ema21 if ema21 > 0 else 1.0
    if (cfg.scalp_rsi[0] <= rsi <= cfg.scalp_rsi[1]
            and ema_proximity <= cfg.scalp_ema_prx
            and vol >= cfg.scalp_vol):
        return 'SCALP'

    # STRONG BUY: pullback in strong uptrend with volume surge
    if (cfg.strong_buy_pb[0] <= pullback <= cfg.strong_buy_pb[1]
            and cfg.strong_buy_rsi[0] < rsi < cfg.strong_buy_rsi[1]
            and vol >= cfg.strong_buy_vol
            and bb < 0.50):
        return 'STRONG BUY'

    # BUY: standard pullback entry
    if (cfg.buy_pullback[0] <= pullback <= cfg.buy_pullback[1]
            and cfg.buy_rsi[0] < rsi < cfg.buy_rsi[1]
            and vol >= cfg.buy_vol):
        return 'BUY'

    return None


# ── Trade record ────────────────────────────────────────────────

@dataclass
class Trade:
    ticker:      str
    signal:      str
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
                    # Exit at target_lo (limit order); cap at target_hi
                    exit_price  = min(max(fwd_hi * 0.995, target_lo), target_hi)
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
                ticker=ticker, signal=sig,
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

    # Annualised Sharpe (assume avg ~1.5 trades/week)
    sharpe = 0.0
    if df['pnl_pct'].std() > 0:
        sharpe = expect / df['pnl_pct'].std() * np.sqrt(252 / 2)

    # Max drawdown via equity curve
    equity      = (1 + df['pnl_pct'] / 100).cumprod()
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
