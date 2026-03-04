from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from tradingview_screener import Query
from services.indicators import compute_indicators, classify_candle, make_forecast
from services.news import fetch_news
from services.calibration import calibrator, auto_calibrate
from screener_service import get_scalp_candidates
from typing import Any
import yfinance as yf
import asyncio
import logging
import time
import urllib.request
import json as _json
import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(asyncio.to_thread(auto_calibrate, calibrator, 20))
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory TTL cache ─────────────────────────────────────────
_cache: dict[str, tuple[float, Any]] = {}

def _cache_get(key: str, ttl: int) -> Any:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None

def _cache_set(key: str, val: Any) -> None:
    _cache[key] = (time.time(), val)


def format_ticker(symbol: str) -> str:
    return symbol.split(':')[-1] + ".JK"


def get_market_status() -> str:
    """IDX trading hours: 09:00–15:50 WIB (UTC+7), Mon–Fri."""
    now_wib = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    if now_wib.weekday() >= 5:  # Sat/Sun
        return 'closed'
    t = now_wib.hour * 60 + now_wib.minute
    if 9 * 60 <= t <= 15 * 60 + 50:
        return 'open'
    if 8 * 60 <= t < 9 * 60:
        return 'pre-market'
    return 'closed'


# ─── Endpoints ──────────────────────────────────────────────────

@app.get("/api/candidates")
async def candidates():
    cached = _cache_get("candidates", 300)
    if cached is not None:
        return {"status": "success", "data": cached}
    try:
        data = await asyncio.to_thread(get_scalp_candidates)
        _cache_set("candidates", data)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/search")
async def search(q: str = ""):
    if not q or len(q) < 2:
        return {"status": "success", "data": []}
    cache_key = f"search:{q.upper()}"
    cached = _cache_get(cache_key, 120)
    if cached is not None:
        return {"status": "success", "data": cached}
    try:
        def _search():
            query = (Query()
                .set_markets('indonesia')
                .select('name', 'close', 'change', 'volume', 'relative_volume_10d_calc', 'RSI', 'sector')
                .limit(100))
            _, df = query.get_scanner_data()
            q_upper = q.upper()
            mask = (
                df['name'].str.upper().str.contains(q_upper, na=False) |
                df['ticker'].str.upper().str.contains(q_upper, na=False)
            )
            matched = df[mask].head(10).copy()
            matched['signal'] = 'WATCH'
            return matched.to_dict(orient='records')

        data = await asyncio.to_thread(_search)
        _cache_set(cache_key, data)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/history/{symbol}")
async def history(symbol: str):
    cache_key = f"history:{symbol}"
    cached = _cache_get(cache_key, 1800)
    if cached is not None:
        return cached
    try:
        def _fetch():
            df = yf.Ticker(format_ticker(symbol)).history(period="1y", interval="1d")
            if df.empty:
                return None
            df = compute_indicators(df).dropna().reset_index()
            df['time'] = df['Date'].apply(lambda x: x.strftime('%Y-%m-%d'))
            markers = []
            for _, row in df.iterrows():
                m = classify_candle(row)
                if m:
                    close = float(row['Close'])
                    atr   = float(row['ATR'])
                    ema21 = float(row['EMA21'])
                    vol   = float(row['Vol_ratio'])
                    bb_lo = float(row['BB_lower']) if 'BB_lower' in row.index else 0
                    # Compute buy/sell price ranges for this signal
                    ranges = calibrator.compute_ranges(
                        signal=m['text'].replace(' BUY', ' BUY') if 'BUY' in m['text'] else m['text'],
                        close=close,
                        atr=atr if atr > 0 else close * 0.02,
                        ema21=ema21 if ema21 > 0 else close,
                        vol_ratio=vol,
                        bb_lower=bb_lo,
                    )
                    markers.append({
                        'time': row['time'],
                        **m,
                        'buy_low':   ranges['buy_low'],
                        'buy_high':  ranges['buy_high'],
                        'sell_low':  ranges['sell_low'],
                        'sell_high': ranges['sell_high'],
                    })
            chart_data = df[['time', 'Open', 'High', 'Low', 'Close']].rename(
                columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'}
            ).to_dict(orient='records')
            return {"status": "success", "data": chart_data, "markers": markers}

        result = await asyncio.to_thread(_fetch)
        if result is None:
            raise HTTPException(status_code=404, detail="No data found")
        _cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/forecast/{symbol}")
async def forecast(symbol: str):
    cache_key = f"forecast:{symbol}"
    cached = _cache_get(cache_key, 1800)
    if cached is not None:
        return cached
    try:
        def _fetch():
            df = yf.Ticker(format_ticker(symbol)).history(period="6mo", interval="1d")
            if df.empty:
                return None
            df   = compute_indicators(df).dropna()
            last = df.iloc[-1]
            res  = make_forecast(last)
            res['last_close'] = round(float(last['Close']), 2)
            res['last_date']  = str(df.index[-1].date())
            res['symbol']     = symbol
            res['atr']        = round(float(last['ATR']), 2)
            return {"status": "success", "data": res}

        result = await asyncio.to_thread(_fetch)
        if result is None:
            raise HTTPException(status_code=404, detail="No data found")
        _cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ihsg")
async def ihsg():
    cached = _cache_get("ihsg", 30)
    if cached is not None:
        return cached
    try:
        def _fetch():
            # Yahoo Finance v8 chart API — instrumentType=INDEX has no declared delay
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EJKSE?interval=1m&range=1d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = _json.loads(r.read())

            meta  = raw["chart"]["result"][0]["meta"]
            price = float(meta["regularMarketPrice"])
            prev  = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
            change     = price - prev
            change_pct = (change / prev * 100) if prev else 0.0
            market_ts  = int(meta.get("regularMarketTime") or 0)

            # Measure actual delay — Yahoo Finance IDX data is consistently ~10 min
            # despite exchangeDataDelayedBy=None (field is misleading for IDX)
            actual_delay_min = round((time.time() - market_ts) / 60) if market_ts else 10

            return {
                "status": "success",
                "data": {
                    "price":         round(price, 2),
                    "change":        round(change, 2),
                    "change_pct":    round(change_pct, 2),
                    "open":          round(float(meta.get("regularMarketOpen") or prev), 2),
                    "day_high":      round(float(meta.get("regularMarketDayHigh") or price), 2),
                    "day_low":       round(float(meta.get("regularMarketDayLow") or price), 2),
                    "market_time":   market_ts,
                    "delayed_by":    actual_delay_min,
                    "market_status": get_market_status(),
                }
            }
        result = await asyncio.to_thread(_fetch)
        _cache_set("ihsg", result)
        return result
    except Exception as e:
        logging.warning(f"IHSG fetch failed: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/quote/{symbol}")
async def quote(symbol: str):
    """Real-time quote for a single IDX stock via Yahoo Finance (.JK)."""
    cache_key = f"quote:{symbol.upper()}"
    cached = _cache_get(cache_key, 30)
    if cached is not None:
        return cached
    try:
        def _fetch():
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{format_ticker(symbol)}?interval=2m&range=1d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = _json.loads(r.read())

            meta  = raw["chart"]["result"][0]["meta"]
            price = float(meta["regularMarketPrice"])
            prev  = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price)
            change     = price - prev
            change_pct = (change / prev * 100) if prev else 0.0
            market_ts  = int(meta.get("regularMarketTime") or 0)
            actual_delay_min = round((time.time() - market_ts) / 60) if market_ts else 10

            return {
                "status": "success",
                "data": {
                    "ticker":        symbol.upper(),
                    "price":         round(price, 0),
                    "change":        round(change, 0),
                    "change_pct":    round(change_pct, 2),
                    "open":          round(float(meta.get("regularMarketOpen") or prev), 0),
                    "day_high":      round(float(meta.get("regularMarketDayHigh") or price), 0),
                    "day_low":       round(float(meta.get("regularMarketDayLow") or price), 0),
                    "market_time":   market_ts,
                    "delayed_by":    actual_delay_min,
                    "market_status": get_market_status(),
                }
            }
        result = await asyncio.to_thread(_fetch)
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        logging.warning(f"Quote fetch failed for {symbol}: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/news")
async def news():
    cached = _cache_get("news", 600)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(fetch_news)
    _cache_set("news", result)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
