from tradingview_screener import Query, col
import pandas as pd

def get_scalp_candidates():
    """
    Fetches IDX stocks with momentum and volume characteristics,
    applies research-backed EMA + RSI + Volume signal logic,
    and groups by sector.
    """
    q = (Query()
         .set_markets('indonesia')
         .select(
             'name', 'close', 'change', 'volume',
             'relative_volume_10d_calc', 'RSI',
             'EMA9', 'EMA21', 'sector'
         )
         .where(
             col('relative_volume_10d_calc') > 1.2,
             col('change') > -5,           # Include slight dips (pullbacks)
             col('RSI') < 75,              # Exclude extreme overbought
             col('RSI') > 20,              # Exclude broken stocks
         )
         .order_by('relative_volume_10d_calc', ascending=False)
         .limit(60))

    _, df = q.get_scanner_data()

    def get_signal(row):
        ema_up    = row.get('EMA9', 0) > row.get('EMA21', 0)
        rsi       = row.get('RSI', 50)
        vol_ratio = row.get('relative_volume_10d_calc', 1.0)

        # STRONG BUY: EMA uptrend + RSI sweet spot + large vol spike
        if ema_up and 30 < rsi < 50 and vol_ratio > 2.0:
            return 'STRONG BUY'

        # BUY: EMA uptrend + RSI ok + decent vol
        if ema_up and 30 < rsi < 55 and vol_ratio > 1.5:
            return 'BUY'

        # Trend continuation buy
        if ema_up and 45 <= rsi <= 65 and vol_ratio > 1.3:
            return 'BUY'

        return 'WATCH'

    df['signal'] = df.apply(get_signal, axis=1)

    # Group by sector
    grouped = {}
    for sector, group in df.groupby('sector'):
        sector_label = sector if sector else 'Other'
        grouped[sector_label] = group.to_dict(orient='records')

    return grouped
