import React, { type MouseEvent } from 'react';
import { Search, X, Star } from 'lucide-react';
import { Stock } from '../types';
import StockCard from './StockCard';

interface FavoritesTabProps {
    favoriteStocks: Stock[];
    selectedSymbol: string;
    favorites: string[];
    onSelect: (ticker: string) => void;
    onToggleFavorite: (stock: Stock, e: MouseEvent) => void;
    onRemoveFavorite: (ticker: string, e: MouseEvent) => void;
    searchQuery: string;
    setSearchQuery: (q: string) => void;
    searchResults: Stock[];
    searchLoading: boolean;
    clearSearch: () => void;
}

const FavoritesTab: React.FC<FavoritesTabProps> = ({
    favoriteStocks, selectedSymbol, favorites,
    onSelect, onToggleFavorite, onRemoveFavorite,
    searchQuery, setSearchQuery, searchResults, searchLoading, clearSearch,
}) => (
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
                    <button className="fav-btn" onClick={clearSearch}>
                        <X size={16} color="#8b949e" />
                    </button>
                )}
            </div>

            {(searchResults.length > 0 || searchLoading) && (
                <div className="search-results">
                    {searchLoading && (
                        <div className="search-result-item" style={{ color: '#8b949e' }}>Searching…</div>
                    )}
                    {searchResults.map((stock) => (
                        <div key={stock.ticker} className="search-result-item" onClick={() => onSelect(stock.ticker)}>
                            <div>
                                <span className="search-result-name">{stock.name}</span>
                                <span className="search-result-ticker">{stock.ticker}</span>
                            </div>
                            <button
                                className={`fav-btn add-fav-btn ${favorites.includes(stock.ticker) ? 'added' : ''}`}
                                onClick={(e) => { e.stopPropagation(); onToggleFavorite(stock, e); }}
                                title={favorites.includes(stock.ticker) ? 'Remove from favorites' : 'Add to favorites'}
                            >
                                <Star
                                    size={16}
                                    fill={favorites.includes(stock.ticker) ? '#f0b429' : 'none'}
                                    color={favorites.includes(stock.ticker) ? '#f0b429' : '#8b949e'}
                                />
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
                <div className="stock-grid">
                    {favoriteStocks.map(s => (
                        <StockCard
                            key={s.ticker}
                            stock={s}
                            selected={selectedSymbol === s.ticker}
                            isFavorited={favorites.includes(s.ticker)}
                            showRemove
                            onClick={() => onSelect(s.ticker)}
                            onToggleFavorite={onToggleFavorite}
                            onRemove={onRemoveFavorite}
                        />
                    ))}
                </div>
            </div>
        ) : (
            <div className="empty-state">
                No favorites yet. Search for a stock above or click ⭐ on any screener card.
            </div>
        )}
    </>
);

export default FavoritesTab;
