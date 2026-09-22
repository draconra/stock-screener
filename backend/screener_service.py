import concurrent.futures

from tradingview_screener import Query, col
from services.syariah import is_syariah
from services.news import analyze_ticker_hype
from services.signal_engine import classify_signal, SignalInputs
from services.calibration import calibrator

# Liquidity gate in Rupiah turnover value, not raw share count. A share-count
# floor alone (the pre-filter below) admits e.g. a Rp5 stock trading exactly
# 1M shares -- Rp5,000,000 changing hands, right at IDX's own official
# low-liquidity line. IDX defines a low-liquidity name as average daily
# transaction value < Rp5,000,000 over a 3-month window (see plan doc). This
# is that same regulatory number, applied same-day rather than as a 3-month
# average -- deliberately NOT a larger invented "good liquidity" cutoff:
# picking a bigger number without backtesting data to justify it would be
# exactly the kind of un-validated threshold tuning the plan's research
# explicitly warns against (Sullivan/Timmermann/White 1999; Aronson 2006).
# Raising this bar is future work that needs real validation, not a guess.
MIN_TURNOVER_VALUE_IDR = 5_000_000  # IDX's own low-liquidity definition


def get_scalp_candidates() -> dict:
    q = (Query()
         .set_markets('indonesia')
         .select('name', 'close', 'change', 'volume',
                 'relative_volume_10d_calc', 'RSI',
                 'EMA9', 'EMA21', 'EMA50', 'ATR',
                 'BB.lower', 'BB.upper',
                 'Stoch.K',
                 'Pivot.M.Classic.R1', 'Pivot.M.Classic.S1',
                 'update_time',
                 'sector')
         .where(
             col('relative_volume_10d_calc') > 1.5,   # must be 50%+ above avg
             col('volume') > 1_000_000,                # coarse share-count pre-filter; turnover gate below is the real one
             col('change') > -10,
             col('RSI') < 80,
             # No RSI floor here (previously RSI > 15): a REVERSAL setup is
             # by definition deeply oversold, and IDX evidence favors
             # contrarian/mean-reversion over continuation (see plan doc) --
             # excluding the most-oversold names before REVERSAL can see them
             # was starving the one signal type the literature best supports.
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
    df = df[df.apply(
        lambda r: float(r.get('close') or 0) * float(r.get('volume') or 0) >= MIN_TURNOVER_VALUE_IDR,
        axis=1
    )]                                                           # real Rupiah turnover, not just share count

    def _signal(row) -> str:
        close  = float(row.get('close') or 0)
        ema9   = float(row.get('EMA9') or 0)
        ema21  = float(row.get('EMA21') or close or 1)
        ema50  = row.get('EMA50')
        bb_lo  = float(row.get('BB.lower') or 0)
        bb_hi  = float(row.get('BB.upper') or 0)
        bb_pct = (close - bb_lo) / (bb_hi - bb_lo) if bb_hi > bb_lo else 0.5
        stoch  = row.get('Stoch.K')

        ind: SignalInputs = {
            'rsi': row.get('RSI', 50),
            'vol_ratio': row.get('relative_volume_10d_calc', 1.0),
            'bb_pct': bb_pct,
            'close': close,
            'ema21': ema21,
            'ema_up': ema9 > ema21,
            'ema_stack': (ema9 > ema21 > float(ema50)) if ema50 is not None else None,
            # consec_down needs per-ticker OHLCV history, not available from
            # a scanner snapshot at this scale (up to 60 candidates) --
            # explicitly None, not silently defaulted, so the pullback-day
            # condition is skipped rather than always failing.
            'consec_down': None,
            'stoch_k': float(stoch) if stoch is not None else None,
        }
        return classify_signal(ind)

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
    df[['buy_low', 'buy_high', 'sell_low', 'sell_high', 'stop_loss']] = ranges

    df['is_syariah'] = df['name'].apply(is_syariah)

    # Concurrently fetch hype_score for all candidates
    tickers = df['name'].tolist()
    hype_scores = []
    # Using 10 workers to balance speed and not overloading yfinance
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # map guarantees results are returned in the exact order of `tickers`
        results = list(executor.map(analyze_ticker_hype, tickers))
        hype_scores = results
    
    df['hype_score'] = hype_scores

    grouped: dict = {}
    for sector, group in df.groupby('sector'):
        # Sort by hype_score first, then by close price
        sorted_group = group.sort_values(['hype_score', 'close'], ascending=[False, True])
        grouped[sector or 'Other'] = sorted_group.to_dict(orient='records')

    return grouped
