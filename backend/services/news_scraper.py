"""On-demand full-article scraper for a single Google News RSS item.

Runs only when a user explicitly asks to read one article (the /api/news
endpoint and its 80-item feed never trigger this) -- nothing here is a
batch job and nothing is persisted to disk. That keeps the legal exposure
closer to "fetch what the user asked to read, once" than to "bulk-store and
redistribute a copy of every article we can reach."

Two real problems this solves, both measured against live Google News RSS
(2026-09-22) before writing any of this:

1. `entry.link` from feedparser is a `news.google.com/rss/articles/...`
   redirect, not the publisher's URL. It does NOT resolve via a plain HTTP
   GET -- the response is a JS-rendered SPA shell that stays on
   news.google.com. Confirmed directly with urllib. `googlenewsdecoder`
   decodes the base64-ish payload in the URL to recover the real publisher
   URL without needing a headless browser.

2. Publisher HTML structure varies completely across sources (ANTARA,
   CNBC Indonesia, Kontan, Bloomberg Technoz, ...). `trafilatura` is a
   generic content-extraction library (boilerplate/nav/ads removal, no
   per-site config) -- tested live against 8 real articles across 8
   different publishers, 8/8 resolved and extracted cleanly.

Both steps fail sometimes (decode failure, publisher blocks/paywalls,
extraction finds nothing) -- every failure mode here returns a structured
{"status": "error", ...} result, never raises, so the caller can fall back
to "here's the metadata we already have, plus a link to the original."
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT_SECONDS = 10
_DECODE_INTERVAL_SECONDS = 1  # googlenewsdecoder's own retry/backoff pacing

# Basic SSRF guard: this endpoint takes a URL from the client and fetches it
# server-side. Constrain the INPUT to genuine Google News redirect links
# (the only kind /api/news ever returns) so this can't be repurposed into an
# arbitrary "fetch any URL through our server" proxy.
_ALLOWED_INPUT_HOST = "news.google.com"
_BLOCKED_RESOLVED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"}


def _is_safe_input_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and parsed.hostname == _ALLOWED_INPUT_HOST


def _is_safe_resolved_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_RESOLVED_HOSTS:
        return False
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
        return False
    return True


def resolve_publisher_url(google_news_url: str) -> dict:
    """google.news redirect -> real publisher URL. Never raises."""
    if not _is_safe_input_url(google_news_url):
        return {"ok": False, "reason": "not_a_google_news_url"}

    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        return {"ok": False, "reason": "decoder_unavailable"}

    try:
        result = gnewsdecoder(google_news_url, interval=_DECODE_INTERVAL_SECONDS)
    except Exception as e:
        logger.warning(f"gnewsdecoder failed: {e}")
        return {"ok": False, "reason": f"decode_exception:{type(e).__name__}"}

    if not result or not result.get("status"):
        return {"ok": False, "reason": "decode_failed"}

    resolved = result.get("decoded_url")
    if not resolved or not _is_safe_resolved_url(resolved):
        return {"ok": False, "reason": "resolved_url_unsafe_or_missing"}

    return {"ok": True, "url": resolved}


def scrape_article_text(publisher_url: str) -> dict:
    """Fetch + extract main article text from a publisher URL. Never raises."""
    try:
        import trafilatura
        from trafilatura.settings import use_config
    except ImportError:
        return {"ok": False, "reason": "extractor_unavailable"}

    # trafilatura's default DOWNLOAD_TIMEOUT is 30s (settings.cfg) -- too
    # long for a request a user is actively waiting on. Confirmed
    # use_config() returns a mutable ConfigParser that fetch_url() honors.
    config = use_config()
    config.set("DEFAULT", "DOWNLOAD_TIMEOUT", str(_FETCH_TIMEOUT_SECONDS))

    try:
        downloaded = trafilatura.fetch_url(publisher_url, config=config)
    except Exception as e:
        logger.warning(f"trafilatura.fetch_url failed for {publisher_url}: {e}")
        return {"ok": False, "reason": f"fetch_exception:{type(e).__name__}"}

    if not downloaded:
        return {"ok": False, "reason": "fetch_empty"}

    try:
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        metadata = trafilatura.extract_metadata(downloaded)
    except Exception as e:
        logger.warning(f"trafilatura.extract failed for {publisher_url}: {e}")
        return {"ok": False, "reason": f"extract_exception:{type(e).__name__}"}

    if not text or len(text.strip()) < 80:
        # Extraction "succeeded" but found nothing usable -- common on
        # paywalled or heavily JS-rendered pages trafilatura can't parse.
        return {"ok": False, "reason": "extract_too_short"}

    site = None
    if metadata is not None:
        site = metadata.sitename or metadata.hostname
    if not site:
        site = urlparse(publisher_url).hostname

    return {
        "ok": True,
        "text": text.strip(),
        "title": (metadata.title if metadata else None),
        "author": (metadata.author if metadata else None),
        "date": (metadata.date if metadata else None),
        "site": site,
        "publisher_url": publisher_url,
    }


def scrape_news_article(google_news_url: str) -> dict:
    """The single entry point the API endpoint calls. Combines decode +
    scrape into one structured result:

        {"status": "success", "data": {...}}
        {"status": "error", "reason": "<short machine-readable code>"}

    `reason` values are intentionally short and stable -- the frontend maps
    them to a friendly Indonesian message, never shows the raw code.
    """
    resolved = resolve_publisher_url(google_news_url)
    if not resolved["ok"]:
        return {"status": "error", "reason": resolved["reason"]}

    scraped = scrape_article_text(resolved["url"])
    if not scraped["ok"]:
        return {"status": "error", "reason": scraped["reason"]}

    return {
        "status": "success",
        "data": {
            "text": scraped["text"],
            "title": scraped["title"],
            "author": scraped["author"],
            "date": scraped["date"],
            "site": scraped["site"],
            "publisher_url": scraped["publisher_url"],
        },
    }
