from tradingview_screener import Query, col
from services.syariah import is_syariah
from services.indicators import (
    STRONG_BUY_RSI, STRONG_BUY_VOL,
    BUY_RSI, BUY_VOL,
    TREND_RSI, TREND_VOL,
    SCALP_RSI, SCALP_VOL,
    REVERSAL_RSI, REVERSAL_VOL, REVERSAL_BB,
)
from services.calibration import calibrator


def get_scalp_candidates() -> dict:
    q = (Query()
         .set_markets('indonesia')
         .select('name', 'close', 'change', 'volume',
                 'relative_volume_10d_calc', 'RSI',
                 'EMA9', 'EMA21', 'ATR',
                 'BB.lower', 'BB.upper',
                 'Stoch.K',
                 'Pivot.M.Classic.R1', 'Pivot.M.Classic.S1',
                 'update_time',
                 'sector')
         .where(
             col('relative_volume_10d_calc') > 1.5,   # must be 50%+ above avg
             col('volume') > 1_000_000,                # min 1M shares traded today
             col('change') > -10,
             col('RSI') < 80,
             col('RSI') > 15,
         )
         .order_by('relative_volume_10d_calc', ascending=False)
         .limit(60))

    _, df = q.get_scanner_data()

    # Drop flat / structurally non-volatile stocks
    df = df[df['change'].abs() >= 0.5]                          # must have moved ≥0.5%
    df = df[df.apply(
        lambda r: (float(r.get('ATR') or 0) / float(r.get('close') or 1)) >= 0.005,
        axis=1
    )]                                                           # ATR ≥ 0.5% of price

    def _signal(row) -> str:
        ema_up = row.get('EMA9', 0) > row.get('EMA21', 0)
        rsi    = row.get('RSI', 50)
        vol    = row.get('relative_volume_10d_calc', 1.0)
        close  = float(row.get('close') or 0)
        ema21  = float(row.get('EMA21') or close or 1)
        bb_lo  = float(row.get('BB.lower') or 0)
        bb_hi  = float(row.get('BB.upper') or 0)
        stoch  = float(row.get('Stoch.K') or 50)

        bb_pct = (close - bb_lo) / (bb_hi - bb_lo) if bb_hi > bb_lo else 0.5
        near_ema = abs(close - ema21) / ema21 < 0.015

        if ema_up and STRONG_BUY_RSI[0] < rsi < STRONG_BUY_RSI[1] and vol > STRONG_BUY_VOL:
            return 'STRONG BUY'
        if ema_up and BUY_RSI[0] < rsi < BUY_RSI[1] and vol > BUY_VOL:
            return 'BUY'
        if ema_up and TREND_RSI[0] <= rsi <= TREND_RSI[1] and vol > TREND_VOL:
            return 'BUY'
        if ema_up and near_ema and SCALP_RSI[0] <= rsi <= SCALP_RSI[1] and vol > SCALP_VOL:
            return 'SCALP'
        if (not ema_up and (rsi < REVERSAL_RSI or stoch < 20)
                and bb_pct < REVERSAL_BB and vol > REVERSAL_VOL):
            return 'REVERSAL'
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

    df['is_syariah'] = df['name'].apply(is_syariah)

    grouped: dict = {}
    for sector, group in df.groupby('sector'):
        grouped[sector or 'Other'] = group.sort_values('close').to_dict(orient='records')

    return grouped
