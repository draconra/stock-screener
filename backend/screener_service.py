from tradingview_screener import Query, col
from services.indicators import (
    STRONG_BUY_RSI, STRONG_BUY_VOL,
    BUY_RSI, BUY_VOL,
    TREND_RSI, TREND_VOL,
)


def _price_ranges(row) -> dict:
    close = float(row.get('close') or 0)
    if close <= 0:
        return {'buy_low': 0, 'buy_high': 0, 'sell_low': 0, 'sell_high': 0}

    atr   = float(row.get('ATR') or 0) or (close * 0.02)
    ema21 = float(row.get('EMA21') or close)
    r1    = float(row.get('Pivot.M.Classic.R1') or 0)

    # Buy zone: EMA21 support up to current price
    buy_low  = int(round(max(ema21, close - atr * 0.5)))
    buy_high = int(round(close))
    if buy_low >= buy_high:          # safety if EMA21 > close (downtrend)
        buy_low = int(round(close - atr * 0.5))

    # Sell target: 1.5–2.5× ATR risk/reward, capped at monthly R1
    sell_low  = int(round(close + atr * 1.5))
    sell_high = int(round(close + atr * 2.5))
    if r1 > sell_low:
        sell_high = int(round(min(sell_high, r1)))

    return {'buy_low': buy_low, 'buy_high': buy_high,
            'sell_low': sell_low, 'sell_high': sell_high}


def get_scalp_candidates() -> dict:
    q = (Query()
         .set_markets('indonesia')
         .select('name', 'close', 'change', 'volume',
                 'relative_volume_10d_calc', 'RSI',
                 'EMA9', 'EMA21', 'ATR',
                 'Pivot.M.Classic.R1', 'Pivot.M.Classic.S1',
                 'sector')
         .where(
             col('relative_volume_10d_calc') > 1.2,
             col('change') > -5,
             col('RSI') < 75,
             col('RSI') > 20,
         )
         .order_by('relative_volume_10d_calc', ascending=False)
         .limit(60))

    _, df = q.get_scanner_data()

    def _signal(row) -> str:
        ema_up = row.get('EMA9', 0) > row.get('EMA21', 0)
        rsi    = row.get('RSI', 50)
        vol    = row.get('relative_volume_10d_calc', 1.0)

        if ema_up and STRONG_BUY_RSI[0] < rsi < STRONG_BUY_RSI[1] and vol > STRONG_BUY_VOL:
            return 'STRONG BUY'
        if ema_up and BUY_RSI[0] < rsi < BUY_RSI[1] and vol > BUY_VOL:
            return 'BUY'
        if ema_up and TREND_RSI[0] <= rsi <= TREND_RSI[1] and vol > TREND_VOL:
            return 'BUY'
        return 'WATCH'

    df['signal'] = df.apply(_signal, axis=1)

    ranges = df.apply(_price_ranges, axis=1, result_type='expand')
    df[['buy_low', 'buy_high', 'sell_low', 'sell_high']] = ranges

    grouped: dict = {}
    for sector, group in df.groupby('sector'):
        grouped[sector or 'Other'] = group.to_dict(orient='records')

    return grouped
