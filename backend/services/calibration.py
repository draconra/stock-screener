"""
Dynamic price-range calibration.

Multipliers are ATR-based, EXCEPT where the per-signal target floor below
takes over for low-ATR names -- see _TARGET_FLOOR. Auto-calibration runs at
startup against the top-20 most liquid IDX stocks (6-month history). The
backtest uses pattern-specific forward windows (SCALP=2d, BUY=3d, STRONG
BUY/REVERSAL=5d -- see _HOLD_DAYS below) so each signal's reachable high is
measured appropriately.

Sell targets respect a per-signal floor (see _TARGET_FLOOR): even low-ATR
stocks get a minimum gain zone, sized to what's actually achievable within
that signal's hold window rather than a single number for every signal.
Round-trip cost for an IDX scalp is ~0.44% (0.15% buy + 0.25% sell + 0.04%
levy), the figure the rest of this module and simulate.py use consistently.
"""

from __future__ import annotations
import copy
import logging
import yfinance as yf
import pandas as pd
import numpy as np
import os
import json
from dataclasses import dataclass, field
from services.indicators import compute_indicators, classify_candle

log = logging.getLogger(__name__)

# ── Pattern-specific forward window (trading days) ──────────────
# How many sessions to look ahead when measuring MFE in the backtest.
# Determines what "achievable target" means per signal type.
_HOLD_DAYS: dict[str, int] = {
    'STRONG BUY': 5,
    'BUY':        3,
    'SCALP':      2,
    'REVERSAL':   5,
    'SELL':       1,
    'WATCH':      1,
}

# ── Per-signal minimum sell target (floor above entry price) ────
# Graduated by hold window, not a single flat number for every signal type.
# Measured in this app's own backtest history (see simulate.py's iteration
# log): a uniform 3% floor on SCALP's 2-day hold caused 49% of SCALP trades
# to time out, because the floor was demanding a move the ATR-scaled target
# rarely reached in that short a window. A signal that holds longer
# (STRONG BUY/REVERSAL, 5 days) can carry a higher floor and still clear it
# often enough; SCALP's shorter window needs a lower one. This restores that
# graduation -- a prior edit had flattened every non-SELL signal to 3.5%,
# which silently reintroduced the exact problem this comment describes (see
# git history / plan doc for the measured drift).
_TARGET_FLOOR: dict[str, float] = {
    'SCALP':      0.015,
    'BUY':        0.025,
    'STRONG BUY': 0.030,
    'REVERSAL':   0.030,
    'SELL':       0.010,
    'WATCH':      0.025,
}

# ── Stop-loss ─────────────────────────────────────────────────
# Matches simulate.py's Config defaults (stop_atr_mult=1.0, hard_stop_pct=
# 0.03) rather than inventing new numbers -- those are the values the
# backtest in this app already exercises. README previously claimed "Stop
# losses are set dynamically based on a multiple of the stock's ATR", but
# simulate.py's stop model was never actually surfaced to the live product
# -- compute_ranges() only ever returned buy/sell zones. This closes that
# gap using the same, already-shipped formula.
STOP_ATR_MULT = 1.0
HARD_STOP_PCT = 0.03

# ── Default ATR-multiplier table (history-calibrated) ───────────
# target_lo = p50 MFE (median reachable gain / ATR)
# target_hi = p75 MFE (75th-percentile reachable gain / ATR)
# Typical active IDX ATR ≈ 1.5–3 % of price.
# At 2 % ATR: 1.5x → 3 %, 2.0x → 4 %, 2.5x → 5 %.
# The per-signal floor in _TARGET_FLOOR above is enforced in compute_ranges
# regardless of ATR size -- SCALP 1.5%, BUY 2.5%, STRONG BUY/REVERSAL 3%.
_DEFAULT_TABLE: dict[tuple[str, str], dict] = {
    # STRONG BUY — high conviction pullback, holds 5 sessions (_HOLD_DAYS)
    ('STRONG BUY', 'low'):  {'buy_depth': 0.80, 'target_lo': 1.80, 'target_hi': 3.00},
    ('STRONG BUY', 'med'):  {'buy_depth': 0.75, 'target_lo': 1.80, 'target_hi': 3.00},
    ('STRONG BUY', 'high'): {'buy_depth': 0.60, 'target_lo': 1.80, 'target_hi': 3.00},
    # BUY — standard momentum pullback, holds 3 sessions
    ('BUY', 'low'):         {'buy_depth': 1.00, 'target_lo': 1.50, 'target_hi': 2.50},
    ('BUY', 'med'):         {'buy_depth': 0.90, 'target_lo': 1.50, 'target_hi': 2.50},
    ('BUY', 'high'):        {'buy_depth': 0.70, 'target_lo': 1.50, 'target_hi': 2.50},
    # SCALP — 2-session continuation, tightest targets of the four buy signals
    ('SCALP', 'low'):       {'buy_depth': 0.40, 'target_lo': 1.20, 'target_hi': 2.00},
    ('SCALP', 'med'):       {'buy_depth': 0.40, 'target_lo': 1.20, 'target_hi': 2.00},
    ('SCALP', 'high'):      {'buy_depth': 0.35, 'target_lo': 1.20, 'target_hi': 2.00},
    # REVERSAL — oversold bounce: simulation confirms WIDER stop (1.5x ATR) raises WR
    # from 49% → 54% and avg from +0.96% → +1.11% (iteration 6 of the sweep)
    ('REVERSAL', 'low'):    {'buy_depth': 1.50, 'target_lo': 1.80, 'target_hi': 3.00},
    ('REVERSAL', 'med'):    {'buy_depth': 1.30, 'target_lo': 1.80, 'target_hi': 3.00},
    ('REVERSAL', 'high'):   {'buy_depth': 1.10, 'target_lo': 1.80, 'target_hi': 3.00},
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
    # Deep copy, not `dict(_DEFAULT_TABLE)`: a shallow copy shares the inner
    # per-cell dicts with _DEFAULT_TABLE, so any in-place `.update()` on a
    # calibrated instance (both the statistical pass historically, and the
    # AI pass at _ai_calibrate) permanently mutates the module-level
    # defaults for the rest of the process. Every later Calibrator() then
    # inherits an already-drifted baseline instead of the real defaults.
    table: dict[tuple[str, str], dict] = field(default_factory=lambda: copy.deepcopy(_DEFAULT_TABLE))
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
            return {'buy_low': 0, 'buy_high': 0, 'sell_low': 0, 'sell_high': 0, 'stop_loss': 0}

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

            # ── Per-signal target floor ───────────────────────────
            # Applied BEFORE the pivot-R1 resistance cap below, not after --
            # previously the floor ran last and could push sell_high back
            # above a resistance level the pivot check had just capped it
            # to, silently un-doing that check. Floor first means "the
            # target is at least this far above entry", then the pivot cap
            # (if any) still gets the final say on where resistance is.
            floor_pct  = _TARGET_FLOOR.get(signal, 0.025)
            floor_hi   = int(round(close * (1 + floor_pct)))
            floor_lo   = int(round(close * (1 + floor_pct * 0.67)))
            sell_high  = max(sell_high, floor_hi)
            sell_low   = max(sell_low,  floor_lo)
            if sell_low >= sell_high:
                sell_high = int(round(close * (1 + floor_pct * 1.3)))

            # Respect pivot R1 as a resistance ceiling when meaningful
            if 0 < pivot_r1 < sell_high and pivot_r1 > sell_low:
                sell_high = int(round(pivot_r1))

        # Stop-loss: the tighter of an ATR-multiple stop and a hard
        # percentage floor, placed below the recommended entry (buy_low),
        # not below the current close -- a stop belongs relative to where
        # you'd actually be filled. Not meaningful for SELL (an exit/avoid
        # signal, not a new long position) or WATCH.
        if signal in ('SELL', 'WATCH'):
            stop_loss = 0
        else:
            stop_raw  = buy_low - STOP_ATR_MULT * atr
            hard_stop = buy_low * (1 - HARD_STOP_PCT)
            stop_loss = int(round(max(stop_raw, hard_stop)))
            if stop_loss >= buy_low:
                stop_loss = int(round(buy_low * (1 - HARD_STOP_PCT)))

        return {
            'buy_low':  buy_low,
            'buy_high': buy_high,
            'sell_low':  sell_low,
            'sell_high': sell_high,
            'stop_loss': stop_loss,
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
    Re-derive multipliers from recent 6-month data of the top-N IDX stocks
    by Rupiah turnover value. Only updates a cell if the new value differs
    by >10 % from the default.
    """
    from tradingview_screener import Query, col

    log.info('Auto-calibrating price ranges ...')
    try:
        # Ranked by turnover value (Value.Traded, in IDR), not raw share
        # volume -- a raw-volume ranking systematically selects low-priced,
        # high-share-count names on IDX rather than the stocks with the
        # most actual money moving through them. Measured: ordering by
        # Value.Traded surfaces BBRI/BUMI/DSSA/BMRI/BBCA as the top 5,
        # matching what "most liquid" actually means for this app's purpose
        # (enough real turnover to fill a trade without moving the price).
        _, tv = (Query()
            .set_markets('indonesia')
            .select('name', 'volume', 'Value.Traded')
            .where(col('volume') > 100_000, col('close') > 50)
            .order_by('Value.Traded', ascending=False)
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

    # Try AI Calibration as a second pass. Pass the per-cell sample counts
    # so the AI pass can apply the same n>=5 gate the statistical pass above
    # already enforces -- previously it had no sample-size guard at all.
    counts = bt.groupby(['signal', 'tier']).size().to_dict()
    _ai_calibrate(cal, bt, counts)


# Bounds mirroring the statistical pass above (lines ~270-276) -- previously
# the AI pass only clamped a LOWER bound (max(0.0/0.5/1.0, ...)), so a
# malformed or hallucinated response could set e.g. target_hi to 50 with
# nothing catching it. buy_depth range matches _DEFAULT_TABLE's observed
# 0.35-1.50 span with headroom; target_lo/target_hi match the statistical
# pass's clamps exactly so both passes can't disagree about what's plausible.
_AI_BUY_DEPTH_RANGE = (0.10, 3.00)
_AI_TARGET_LO_RANGE = (0.80, 4.00)
_AI_TARGET_HI_MAX = 6.00
_AI_MIN_SAMPLES = 5


def _ai_calibrate(cal: Calibrator, bt: pd.DataFrame, counts: dict[tuple[str, str], int]) -> None:
    """Passes the recent backtest data to GLM AI to suggest dynamic multiplier
    tweaks. Guardrails below are deliberately as strict as the statistical
    pass's -- an LLM suggestion is not inherently more trustworthy than a
    quantile computed directly from the same data, so it gets the same
    bounds, the same sample-size gate, and its changes are logged as a diff
    instead of just a count, so a bad calibration run is auditable after
    the fact rather than a silent table replacement."""
    api_key = os.environ.get("GLM_API_KEY")
    if not api_key:
        log.warning("AI Calibration skipped: GLM_API_KEY not set in environment.")
        return

    try:
        from zhipuai import ZhipuAI
        client = ZhipuAI(api_key=api_key)

        # Summarize the backtest data for the AI to reduce token usage
        summary = bt.groupby(['signal', 'tier']).agg({
            'mae': ['mean', 'median', lambda x: x.quantile(0.75)],
            'mfe': ['mean', 'median', lambda x: x.quantile(0.75)],
        }).round(3).reset_index()
        summary.columns = ['signal', 'tier', 'mae_mean', 'mae_p50', 'mae_p75', 'mfe_mean', 'mfe_p50', 'mfe_p75']

        current_table_str = json.dumps({f"{k[0]}|{k[1]}": v for k, v in cal.table.items()})
        bt_data_str = summary.to_csv(index=False)

        prompt = f"""
You are an expert quantitative trading AI. We have an algorithm that trades the Indonesian Stock Exchange (IDX).
Our current configuration for ATR multipliers per signal and volume tier is:
{current_table_str}

We ran a 6-month historical backtest on the top 20 most liquid IDX stocks. Here is the summary of Maximum Adverse Excursion (MAE) and Maximum Favorable Excursion (MFE) scaled by ATR:
{bt_data_str}

Please analyze this data and suggest updated 'buy_depth', 'target_lo', and 'target_hi' values.
- buy_depth represents the pullback depth to place a limit buy order.
- target_lo and target_hi represent the sell zone multipliers.
- We target a 2-3% net profit, and fees are 0.44% round-trip.
- Respond ONLY with a valid JSON object matching the input structure (keys formatted as "SIGNAL|tier"). Do not include markdown formatting, backticks, or any conversational text.
"""
        log.info("Sending backtest summary to GLM AI for dynamic calibration...")
        response = client.chat.completions.create(
            model="glm-4-plus", # Use the generic GLM-4-plus model name as a final fallback
            messages=[
                {"role": "system", "content": "You are a quantitative trading system generating JSON configurations."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1024
        )

        result_content = response.choices[0].message.content.strip()

        # Clean up any potential markdown formatting the AI might still include
        if result_content.startswith("```json"):
            result_content = result_content[7:]
        if result_content.endswith("```"):
            result_content = result_content[:-3]

        ai_suggestions = json.loads(result_content.strip())

        updated_count = 0
        skipped_low_n = 0
        skipped_invalid = 0
        diffs = []
        for k_str, v in ai_suggestions.items():
            parts = k_str.split('|')
            if len(parts) != 2:
                continue
            sig, tier = parts[0], parts[1]
            key = (sig, tier)
            if key not in cal.table:
                continue

            # Sample-size gate: don't let the AI touch a cell the statistical
            # pass itself would have skipped for insufficient data.
            if counts.get(key, 0) < _AI_MIN_SAMPLES:
                skipped_low_n += 1
                continue

            try:
                new_depth = float(v.get('buy_depth', cal.table[key]['buy_depth']))
                new_lo    = float(v.get('target_lo', cal.table[key]['target_lo']))
                new_hi    = float(v.get('target_hi', cal.table[key]['target_hi']))
            except (TypeError, ValueError):
                skipped_invalid += 1
                continue

            new_depth = max(_AI_BUY_DEPTH_RANGE[0], min(_AI_BUY_DEPTH_RANGE[1], new_depth))
            new_lo    = max(_AI_TARGET_LO_RANGE[0], min(_AI_TARGET_LO_RANGE[1], new_lo))
            new_hi    = max(new_lo + 0.30, min(_AI_TARGET_HI_MAX, new_hi))

            # Ordering check: target_hi < target_lo would previously be
            # accepted as-is and only quietly papered over later by
            # compute_ranges' own floor fallback -- reject it here instead,
            # at the source, so a bad AI response never enters the table.
            if new_hi <= new_lo:
                skipped_invalid += 1
                continue

            old = dict(cal.table[key])
            cal.table[key].update({'buy_depth': new_depth, 'target_lo': new_lo, 'target_hi': new_hi})
            updated_count += 1
            if old != cal.table[key]:
                diffs.append(f"{k_str}: {old} -> {cal.table[key]}")

        log.info(
            "AI Calibration complete. Applied %d adjustments, skipped %d (low sample size), "
            "skipped %d (invalid/out-of-order response).",
            updated_count, skipped_low_n, skipped_invalid,
        )
        if diffs:
            log.info("AI Calibration diff:\n%s", "\n".join(diffs))
    except Exception as e:
        log.error(f"AI Calibration failed: {e}")

# Module-level singleton
calibrator = Calibrator()
