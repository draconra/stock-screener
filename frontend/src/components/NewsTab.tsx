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

const FILTERS = ['All', 'IHSG', 'IDX', 'Global', 'Commodity'];

const NewsTab: React.FC = () => {
    const [news, setNews] = useState<NewsItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('All');
    const [lastUpdated, setLastUpdated] = useState('');

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

    // Sentiment summary for current filter
    const bullCount = filtered.filter(n => n.sentiment === 'bullish').length;
    const bearCount = filtered.filter(n => n.sentiment === 'bearish').length;
    const total = filtered.length || 1;
    const bullPct = Math.round((bullCount / total) * 100);
    const bearPct = Math.round((bearCount / total) * 100);
    const marketMood = bullPct > bearPct + 10 ? 'Bullish' : bearPct > bullPct + 10 ? 'Bearish' : 'Mixed';
    const moodColor = marketMood === 'Bullish' ? '#26a69a' : marketMood === 'Bearish' ? '#ef5350' : '#f0b429';

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '12px' }}>
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
                <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px', padding: '10px 14px' }}>
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
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
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

            {/* News list */}
            <div style={{ flex: 1, overflowY: 'auto' }}>
                {loading ? (
                    <div style={{ textAlign: 'center', color: '#8b949e', padding: '3rem', fontSize: '0.9rem' }}>
                        Fetching latest news…
                    </div>
                ) : filtered.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#8b949e', padding: '3rem' }}>No news available.</div>
                ) : (
                    filtered.map((item, i) => {
                        const catColor = CATEGORY_COLORS[item.category] || '#1f6feb';
                        return (
                            <a
                                key={i}
                                href={item.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ textDecoration: 'none', display: 'block' }}
                            >
                                <div
                                    style={{ padding: '10px 6px', borderBottom: '1px solid #21262d', display: 'flex', gap: 10, alignItems: 'flex-start', borderRadius: 4, transition: 'background 0.15s' }}
                                    onMouseEnter={e => (e.currentTarget.style.background = '#161b22')}
                                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
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
                                    <ExternalLink size={11} color="#6e7681" style={{ flexShrink: 0, marginTop: 3 }} />
                                </div>
                            </a>
                        );
                    })
                )}
            </div>
        </div>
    );
};

export default NewsTab;
