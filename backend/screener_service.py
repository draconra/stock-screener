from tradingview_screener import Query, col
from services.indicators import (
    STRONG_BUY_RSI, STRONG_BUY_VOL,
    BUY_RSI, BUY_VOL,
    TREND_RSI, TREND_VOL,
)
from services.calibration import calibrator


def get_scalp_candidates() -> dict:
    q = (Query()
         .set_markets('indonesia')
         .select('name', 'close', 'change', 'volume',
                 'relative_volume_10d_calc', 'RSI',
                 'EMA9', 'EMA21', 'ATR',
                 'BB.lower',
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

    def _ranges(row) -> dict:
        close = float(row.get('close') or 0)
        return calibrator.compute_ranges(
            signal=row.get('signal', 'WATCH'),
            close=close,
            atr=float(row.get('ATR') or 0) or (close * 0.02),
            ema21=float(row.get('EMA21') or close),
            vol_ratio=float(row.get('relative_volume_10d_calc') or 1.0),
            pivot_r1=float(row.get('Pivot.M.Classic.R1') or 0),
            pivot_s1=float(row.get('Pivot.M.Classic.S1') or 0),
            bb_lower=float(row.get('BB.lower') or 0),
        )

    ranges = df.apply(_ranges, axis=1, result_type='expand')
    df[['buy_low', 'buy_high', 'sell_low', 'sell_high']] = ranges

    grouped: dict = {}
    for sector, group in df.groupby('sector'):
        grouped[sector or 'Other'] = group.to_dict(orient='records')

    return grouped
