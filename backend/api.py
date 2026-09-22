from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from tradingview_screener import Query
from services.indicators import compute_indicators, classify_candle, make_forecast
from services.news import fetch_news
from services.news_scraper import scrape_news_article
from services.syariah import is_syariah
from services.calibration import calibrator, auto_calibrate
from screener_service import get_scalp_candidates
from fundamentals import store as fundamentals_store
from fundamentals import screen as fundamentals_screen
from fundamentals.config import CONFIG_VERSION, GATES, PILLAR_MAX_POINTS
from typing import Any, Optional
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


@app.get("/api/news/article")
async def news_article(url: str):
    """On-demand full-article fetch for ONE Google News RSS item -- runs
    only when a user opens a specific article in the News tab's detail
    panel, never as part of the /api/news list. See
    services/news_scraper.py's module docstring for why this exists and
    what it deliberately does not do (no batch job, nothing persisted).

    `url` must be one of the news.google.com redirect links /api/news
    itself returned -- scrape_news_article() rejects anything else, so this
    endpoint can't be repurposed into a general "fetch any URL" proxy.

    Cached 1h: article content is static once published, and the same
    article can reasonably be reopened in one session.
    """
    cache_key = f"article:{url}"
    cached = _cache_get(cache_key, 3600)
    if cached is not None:
        return cached
    result = await asyncio.to_thread(scrape_news_article, url)
    if result["status"] == "success":
        _cache_set(cache_key, result)
    return result


# ─── Fundamental (long-term) screener ────────────────────────────────────
#
# Separate horizon from everything above: fundamentals update quarterly, not
# intraday, so this reads pre-computed CSV snapshots via `fundamentals.store`
# (stdlib csv/json only -- no pandas, no network) rather than the TTL `_cache`
# pattern used for the scalper. Data is refreshed offline (GitHub Actions,
# see .github/workflows/fundamentals-refresh.yml) and committed to `data/` --
# see backend/fundamentals/ for the full pipeline.
#
# `compute_indicators` (used by /api/history and /api/forecast above) is
# never imported here -- the fundamental screener computes its own timing
# hints independently so a future change to the scalper's indicators cannot
# break this feature, and vice versa.

_fundamentals_cache: dict[str, Any] = {}


def _scored_fundamentals() -> list:
    """Cached for the container's lifetime -- fundamentals data cannot go
    stale mid-container (it only changes via a redeploy), so there is no TTL
    to pick, unlike the scalper endpoints above."""
    if "reports" not in _fundamentals_cache:
        rows = list(fundamentals_store.latest_rows())
        reports = fundamentals_screen.score_all(
            rows, fundamentals_store.statements_for, is_syariah_fn=is_syariah
        )
        _fundamentals_cache["reports"] = reports
        _fundamentals_cache["universe_size"] = len(rows)
    return _fundamentals_cache["reports"]


@app.get("/api/fundamental/config")
async def fundamental_config():
    """Renders the exact ruleset a verdict was computed under -- so a
    verdict change a year from now is attributable to either the company or
    a reviewed config change, never an untracked guess."""
    return {
        "status": "success",
        "data": {"version": CONFIG_VERSION, "gates": GATES, "pillar_max_points": PILLAR_MAX_POINTS},
    }


@app.get("/api/fundamental/meta")
async def fundamental_meta():
    """Self-check -- hit this right after every deploy. If `rows_loaded` is
    low or missing, `data/` was not bundled by Vercel (see vercel.json
    includeFiles) even though everything works locally."""
    try:
        health = fundamentals_store.health()
        health["rows_loaded"] = len(fundamentals_store.latest_rows()) if fundamentals_store.has_data() else 0
        return {"status": "success", "data": health}
    except Exception as e:
        return {
            "status": "error",
            "message": f"fundamentals data not available: {e}",
            "data_dir": str(fundamentals_store.DATA_DIR),
        }


@app.get("/api/fundamental/screen")
async def fundamental_screen(
    min_score: int = 0,
    syariah_only: bool = False,
    sector: str = "",
    max_per: Optional[float] = None,
    min_yield: Optional[float] = None,
    include_failed: bool = False,
):
    """Long-term fundamental screen. Thresholds themselves are NOT
    overridable via query param -- see fundamentals/config.py's module
    docstring for why (it would let you dial a stock into passing, which is
    exactly what a multi-year screen exists to prevent). These params are
    views over one fixed computation, not new scoring rules."""
    try:
        if not fundamentals_store.has_data():
            return {"status": "error", "message": "No fundamentals snapshot yet -- run the refresh pipeline first"}
        reports = await asyncio.to_thread(_scored_fundamentals)
        universe_size = _fundamentals_cache.get("universe_size", len(reports))
        filtered = fundamentals_screen.apply_filters(
            reports, min_score=min_score, syariah_only=syariah_only, sector=sector,
            max_per=max_per, min_yield=min_yield, include_failed=include_failed,
        )
        funnel = fundamentals_screen.build_funnel(reports, universe_size, reports)
        passed = [r for r in reports if r.gates_passed]
        insufficient = [r for r in reports if r.verdict == "DATA_KURANG"]
        return {
            "status": "success",
            "data": {
                "as_of": fundamentals_store.meta().get("as_of"),
                "config_version": CONFIG_VERSION,
                "funnel": funnel,
                "counts": {
                    "evaluated": len(reports), "passed": len(passed),
                    "failed": len(reports) - len(passed), "insufficient_data": len(insufficient),
                },
                "groups": fundamentals_screen.group_by_sector(filtered),
                "failed": fundamentals_screen.failed_summary(reports),
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/fundamental/trend/{ticker}")
async def fundamental_trend(ticker: str):
    series = fundamentals_store.trend(ticker.upper())
    if not series:
        raise HTTPException(status_code=404, detail="No fundamental history for this ticker")
    return {"status": "success", "data": series}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
