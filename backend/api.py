from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from tradingview_screener import Query
from services.indicators import compute_indicators, classify_candle, make_forecast
from services.news import fetch_news
from screener_service import get_scalp_candidates
from typing import Any
import yfinance as yf
import asyncio
import time


app = FastAPI()

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
                    markers.append({'time': row['time'], **m})
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
