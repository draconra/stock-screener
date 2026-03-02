import React, { useState } from 'react';
import { BarChart2, RefreshCw, Star, Newspaper } from 'lucide-react';
import { useStocks } from './hooks/useStocks';
import { useFavorites } from './hooks/useFavorites';
import { useSearch } from './hooks/useSearch';
import ScreenerTab from './components/ScreenerTab';
import FavoritesTab from './components/FavoritesTab';
import NewsTab from './components/NewsTab';
import TVChart from './components/TVChart';
import ForecastCard from './components/ForecastCard';

type TabType = 'screener' | 'favorites' | 'news';

function App() {
    const [selectedSymbol, setSelectedSymbol] = useState('IDX:OILS');
    const [activeTab, setActiveTab]           = useState<TabType>('screener');

    const { groupedStocks, allStocks, loading, fetchStocks } = useStocks();
    const { favorites, favoriteStocks, toggleFavorite, removeFavorite } = useFavorites(allStocks);
    const { searchQuery, setSearchQuery, searchResults, searchLoading, clearSearch } = useSearch();

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
                    <button className={`tab-btn ${activeTab === 'news' ? 'tab-active' : ''}`} onClick={() => setActiveTab('news')}>
                        <Newspaper size={14} />
                        News
                    </button>
                </div>

                <button onClick={fetchStocks} disabled={loading} style={{ background: '#21262d', border: '1px solid #30363d', color: 'white', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    Refresh
                </button>
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
