from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser

NEWS_FEEDS = [
    {"url": "https://news.google.com/rss/search?q=IHSG+saham+indonesia+bursa&hl=id&gl=ID&ceid=ID:id",              "category": "IHSG"},
    {"url": "https://news.google.com/rss/search?q=bursa+efek+indonesia+investasi+emiten&hl=id&gl=ID&ceid=ID:id",  "category": "IDX"},
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


def get_sentiment(title: str) -> str:
    t    = title.lower()
    bull = sum(1 for w in _BULLISH_KW if w in t)
    bear = sum(1 for w in _BEARISH_KW if w in t)
    if bear > bull:  return "bearish"
    if bull > bear:  return "bullish"
    return "neutral"


def _time_ago(dt: datetime) -> str:
    diff = int((datetime.now(timezone.utc) - dt).total_seconds())
    if diff < 3600:   return f"{max(diff // 60, 1)}m ago"
    if diff < 86400:  return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


def fetch_news() -> dict:
    items: list = []
    seen:  set  = set()

    for feed_cfg in NEWS_FEEDS:
        try:
            d = feedparser.parse(feed_cfg["url"])
            for entry in d.entries[:30]:
                title = entry.get("title", "").strip()
                url   = entry.get("link", "")
                if not title or title in seen:
                    continue
                seen.add(title)

                try:
                    pub             = parsedate_to_datetime(entry.get("published", ""))
                    published_at    = pub.isoformat()
                    published_label = _time_ago(pub)
                except Exception:
                    published_at    = ""
                    published_label = ""

                src    = entry.get("source", {})
                source = src.get("title", "") if isinstance(src, dict) else str(src)

                items.append({
                    "title":           title,
                    "url":             url,
                    "source":          source,
                    "published_at":    published_at,
                    "published_label": published_label,
                    "category":        feed_cfg["category"],
                    "sentiment":       get_sentiment(title),
                })
        except Exception:
            continue

    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return {"status": "success", "data": items[:80]}


def analyze_ticker_hype(ticker: str) -> int:
    """
    Fetches recent news for a specific ticker (e.g., using yfinance) and calculates a hype score.
    Returns an integer representing the aggregated sentiment score.
    """
    try:
        import yfinance as yf
        # Ensure we use the proper .JK suffix for Indonesian stocks if not present
        if not ticker.endswith(".JK"):
            query_ticker = f"{ticker}.JK"
        else:
            query_ticker = ticker
            
        news_items = yf.Ticker(query_ticker).news
        if not news_items:
            return 0
            
        score = 0
        for item in news_items:
            title = item.get("title", "")
            if not title:
                continue
            sentiment = get_sentiment(title)
            if sentiment == "bullish":
                score += 1
            elif sentiment == "bearish":
                score -= 1
        return score
    except Exception as e:
        # Silently fail and return 0 if news cannot be fetched to not break the screener
        return 0
