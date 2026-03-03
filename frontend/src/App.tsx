import React, { useState } from 'react';
import { BarChart2, RefreshCw, Star, Newspaper, BookOpen, LogOut } from 'lucide-react';
import { useStocks } from './hooks/useStocks';
import { useIHSG } from './hooks/useIHSG';
import { useFavorites } from './hooks/useFavorites';
import { useSearch } from './hooks/useSearch';
import { useAuth } from './hooks/useAuth';
import ScreenerTab from './components/ScreenerTab';
import FavoritesTab from './components/FavoritesTab';
import NewsTab from './components/NewsTab';
import GlossaryTab from './components/GlossaryTab';
import TVChart from './components/TVChart';
import ForecastCard from './components/ForecastCard';
import LoginPage from './components/LoginPage';

type TabType = 'screener' | 'favorites' | 'news' | 'glossary';

function App() {
    const { isAuthenticated, login, logout } = useAuth();
    const [selectedSymbol, setSelectedSymbol] = useState('IDX:OILS');
    const [activeTab, setActiveTab] = useState<TabType>('screener');

    const { groupedStocks, allStocks, loading, lastUpdated, fetchStocks } = useStocks();
    const { data: ihsg } = useIHSG();
    const { favorites, favoriteStocks, toggleFavorite, removeFavorite } = useFavorites(allStocks);
    const { searchQuery, setSearchQuery, searchResults, searchLoading, clearSearch } = useSearch();

    if (!isAuthenticated) {
        return <LoginPage onLogin={login} />;
    }

    return (
        <div className="dashboard-container">
            <div className="top-bar">
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <BarChart2 size={24} color="#1f6feb" />
                        <h1 style={{ margin: 0, fontSize: '1.4rem' }}>IDX Scalper Grid</h1>
                    </div>
                    {ihsg && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', padding: '4px 10px', background: '#161b22', borderRadius: '6px', border: '1px solid #30363d' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <span style={{
                                    width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                                    background: ihsg.market_status === 'open' ? '#3fb950' : ihsg.market_status === 'pre-market' ? '#f0b429' : '#f85149',
                                }} title={ihsg.market_status} />
                                <span style={{ fontSize: '0.7rem', color: '#8b949e', fontWeight: 'bold' }}>IHSG</span>
                                <span style={{ fontSize: '0.95rem', fontWeight: 'bold', color: '#e6edf3' }}>
                                    {ihsg.price.toLocaleString('id-ID', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                                <span style={{ fontSize: '0.78rem', color: ihsg.change_pct >= 0 ? '#3fb950' : '#f85149' }}>
                                    {ihsg.change_pct >= 0 ? '+' : ''}{ihsg.change_pct.toFixed(2)}%
                                </span>
                                {ihsg.market_time > 0 && (
                                    <span style={{ fontSize: '0.65rem', color: '#6e7681' }} title={`Data as of ${new Date(ihsg.market_time * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}`}>
                                        {new Date(ihsg.market_time * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}
                                        {ihsg.delayed_by > 0 && <span style={{ color: '#f0b429' }}> +{ihsg.delayed_by}m</span>}
                                    </span>
                                )}
                            </div>
                            <div style={{ display: 'flex', gap: '8px', fontSize: '0.65rem', color: '#6e7681' }}>
                                <span>H: {ihsg.day_high.toLocaleString('id-ID', { maximumFractionDigits: 0 })}</span>
                                <span>L: {ihsg.day_low.toLocaleString('id-ID', { maximumFractionDigits: 0 })}</span>
                            </div>
                        </div>
                    )}
                </div>

                <div className="tab-bar">
                    <button className={`tab-btn ${activeTab === 'screener' ? 'tab-active' : ''}`} onClick={() => setActiveTab('screener')}>
                        Screener
                    </button>
                    <button className={`tab-btn ${activeTab === 'favorites' ? 'tab-active' : ''}`} onClick={() => setActiveTab('favorites')}>
                        <Star size={14} fill={activeTab === 'favorites' ? '#f0b429' : 'none'} color={activeTab === 'favorites' ? '#f0b429' : '#8b949e'} />
                        Favorites ({favorites.length})
                    </button>
                    <button className={`tab-btn ${activeTab === 'news' ? 'tab-active' : ''}`} onClick={() => setActiveTab('news')}>
                        <Newspaper size={14} />
                        News
                    </button>
                    <button className={`tab-btn ${activeTab === 'glossary' ? 'tab-active' : ''}`} onClick={() => setActiveTab('glossary')}>
                        <BookOpen size={14} />
                        Kamus
                    </button>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {lastUpdated && <span style={{ color: '#6e7681', fontSize: '0.75rem' }}>Updated {lastUpdated}</span>}
                    <button onClick={fetchStocks} disabled={loading} style={{ background: '#21262d', border: '1px solid #30363d', color: 'white', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className={loading ? 'animate-spin' : ''} style={{ display: 'inline-flex' }}>
                            <RefreshCw size={18} />
                        </span>
                        {loading ? 'Loading…' : 'Refresh'}
                    </button>
                    <button onClick={logout} title="Logout" style={{ background: '#21262d', border: '1px solid #30363d', color: '#8b949e', padding: '8px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'color 0.2s' }}>
                        <LogOut size={16} />
                    </button>
                </div>
            </div>

            <div className="main-content">
                <div className="grid-view">
                    {activeTab === 'screener' && (
                        <ScreenerTab
                            groupedStocks={groupedStocks}
                            loading={loading}
                            selectedSymbol={selectedSymbol}
                            favorites={favorites}
                            onSelect={setSelectedSymbol}
                            onToggleFavorite={toggleFavorite}
                        />
                    )}
                    {activeTab === 'favorites' && (
                        <FavoritesTab
                            favoriteStocks={favoriteStocks}
                            selectedSymbol={selectedSymbol}
                            favorites={favorites}
                            onSelect={setSelectedSymbol}
                            onToggleFavorite={toggleFavorite}
                            onRemoveFavorite={removeFavorite}
                            searchQuery={searchQuery}
                            setSearchQuery={setSearchQuery}
                            searchResults={searchResults}
                            searchLoading={searchLoading}
                            clearSearch={clearSearch}
                        />
                    )}
                    {activeTab === 'news' && <NewsTab />}
                    {activeTab === 'glossary' && <GlossaryTab />}
                </div>

                {(activeTab === 'screener' || activeTab === 'favorites') && (
                    <div className="chart-panel">
                        <ForecastCard symbol={selectedSymbol} />
                        <TVChart symbol={selectedSymbol} />
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;
