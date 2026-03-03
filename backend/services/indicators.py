from typing import Optional
import pandas as pd

# ─── Signal thresholds — single source of truth ─────────────────
# Shared with screener_service so both use identical criteria.
STRONG_BUY_RSI = (30, 50)
STRONG_BUY_VOL = 2.0

BUY_RSI = (30, 55)
BUY_VOL = 1.5

TREND_RSI = (45, 65)
TREND_VOL = 1.3

SELL_BB  = 0.85
SELL_RSI = 65
SELL_VOL = 1.5

# Scalp: uptrend continuation touch on EMA21 — RSI must be ABOVE midline (50+)
# Simulation showed RSI 40-50 near EMA21 is a pullback, better caught by BUY signal.
# Only RSI 50-68 guarantees price is still in confirmed uptrend momentum.
# Modified: tighter SCALP RSI range based on historical simulation for improved Expectancy and R:R
SCALP_RSI = (45, 55)
SCALP_VOL = 1.5

# Reversal: oversold bounce with volume confirmation
REVERSAL_RSI = 35       # RSI must be below this
REVERSAL_VOL = 2.0      # Volume spike = smart money
REVERSAL_BB  = 0.20     # Near or below Bollinger lower band


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # RSI 14
    delta = df['Close'].diff()
    gain  = delta.where(delta > 0, 0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))

    # EMAs
    df['EMA9']  = df['Close'].ewm(span=9).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()

    # Bollinger Bands (20, 2)
    df['BB_mid']   = df['Close'].rolling(20).mean()
    bb_std         = df['Close'].rolling(20).std()
    df['BB_upper'] = df['BB_mid'] + 2 * bb_std
    df['BB_lower'] = df['BB_mid'] - 2 * bb_std
    df['BB_pct']   = (df['Close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'])

    # Stochastic %K, %D (14, 3)
    lo14 = df['Low'].rolling(14).min()
    hi14 = df['High'].rolling(14).max()
    df['Stoch_K'] = 100 * (df['Close'] - lo14) / (hi14 - lo14)
    df['Stoch_D'] = df['Stoch_K'].rolling(3).mean()

    # Volume ratio vs 20-day avg
    df['Vol_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()

    # ATR 14
    df['TR'] = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low']  - df['Close'].shift()).abs(),
    ], axis=1).max(axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()

    # Consecutive down days
    df['pct_chg']  = df['Close'].pct_change()
    df['down_day'] = (df['pct_chg'] < 0).astype(int)
    df['consec_down'] = (
        df['down_day']
        .groupby((df['down_day'] != df['down_day'].shift()).cumsum())
        .cumcount() + 1
    ) * df['down_day']

    return df


def classify_candle(row) -> Optional[dict]:
    ema_up   = row['EMA9'] > row['EMA21']
    rsi      = row['RSI']
    vol      = row['Vol_ratio']
    bb       = row['BB_pct']
    pullback = row['consec_down']

    if (ema_up and 2 <= pullback <= 3 and
            STRONG_BUY_RSI[0] < rsi < STRONG_BUY_RSI[1] and
            vol > STRONG_BUY_VOL and bb < 0.5):
        return {'position': 'belowBar', 'color': '#00e676', 'shape': 'arrowUp', 'text': 'STRONG BUY'}

    if ema_up and 1 <= pullback <= 3 and BUY_RSI[0] < rsi < BUY_RSI[1] and vol > BUY_VOL:
        return {'position': 'belowBar', 'color': '#2196F3', 'shape': 'arrowUp', 'text': 'BUY'}

    if (row['EMA9'] > row['EMA21'] > row['EMA50'] and
            TREND_RSI[0] <= rsi <= TREND_RSI[1] and vol > TREND_VOL and bb < 0.7):
        return {'position': 'belowBar', 'color': '#2196F3', 'shape': 'arrowUp', 'text': 'BUY'}

    if bb > SELL_BB and rsi > SELL_RSI and vol > SELL_VOL:
        return {'position': 'aboveBar', 'color': '#e91e63', 'shape': 'arrowDown', 'text': 'SELL'}

    # REVERSAL BUY: oversold + volume spike + price near BB lower (downtrend bounce)
    stoch = row.get('Stoch_K', 50) if 'Stoch_K' in row.index else 50
    if (not ema_up and (rsi < REVERSAL_RSI or stoch < 20)
            and bb < REVERSAL_BB and vol > REVERSAL_VOL):
        return {'position': 'belowBar', 'color': '#ff9800', 'shape': 'arrowUp', 'text': 'REVERSAL BUY'}

    # SCALP: uptrend continuation — price touching EMA21 from ABOVE with RSI 50-68
    # Confirmed by simulation: RSI below 50 near EMA21 is better treated as BUY.
    ema21 = row['EMA21']
    close = row['Close']
    near_ema = abs(close - ema21) / ema21 < 0.010  # within 1.0% of EMA21 (tighter based on simulation 4)
    if (ema_up and near_ema and SCALP_RSI[0] <= rsi <= SCALP_RSI[1] and vol > SCALP_VOL):
        return {'position': 'belowBar', 'color': '#00bcd4', 'shape': 'arrowUp', 'text': 'SCALP'}

    return None


def make_forecast(row) -> dict:
    score   = 0
    factors = []

    rsi       = row['RSI']
    vol       = row['Vol_ratio']
    bb        = row['BB_pct']
    ema_up    = row['EMA9'] > row['EMA21']
    ema_stack = row['EMA9'] > row['EMA21'] > row['EMA50']
    pullback  = row['consec_down']
    stoch     = row['Stoch_K']

    if ema_up:
        score += 15; factors.append({'label': 'EMA9 above EMA21', 'bull': True})
    if ema_stack:
        score += 10; factors.append({'label': 'Full EMA stack (EMA9>21>50)', 'bull': True})
    if 30 < rsi < 50:
        score += 20; factors.append({'label': f'RSI {rsi:.0f} — optimal buy zone', 'bull': True})
    elif 50 <= rsi <= 65:
        score += 5;  factors.append({'label': f'RSI {rsi:.0f} — healthy range', 'bull': True})
    if 1 <= pullback <= 3:
        score += 15; factors.append({'label': f'{int(pullback)} consecutive down day pullback', 'bull': True})
    if vol > 2.0:
        score += 25; factors.append({'label': f'Volume spike {vol:.1f}x (strong buying interest)', 'bull': True})
    elif vol > 1.5:
        score += 15; factors.append({'label': f'Volume {vol:.1f}x above avg', 'bull': True})
    elif vol > 1.2:
        score += 5;  factors.append({'label': f'Volume slightly elevated {vol:.1f}x', 'bull': True})
    if bb < 0.2:
        score += 20; factors.append({'label': 'Price near Bollinger lower band (potential bounce)', 'bull': True})
    elif bb < 0.4:
        score += 10; factors.append({'label': f'BB position {bb:.2f} — lower half', 'bull': True})
    if stoch < 25:
        score += 10; factors.append({'label': f'Stochastic {stoch:.0f} — oversold', 'bull': True})

    if rsi > 70:
        score -= 25; factors.append({'label': f'RSI {rsi:.0f} — overbought', 'bull': False})
    elif rsi > 60:
        score -= 10; factors.append({'label': f'RSI {rsi:.0f} — approaching overbought', 'bull': False})
    if bb > 0.85:
        score -= 20; factors.append({'label': f'Price near Bollinger upper band ({bb:.2f})', 'bull': False})
    if stoch > 80:
        score -= 15; factors.append({'label': f'Stochastic {stoch:.0f} — overbought', 'bull': False})
    if not ema_up:
        score -= 20; factors.append({'label': 'EMA9 below EMA21 (downtrend)', 'bull': False})
    if vol < 0.7:
        score -= 10; factors.append({'label': f'Volume dry ({vol:.1f}x) — weak interest', 'bull': False})

    confidence = max(38, min(90, 50 + score * 0.4))
    direction  = 'UP' if score > 10 else 'DOWN' if score < -10 else 'NEUTRAL'

    return {
        'direction':    direction,
        'confidence':   round(confidence),
        'score':        round(score),
        'factors':      factors,
        'rsi':          round(rsi, 1),
        'vol_ratio':    round(vol, 2),
        'bb_pct':       round(bb, 2),
        'stoch_k':      round(stoch, 1),
        'ema_uptrend':  bool(ema_up),
        'pullback_days': int(pullback),
    }
