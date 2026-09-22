"""Single source of truth for buy/sell signal classification.

Before this module existed, the same logic was hand-duplicated in three
places with three different orderings and three different condition sets:

  - indicators.classify_candle()   (chart markers; feeds calibration backtest)
  - screener_service._signal()     (the live screener users actually trade)
  - simulate.detect_signal()       (the parameter-sweep backtest)

Measured consequence: SCALP was unreachable in the live screener (its
condition set is a strict subset of the generic BUY conditions checked
before it), the backtest measured a signal definition different from what
the screener served, and a bare `1978/1992`-vintage indicator set was
producing inconsistent labels for the identical input depending on which
file happened to compute it. See the plan doc for the full measured
findings and citations.

`classify_signal()` is the one function all three now call. Callers that
can't supply a field (e.g. the live screener has no `consec_down` — that
needs per-ticker OHLCV history, not available from a TradingView scanner
snapshot) pass `None` for it, and the conditions that need it are skipped
for that call, not silently treated as failing. This mirrors the explicit
missing-value policy already used in `fundamentals/criteria.py::evaluate()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TypedDict

from .indicators import (
    STRONG_BUY_RSI, STRONG_BUY_VOL,
    BUY_RSI, BUY_VOL,
    TREND_RSI, TREND_VOL, TREND_BB_MAX,
    SCALP_RSI, SCALP_VOL, SCALP_EMA_PROXIMITY,
    REVERSAL_RSI, REVERSAL_VOL, REVERSAL_BB, REVERSAL_STOCH,
    SELL_BB, SELL_RSI, SELL_VOL,
)


class SignalInputs(TypedDict, total=False):
    rsi: float
    vol_ratio: float
    bb_pct: float
    close: float
    ema21: float
    ema_up: bool
    ema_stack: Optional[bool]    # EMA9 > EMA21 > EMA50; None when EMA50 unavailable
    consec_down: Optional[int]   # None when unavailable (e.g. screener snapshot)
    stoch_k: Optional[float]


@dataclass(frozen=True)
class SignalThresholds:
    """Defaults are the canonical values from indicators.py. simulate.py's
    parameter sweep builds one of these per Config so it can vary thresholds
    without maintaining a second copy of the classification logic."""
    strong_buy_rsi: tuple = STRONG_BUY_RSI
    strong_buy_vol: float = STRONG_BUY_VOL
    strong_buy_pullback: tuple = (2, 3)

    buy_rsi: tuple = BUY_RSI
    buy_vol: float = BUY_VOL
    buy_pullback: tuple = (1, 3)

    trend_rsi: tuple = TREND_RSI
    trend_vol: float = TREND_VOL
    trend_bb_max: float = TREND_BB_MAX

    scalp_rsi: tuple = SCALP_RSI
    scalp_vol: float = SCALP_VOL
    scalp_ema_proximity: float = SCALP_EMA_PROXIMITY

    reversal_rsi: float = REVERSAL_RSI
    reversal_vol: float = REVERSAL_VOL
    reversal_bb: float = REVERSAL_BB
    reversal_stoch: float = REVERSAL_STOCH

    sell_bb: float = SELL_BB
    sell_rsi: float = SELL_RSI
    sell_vol: float = SELL_VOL

    require_ema_up: bool = True


DEFAULT_THRESHOLDS = SignalThresholds()


def classify_signal(ind: SignalInputs, thresholds: SignalThresholds = DEFAULT_THRESHOLDS) -> str:
    """Returns one of: 'STRONG BUY', 'BUY', 'SCALP', 'REVERSAL', 'SELL', 'WATCH'."""
    t = thresholds
    rsi = ind['rsi']
    vol = ind['vol_ratio']
    bb = ind['bb_pct']
    ema_up = ind['ema_up']
    ema_stack = ind.get('ema_stack')
    consec_down = ind.get('consec_down')
    stoch_k = ind.get('stoch_k')
    close = ind.get('close', 0.0) or 0.0
    ema21 = ind.get('ema21', 0.0) or 0.0
    near_ema21 = ema21 > 0 and abs(close - ema21) / ema21 < t.scalp_ema_proximity

    # SELL: independent of trend direction (an overbought exit can fire in
    # either state), evaluated first. Thresholds are disjoint from every
    # buy-type RSI band below (max buy-side RSI ceiling is TREND_RSI's 65,
    # inclusive; SELL requires RSI > 65, exclusive) so checking it first
    # changes nothing for the buy branches.
    if bb > t.sell_bb and rsi > t.sell_rsi and vol > t.sell_vol:
        return 'SELL'

    # REVERSAL: downtrend oversold bounce. Gate mirrors the historical
    # `not require_ema_up or not ema_up` semantics from simulate.py's sweep
    # config (require_ema_up=False is never actually used by any of the
    # shipped sweep configs, but the flag is preserved for future sweeps).
    if (not ema_up) or (not t.require_ema_up):
        stoch_ok = stoch_k is not None and stoch_k < t.reversal_stoch
        if (rsi < t.reversal_rsi or stoch_ok) and bb < t.reversal_bb and vol > t.reversal_vol:
            return 'REVERSAL'

    # Continuation signals need an uptrend, unless the gate is explicitly disabled.
    if t.require_ema_up and not ema_up:
        return 'WATCH'

    # STRONG BUY: highest-conviction pullback. `consec_down` unavailable
    # (screener snapshot) -> this leg is skipped, not failed.
    pullback_ok = consec_down is None or (t.strong_buy_pullback[0] <= consec_down <= t.strong_buy_pullback[1])
    if pullback_ok and t.strong_buy_rsi[0] < rsi < t.strong_buy_rsi[1] and vol > t.strong_buy_vol:
        return 'STRONG BUY'

    # SCALP: the narrowest condition — checked BEFORE the broader BUY
    # branches below. This ordering is the actual fix for the historical
    # dead-code bug (see SCALP_RSI's docstring in indicators.py).
    if near_ema21 and t.scalp_rsi[0] <= rsi <= t.scalp_rsi[1] and vol > t.scalp_vol:
        return 'SCALP'

    # BUY (pullback): standard momentum pullback.
    pullback_ok = consec_down is None or (t.buy_pullback[0] <= consec_down <= t.buy_pullback[1])
    if pullback_ok and t.buy_rsi[0] < rsi < t.buy_rsi[1] and vol > t.buy_vol:
        return 'BUY'

    # BUY (trend continuation): full EMA9>21>50 stack when available.
    stack_ok = ema_stack is None or ema_stack
    if stack_ok and t.trend_rsi[0] <= rsi <= t.trend_rsi[1] and vol > t.trend_vol and bb < t.trend_bb_max:
        return 'BUY'

    return 'WATCH'
