from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from screener_service import get_scalp_candidates
from tradingview_screener import Query
from typing import Optional, Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import yfinance as yf
import pandas as pd
import numpy as np
import feedparser
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


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all indicators needed for signals and forecasting."""
    # RSI 14
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))

    # EMAs
    df['EMA9']  = df['Close'].ewm(span=9).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()

    # Bollinger Bands (20,2)
    df['BB_mid']   = df['Close'].rolling(20).mean()
    bb_std         = df['Close'].rolling(20).std()
    df['BB_upper'] = df['BB_mid'] + 2 * bb_std
    df['BB_lower'] = df['BB_mid'] - 2 * bb_std
    df['BB_pct']   = (df['Close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'])

    # Stochastic %K,%D (14,3)
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

    # Consecutive down days (pullback counter)
    df['pct_chg']  = df['Close'].pct_change()
    df['down_day'] = (df['pct_chg'] < 0).astype(int)
    df['consec_down'] = (
        df['down_day']
        .groupby((df['down_day'] != df['down_day'].shift()).cumsum())
        .cumcount() + 1
    ) * df['down_day']

    return df


def classify_candle(row) -> Optional[dict]:
    """
    Classify a single row as STRONG BUY / BUY / SELL or None.
    Returns marker dict or None.
    Research-backed thresholds (see signal_research.md):
      STRONG BUY  ~65-80% 3-day accuracy
      BUY         ~54-65% 3-day accuracy
      SELL        ~57% negative 3-day accuracy
    """
    ema_up   = row['EMA9'] > row['EMA21']
    rsi      = row['RSI']
    vol      = row['Vol_ratio']
    bb       = row['BB_pct']
    pullback = row['consec_down']

    # STRONG BUY
    if (ema_up and
            2 <= pullback <= 3 and
            30 < rsi < 50 and
            vol > 2.0 and
            bb < 0.5):
        return {'position': 'belowBar', 'color': '#00e676', 'shape': 'arrowUp', 'text': 'STRONG BUY'}

    # BUY
    if ema_up and 1 <= pullback <= 3 and 30 < rsi < 55 and vol > 1.5:
        return {'position': 'belowBar', 'color': '#2196F3', 'shape': 'arrowUp', 'text': 'BUY'}

    # Also BUY via trend continuation (EMA stack, RSI sweet spot, vol surge)
    if (row['EMA9'] > row['EMA21'] > row['EMA50'] and
            45 <= rsi <= 65 and
            vol > 1.3 and
            bb < 0.7):
        return {'position': 'belowBar', 'color': '#2196F3', 'shape': 'arrowUp', 'text': 'BUY'}

    # SELL / overbought
    if bb > 0.85 and rsi > 65 and vol > 1.5:
        return {'position': 'aboveBar', 'color': '#e91e63', 'shape': 'arrowDown', 'text': 'SELL'}

    return None


def make_forecast(row) -> dict:
    """
    Score today's candle to produce a tomorrow direction forecast.
    Returns direction, confidence (0-100), and a list of factor strings.
    """
    score  = 0   # positive = bullish, negative = bearish
    factors = []

    rsi  = row['RSI']
    vol  = row['Vol_ratio']
    bb   = row['BB_pct']
    ema_up = row['EMA9'] > row['EMA21']
    ema_stack = row['EMA9'] > row['EMA21'] > row['EMA50']
    pullback = row['consec_down']
    stoch = row['Stoch_K']

    # === Bullish factors ===
    if ema_up:
        score += 15
        factors.append({'label': 'EMA9 above EMA21', 'bull': True})
    if ema_stack:
        score += 10
        factors.append({'label': 'Full EMA stack (EMA9>21>50)', 'bull': True})
    if 30 < rsi < 50:
        score += 20
        factors.append({'label': f'RSI {rsi:.0f} — optimal buy zone', 'bull': True})
    elif 50 <= rsi <= 65:
        score += 5
        factors.append({'label': f'RSI {rsi:.0f} — healthy range', 'bull': True})
    if 1 <= pullback <= 3:
        score += 15
        factors.append({'label': f'{int(pullback)} consecutive down day pullback', 'bull': True})
    if vol > 2.0:
        score += 25
        factors.append({'label': f'Volume spike {vol:.1f}x (strong buying interest)', 'bull': True})
    elif vol > 1.5:
        score += 15
        factors.append({'label': f'Volume {vol:.1f}x above avg', 'bull': True})
    elif vol > 1.2:
        score += 5
        factors.append({'label': f'Volume slightly elevated {vol:.1f}x', 'bull': True})
    if bb < 0.2:
        score += 20
        factors.append({'label': 'Price near Bollinger lower band (potential bounce)', 'bull': True})
    elif bb < 0.4:
        score += 10
        factors.append({'label': f'BB position {bb:.2f} — lower half', 'bull': True})
    if stoch < 25:
        score += 10
        factors.append({'label': f'Stochastic {stoch:.0f} — oversold', 'bull': True})

    # === Bearish factors ===
    if rsi > 70:
        score -= 25
        factors.append({'label': f'RSI {rsi:.0f} — overbought', 'bull': False})
    elif rsi > 60:
        score -= 10
        factors.append({'label': f'RSI {rsi:.0f} — approaching overbought', 'bull': False})
    if bb > 0.85:
        score -= 20
        factors.append({'label': f'Price near Bollinger upper band ({bb:.2f})', 'bull': False})
    if stoch > 80:
        score -= 15
        factors.append({'label': f'Stochastic {stoch:.0f} — overbought', 'bull': False})
    if not ema_up:
        score -= 20
        factors.append({'label': 'EMA9 below EMA21 (downtrend)', 'bull': False})
    if vol < 0.7:
        score -= 10
        factors.append({'label': f'Volume dry ({vol:.1f}x) — weak interest', 'bull': False})

    # Convert score to confidence (clamp 40-90%)
    # Neutral ~0 = 50%, max bullish ~100 = 90%, max bearish ~-100 = 10%
    raw_conf = 50 + (score * 0.4)
    confidence = max(38, min(90, raw_conf))

    if score > 10:
        direction = 'UP'
    elif score < -10:
        direction = 'DOWN'
    else:
        direction = 'NEUTRAL'

    return {
        'direction': direction,
        'confidence': round(confidence),
        'score': round(score),
        'factors': factors,
        'rsi': round(rsi, 1),
        'vol_ratio': round(vol, 2),
        'bb_pct': round(bb, 2),
        'stoch_k': round(stoch, 1),
        'ema_uptrend': bool(ema_up),
        'pullback_days': int(pullback),
    }


# ─── News helpers ───────────────────────────────────────────────

NEWS_FEEDS = [
    {"url": "https://news.google.com/rss/search?q=IHSG+saham+indonesia+bursa&hl=id&gl=ID&ceid=ID:id", "category": "IHSG"},
    {"url": "https://news.google.com/rss/search?q=bursa+efek+indonesia+investasi+emiten&hl=id&gl=ID&ceid=ID:id", "category": "IDX"},
    {"url": "https://news.google.com/rss/search?q=indonesia+stock+market+IDX+IHSG+economy&hl=en-US&gl=US&ceid=US:en", "category": "Global"},
    {"url": "https://news.google.com/rss/search?q=coal+palm+oil+nickel+indonesia+commodity&hl=en-US&gl=US&ceid=US:en", "category": "Commodity"},
]

_BEARISH_KW = [
    "drop", "fall", "crash", "decline", "weak", "fear", "warning", "risk", "slump",
    "ambruk", "jeblok", "turun", "jatuh", "perang", "anjlok", "melemah", "koreksi",
    "jual", "rugi", "tersungkur", "tertekan", "terpuruk",
]
_BULLISH_KW = [
    "rise", "gain", "rally", "growth", "strong", "bullish", "surge", "recover", "rebound",
    "naik", "optimis", "menguat", "tumbuh", "positif", "beli", "kuat", "reli",
]


def _get_sentiment(title: str) -> str:
    t = title.lower()
    bull = sum(1 for w in _BULLISH_KW if w in t)
    bear = sum(1 for w in _BEARISH_KW if w in t)
    if bear > bull:
        return "bearish"
    if bull > bear:
        return "bullish"
    return "neutral"


def _time_ago(dt: datetime) -> str:
    diff = int((datetime.now(timezone.utc) - dt).total_seconds())
    if diff < 3600:
        return f"{max(diff // 60, 1)}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


# ─── Endpoints ──────────────────────────────────────────────────

@app.get("/api/candidates")
async def candidates():
    cached = _cache_get("candidates", 300)  # 5 min
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
    cached = _cache_get(cache_key, 120)  # 2 min
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
    """Daily OHLC + buy/sell markers using research-backed signal logic."""
    cache_key = f"history:{symbol}"
    cached = _cache_get(cache_key, 1800)  # 30 min
    if cached is not None:
        return cached
    try:
        def _fetch():
            ticker_symbol = format_ticker(symbol)
            df = yf.Ticker(ticker_symbol).history(period="1y", interval="1d")
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
    """Tomorrow's direction forecast based on today's indicators."""
    cache_key = f"forecast:{symbol}"
    cached = _cache_get(cache_key, 1800)  # 30 min
    if cached is not None:
        return cached
    try:
        def _fetch():
            ticker_symbol = format_ticker(symbol)
            df = yf.Ticker(ticker_symbol).history(period="6mo", interval="1d")
            if df.empty:
                return None
            df = compute_indicators(df).dropna()
            last = df.iloc[-1]
            result = make_forecast(last)
            result['last_close'] = round(float(last['Close']), 2)
            result['last_date']  = str(df.index[-1].date())
            result['symbol']     = symbol
            result['atr']        = round(float(last['ATR']), 2)
            return {"status": "success", "data": result}

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
    cached = _cache_get("news", 600)  # 10 min
    if cached is not None:
        return cached

    def _fetch_news():
        items = []
        seen: set = set()
        for feed_cfg in NEWS_FEEDS:
            try:
                d = feedparser.parse(feed_cfg["url"])
                for entry in d.entries[:30]:
                    title = entry.get("title", "").strip()
                    url = entry.get("link", "")
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    try:
                        pub = parsedate_to_datetime(entry.get("published", ""))
                        published_at = pub.isoformat()
                        published_label = _time_ago(pub)
                    except Exception:
                        published_at = ""
                        published_label = ""
                    src = entry.get("source", {})
                    source = src.get("title", "") if isinstance(src, dict) else str(src)
                    items.append({
                        "title": title,
                        "url": url,
                        "source": source,
                        "published_at": published_at,
                        "published_label": published_label,
                        "category": feed_cfg["category"],
                        "sentiment": _get_sentiment(title),
                    })
            except Exception:
                continue
        items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return {"status": "success", "data": items[:80]}

    result = await asyncio.to_thread(_fetch_news)
    _cache_set("news", result)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
