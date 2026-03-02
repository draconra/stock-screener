import React, { useState, useEffect, useRef } from 'react';
import { BarChart2, RefreshCw, Star, Search, X } from 'lucide-react';
import TVChart from './components/TVChart';
import ForecastCard from './components/ForecastCard';

interface Stock {
    ticker: string;
    name: string;
    close: number;
    change: number;
    volume: number;
    relative_volume_10d_calc: number;
    RSI: number;
    signal: string;
    sector: string;
}

interface GroupedStocks {
    [key: string]: Stock[];
}

type TabType = 'screener' | 'favorites';

function App() {
    const [groupedStocks, setGroupedStocks] = useState<GroupedStocks>({});
    const [allStocks, setAllStocks] = useState<Stock[]>([]);
    const [selectedSymbol, setSelectedSymbol] = useState<string>('IDX:OILS');
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<TabType>('screener');

    // Favorites state (persisted in localStorage)
    const [favorites, setFavorites] = useState<string[]>(() => {
        const saved = localStorage.getItem('idx-favorites');
        return saved ? JSON.parse(saved) : [];
    });
    // A map from ticker -> Stock info for stocks added via search (not in screener)
    const [customStocks, setCustomStocks] = useState<Record<string, Stock>>(() => {
        const saved = localStorage.getItem('idx-custom-stocks');
        return saved ? JSON.parse(saved) : {};
    });

    // Search state
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<Stock[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        localStorage.setItem('idx-favorites', JSON.stringify(favorites));
    }, [favorites]);

    useEffect(() => {
        localStorage.setItem('idx-custom-stocks', JSON.stringify(customStocks));
    }, [customStocks]);

    const toggleFavorite = (stock: Stock, e?: React.MouseEvent) => {
        e?.stopPropagation();
        const ticker = stock.ticker;
        setFavorites((prev) => {
            if (prev.includes(ticker)) {
                return prev.filter((t) => t !== ticker);
            }
            // Store stock data if it came from search (may not be in screener)
            setCustomStocks((cs) => ({ ...cs, [ticker]: stock }));
            return [...prev, ticker];
        });
    };

    const removeFavorite = (ticker: string, e?: React.MouseEvent) => {
        e?.stopPropagation();
        setFavorites((prev) => prev.filter((t) => t !== ticker));
    };

    const fetchStocks = async () => {
        setLoading(true);
        try {
            const response = await fetch('http://localhost:8000/api/candidates');
            const result = await response.json();
            if (result.status === 'success') {
                setGroupedStocks(result.data);
                const flat: Stock[] = Object.values(result.data as GroupedStocks).flat();
                setAllStocks(flat);
            }
        } catch (error) {
            console.error('Error fetching stocks:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchStocks();
        const interval = setInterval(fetchStocks, 60000);
        return () => clearInterval(interval);
    }, []);

    // Debounced search
    useEffect(() => {
        if (searchTimeout.current) clearTimeout(searchTimeout.current);
        if (searchQuery.trim().length < 2) {
            setSearchResults([]);
            return;
        }
        searchTimeout.current = setTimeout(async () => {
            setSearchLoading(true);
            try {
                const res = await fetch(`http://localhost:8000/api/search?q=${encodeURIComponent(searchQuery)}`);
                const result = await res.json();
                if (result.status === 'success') setSearchResults(result.data);
            } catch (err) {
                console.error('Search error:', err);
            }
            setSearchLoading(false);
        }, 350);
    }, [searchQuery]);

    // Build favorites stock list: use screener data if available, fallback to customStocks
    const screenerMap = Object.fromEntries(allStocks.map((s) => [s.ticker, s]));
    const favoriteStocks = favorites
        .map((t) => screenerMap[t] || customStocks[t])
        .filter(Boolean) as Stock[];

    const renderCard = (stock: Stock, showRemove = false) => (
        <div
            key={stock.ticker}
            className={`stock-card ${selectedSymbol === stock.ticker ? 'active' : ''}`}
            onClick={() => setSelectedSymbol(stock.ticker)}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <span style={{ fontWeight: 'bold' }}>{stock.name}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span className={stock.change >= 0 ? 'price-up' : 'price-down'} style={{ fontSize: '0.9rem' }}>
                        {stock.change?.toFixed(2)}%
                    </span>
                    {showRemove ? (
                        <button className="fav-btn" onClick={(e) => removeFavorite(stock.ticker, e)} title="Remove from favorites">
                            <X size={16} color="#f85149" />
                        </button>
                    ) : (
                        <button className="fav-btn" onClick={(e) => toggleFavorite(stock, e)} title={favorites.includes(stock.ticker) ? 'Remove from favorites' : 'Add to favorites'}>
                            <Star size={16} fill={favorites.includes(stock.ticker) ? '#f0b429' : 'none'} color={favorites.includes(stock.ticker) ? '#f0b429' : '#8b949e'} />
                        </button>
                    )}
                </div>
            </div>
            <div style={{ fontSize: '0.85rem', color: '#8b949e', marginTop: '6px' }}>Price: {stock.close}</div>
            <div style={{ fontSize: '0.85rem', color: '#8b949e' }}>RVOL: {stock.relative_volume_10d_calc?.toFixed(1)}x</div>
            <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className={`signal-badge ${stock.signal === 'STRONG BUY' ? 'signal-strong-buy' : stock.signal === 'WATCH' ? 'signal-watch' : 'signal-buy'}`}>
                    {stock.signal}
                </span>
                <span style={{ color: '#8b949e', fontSize: '0.75rem' }}>RSI: {Math.round(stock.RSI || 0)}</span>
            </div>
        </div>
    );

    return (
        <div className="dashboard-container">
            <div className="top-bar">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <BarChart2 size={24} color="#1f6feb" />
                    <h1 style={{ margin: 0, fontSize: '1.4rem' }}>IDX Scalper Grid</h1>
                </div>
                <div className="tab-bar">
                    <button className={`tab-btn ${activeTab === 'screener' ? 'tab-active' : ''}`} onClick={() => setActiveTab('screener')}>
                        Screener
                    </button>
                    <button className={`tab-btn ${activeTab === 'favorites' ? 'tab-active' : ''}`} onClick={() => setActiveTab('favorites')}>
                        <Star size={14} fill={activeTab === 'favorites' ? '#f0b429' : 'none'} color={activeTab === 'favorites' ? '#f0b429' : '#8b949e'} />
                        Favorites ({favorites.length})
                    </button>
                </div>
                <button onClick={fetchStocks} disabled={loading} style={{ background: '#21262d', border: '1px solid #30363d', color: 'white', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    Refresh
                </button>
            </div>

            <div className="main-content">
                <div className="grid-view">
                    {/* ── SCREENER TAB ── */}
                    {activeTab === 'screener' && (
                        <>
                            {Object.entries(groupedStocks).map(([sector, stocks]) => (
                                <div key={sector} className="sector-section">
                                    <div className="sector-title">{sector || 'Other'}</div>
                                    <div className="stock-grid">{stocks.map((s) => renderCard(s))}</div>
                                </div>
                            ))}
                            {Object.keys(groupedStocks).length === 0 && !loading && (
                                <div className="empty-state">No candidates found matching criteria.</div>
                            )}
                        </>
                    )}

                    {/* ── FAVORITES TAB ── */}
                    {activeTab === 'favorites' && (
                        <>
                            {/* Search box */}
                            <div className="search-section">
                                <div className="search-box">
                                    <Search size={16} color="#8b949e" />
                                    <input
                                        className="search-input"
                                        type="text"
                                        placeholder="Search IDX stocks to add… (e.g. BBCA)"
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                    />
                                    {searchQuery && (
                                        <button className="fav-btn" onClick={() => { setSearchQuery(''); setSearchResults([]); }}>
                                            <X size={16} color="#8b949e" />
                                        </button>
                                    )}
                                </div>

                                {/* Search results dropdown */}
                                {(searchResults.length > 0 || searchLoading) && (
                                    <div className="search-results">
                                        {searchLoading && <div className="search-result-item" style={{ color: '#8b949e' }}>Searching…</div>}
                                        {searchResults.map((stock) => (
                                            <div key={stock.ticker} className="search-result-item" onClick={() => setSelectedSymbol(stock.ticker)}>
                                                <div>
                                                    <span className="search-result-name">{stock.name}</span>
                                                    <span className="search-result-ticker">{stock.ticker}</span>
                                                </div>
                                                <button
                                                    className={`fav-btn add-fav-btn ${favorites.includes(stock.ticker) ? 'added' : ''}`}
                                                    onClick={(e) => { e.stopPropagation(); toggleFavorite(stock, e); }}
                                                    title={favorites.includes(stock.ticker) ? 'Remove from favorites' : 'Add to favorites'}
                                                >
                                                    <Star size={16} fill={favorites.includes(stock.ticker) ? '#f0b429' : 'none'} color={favorites.includes(stock.ticker) ? '#f0b429' : '#8b949e'} />
                                                    {favorites.includes(stock.ticker) ? 'Added' : '+ Favorite'}
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Favorites grid */}
                            {favoriteStocks.length > 0 ? (
                                <div className="sector-section">
                                    <div className="sector-title">⭐ My Favorites</div>
                                    <div className="stock-grid">{favoriteStocks.map((s) => renderCard(s, true))}</div>
                                </div>
                            ) : (
                                <div className="empty-state">
                                    No favorites yet. Search for a stock above or click ⭐ on any screener card.
                                </div>
                            )}
                        </>
                    )}
                </div>

                <div className="chart-panel">
                    <ForecastCard symbol={selectedSymbol} />
                    <TVChart symbol={selectedSymbol} />
                </div>
            </div>
        </div>
    );
}

export default App;
