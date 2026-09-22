import React, { useEffect, useState } from 'react';
import { Newspaper, RefreshCw, ExternalLink, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { API_BASE } from '../config';

interface NewsItem {
    title: string;
    url: string;
    source: string;
    published_at: string;
    published_label: string;
    category: 'IHSG' | 'IDX' | 'Global' | 'Commodity';
    sentiment: 'bullish' | 'bearish' | 'neutral';
}

const CATEGORY_COLORS: Record<string, string> = {
    IHSG: '#1f6feb',
    IDX: '#238636',
    Global: '#8957e5',
    Commodity: '#d4a017',
};

const SentimentIcon = ({ sentiment }: { sentiment: string }) => {
    if (sentiment === 'bullish') return <TrendingUp size={13} color="#26a69a" />;
    if (sentiment === 'bearish') return <TrendingDown size={13} color="#ef5350" />;
    return <Minus size={13} color="#6e7681" />;
};

const SENTIMENT_LABEL: Record<string, string> = {
    bullish: 'Bullish', bearish: 'Bearish', neutral: 'Netral',
};

const FILTERS = ['All', 'IHSG', 'IDX', 'Global', 'Commodity'];

interface ArticleData {
    text: string;
    title: string | null;
    author: string | null;
    date: string | null;
    site: string | null;
    publisher_url: string;
}

// Friendly messages for the backend's short machine-readable failure
// reasons (services/news_scraper.py) -- never show the raw code to the
// user, and always keep the "buka artikel asli" path available since a
// failure here just means "couldn't fetch it for you automatically."
const FAILURE_MESSAGE: Record<string, string> = {
    decode_failed: 'Tidak bisa menemukan URL asli dari link Google News ini.',
    resolved_url_unsafe_or_missing: 'Tidak bisa menemukan URL asli dari link Google News ini.',
    fetch_empty: 'Situs sumber tidak merespons.',
    extract_too_short: 'Situs sumber kemungkinan berbayar atau memblokir pengambilan otomatis.',
};
const DEFAULT_FAILURE_MESSAGE = 'Tidak bisa memuat artikel penuh secara otomatis.';

function failureMessage(reason: string): string {
    if (FAILURE_MESSAGE[reason]) return FAILURE_MESSAGE[reason];
    if (reason.startsWith('fetch_')) return 'Situs sumber tidak bisa diakses.';
    if (reason.startsWith('extract_')) return 'Tidak bisa mengambil isi artikel dari situs sumber.';
    return DEFAULT_FAILURE_MESSAGE;
}

// On-demand full-article fetch: scrapes ONE article, only when the user
// picks it here -- never as part of the news list itself. See
// backend/services/news_scraper.py's module docstring for why (resolves
// the Google News redirect via googlenewsdecoder, then extracts the main
// article text via trafilatura; nothing is scraped in bulk or persisted).
// A failure here degrades to the metadata + external-link view that
// existed before this feature -- it never blocks reading the article,
// just skips the in-app convenience.
const NewsDetail: React.FC<{ item: NewsItem | null }> = ({ item }) => {
    const [article, setArticle] = useState<ArticleData | null>(null);
    const [articleLoading, setArticleLoading] = useState(false);
    const [articleError, setArticleError] = useState<string | null>(null);

    useEffect(() => {
        setArticle(null);
        setArticleError(null);
        if (!item) return;

        let cancelled = false;
        setArticleLoading(true);
        fetch(`${API_BASE}/api/news/article?url=${encodeURIComponent(item.url)}`)
            .then(res => res.json())
            .then(result => {
                if (cancelled) return;
                if (result.status === 'success') {
                    setArticle(result.data);
                } else {
                    setArticleError(failureMessage(result.reason || ''));
                }
            })
            .catch(() => {
                if (!cancelled) setArticleError(DEFAULT_FAILURE_MESSAGE);
            })
            .finally(() => {
                if (!cancelled) setArticleLoading(false);
            });

        return () => { cancelled = true; };
    }, [item]);

    if (!item) {
        return <div className="empty-state">Pilih berita di kiri untuk lihat detail.</div>;
    }
    const catColor = CATEGORY_COLORS[item.category] || '#1f6feb';
    return (
        <div className="news-detail">
            <div className="detail-section">
                <span
                    className="news-detail-category"
                    style={{ background: catColor + '20', color: catColor, border: `1px solid ${catColor}40` }}
                >
                    {item.category}
                </span>
                <h2 className="news-detail-title">{item.title}</h2>
                <div className="news-detail-meta">
                    {item.source && <span>{item.source}</span>}
                    {item.published_label && <span>· {item.published_label}</span>}
                    <span className="news-detail-sentiment">
                        <SentimentIcon sentiment={item.sentiment} /> {SENTIMENT_LABEL[item.sentiment]}
                    </span>
                </div>
            </div>

            <div className="detail-section">
                {articleLoading && (
                    <div className="news-article-status">Memuat artikel penuh…</div>
                )}

                {!articleLoading && article && (
                    <>
                        {(article.author || article.date) && (
                            <div className="news-article-byline">
                                {article.author && <span>Oleh {article.author}</span>}
                                {article.author && article.date && <span> · </span>}
                                {article.date && <span>{article.date}</span>}
                            </div>
                        )}
                        <div className="news-article-text">
                            {article.text.split(/\n+/).filter(Boolean).map((para, i) => (
                                <p key={i}>{para}</p>
                            ))}
                        </div>
                        <div className="news-article-attribution">
                            Diambil otomatis dari {article.site || 'situs sumber'} — cek langsung ke
                            sumbernya untuk tampilan asli, gambar, dan konteks lengkap.
                        </div>
                    </>
                )}

                {!articleLoading && !article && articleError && (
                    <div className="news-article-status news-article-status-error">
                        {articleError} Google News RSS sendiri hanya menyediakan judul dan sumber.
                    </div>
                )}
            </div>

            <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="news-detail-open-btn"
            >
                Buka artikel asli <ExternalLink size={13} />
            </a>
        </div>
    );
};

const NewsTab: React.FC = () => {
    const [news, setNews] = useState<NewsItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('All');
    const [lastUpdated, setLastUpdated] = useState('');
    const [selectedNews, setSelectedNews] = useState<NewsItem | null>(null);

    const fetchNews = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/news`);
            const result = await res.json();
            if (result.status === 'success') {
                setNews(result.data);
                setLastUpdated(new Date().toLocaleTimeString());
            }
        } catch (e) {
            console.error('News fetch error:', e);
        }
        setLoading(false);
    };

    useEffect(() => { fetchNews(); }, []);

    const counts: Record<string, number> = { All: news.length };
    FILTERS.slice(1).forEach(cat => {
        counts[cat] = news.filter(n => n.category === cat).length;
    });

    const filtered = filter === 'All' ? news : news.filter(n => n.category === filter);

    // Keep a detail item selected: pick the first of the current filtered
    // list on load, on filter change, or if the previous selection fell
    // out of the filtered set. Does not fight a still-valid manual pick.
    useEffect(() => {
        if (filtered.length === 0) {
            setSelectedNews(null);
            return;
        }
        if (!selectedNews || !filtered.some(n => n.url === selectedNews.url)) {
            setSelectedNews(filtered[0]);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filter, news]);

    // Sentiment summary for current filter
    const bullCount = filtered.filter(n => n.sentiment === 'bullish').length;
    const bearCount = filtered.filter(n => n.sentiment === 'bearish').length;
    const total = filtered.length || 1;
    const bullPct = Math.round((bullCount / total) * 100);
    const bearPct = Math.round((bearCount / total) * 100);
    const marketMood = bullPct > bearPct + 10 ? 'Bullish' : bearPct > bullPct + 10 ? 'Bearish' : 'Mixed';
    const moodColor = marketMood === 'Bullish' ? '#26a69a' : marketMood === 'Bearish' ? '#ef5350' : '#f0b429';

    return (
        <div className="news-layout">
            <div className="news-list-pane">
                {/* Header row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Newspaper size={17} color="#1f6feb" />
                        <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Market News</span>
                        {lastUpdated && (
                            <span style={{ fontSize: '0.72rem', color: '#6e7681' }}>· {lastUpdated}</span>
                        )}
                    </div>
                    <button
                        onClick={fetchNews}
                        disabled={loading}
                        style={{ background: '#21262d', border: '1px solid #30363d', color: 'white', padding: '5px 12px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem' }}
                    >
                        <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
                        Refresh
                    </button>
                </div>

                {/* Sentiment bar */}
                {!loading && filtered.length > 0 && (
                    <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px', padding: '10px 14px', marginTop: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                            <span style={{ fontSize: '0.8rem', color: '#8b949e' }}>Market Sentiment</span>
                            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: moodColor }}>{marketMood}</span>
                        </div>
                        <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', gap: 2 }}>
                            <div style={{ width: `${bullPct}%`, background: '#26a69a', borderRadius: 3 }} />
                            <div style={{ width: `${100 - bullPct - bearPct}%`, background: '#30363d' }} />
                            <div style={{ width: `${bearPct}%`, background: '#ef5350', borderRadius: 3 }} />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                            <span style={{ fontSize: '0.7rem', color: '#26a69a' }}>▲ {bullCount} bullish</span>
                            <span style={{ fontSize: '0.7rem', color: '#ef5350' }}>{bearCount} bearish ▼</span>
                        </div>
                    </div>
                )}

                {/* Category filter pills */}
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: '12px' }}>
                    {FILTERS.map(cat => {
                        const active = filter === cat;
                        const color = CATEGORY_COLORS[cat] || '#1f6feb';
                        return (
                            <button
                                key={cat}
                                onClick={() => setFilter(cat)}
                                style={{
                                    padding: '3px 10px',
                                    borderRadius: '12px',
                                    border: `1px solid ${active ? color : '#30363d'}`,
                                    background: active ? color + '22' : 'transparent',
                                    color: active ? color : '#8b949e',
                                    cursor: 'pointer',
                                    fontSize: '0.78rem',
                                    fontWeight: active ? 600 : 400,
                                }}
                            >
                                {cat} {counts[cat] > 0 ? `(${counts[cat]})` : ''}
                            </button>
                        );
                    })}
                </div>

                {/* News list -- clicking selects an item for the detail pane;
                    it no longer navigates away. Opening the real article is
                    now only the explicit button inside NewsDetail. */}
                <div style={{ flex: 1, overflowY: 'auto', marginTop: '8px' }}>
                    {loading ? (
                        <div style={{ textAlign: 'center', color: '#8b949e', padding: '3rem', fontSize: '0.9rem' }}>
                            Fetching latest news…
                        </div>
                    ) : filtered.length === 0 ? (
                        <div style={{ textAlign: 'center', color: '#8b949e', padding: '3rem' }}>No news available.</div>
                    ) : (
                        filtered.map((item, i) => {
                            const catColor = CATEGORY_COLORS[item.category] || '#1f6feb';
                            const active = selectedNews?.url === item.url;
                            return (
                                <div
                                    key={i}
                                    className={`news-row ${active ? 'active' : ''}`}
                                    onClick={() => setSelectedNews(item)}
                                >
                                    <div style={{ marginTop: 2, flexShrink: 0 }}>
                                        <SentimentIcon sentiment={item.sentiment} />
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ color: '#c9d1d9', fontSize: '0.875rem', lineHeight: 1.45, marginBottom: 5 }}>
                                            {item.title}
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                            <span style={{
                                                padding: '1px 6px',
                                                borderRadius: '4px',
                                                fontSize: '0.67rem',
                                                fontWeight: 600,
                                                background: catColor + '20',
                                                color: catColor,
                                                border: `1px solid ${catColor}40`,
                                            }}>
                                                {item.category}
                                            </span>
                                            {item.source && (
                                                <span style={{ color: '#8b949e', fontSize: '0.73rem' }}>{item.source}</span>
                                            )}
                                            {item.published_label && (
                                                <span style={{ color: '#6e7681', fontSize: '0.7rem' }}>{item.published_label}</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            <div className="news-detail-pane">
                <NewsDetail item={selectedNews} />
            </div>
        </div>
    );
};

export default NewsTab;
