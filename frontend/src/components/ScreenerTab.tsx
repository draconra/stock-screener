import React, { type MouseEvent } from 'react';
import { GroupedStocks, Stock } from '../types';
import StockCard from './StockCard';

interface ScreenerTabProps {
    groupedStocks: GroupedStocks;
    loading: boolean;
    selectedSymbol: string;
    favorites: string[];
    onSelect: (ticker: string) => void;
    onToggleFavorite: (stock: Stock, e: MouseEvent) => void;
}

const ScreenerTab: React.FC<ScreenerTabProps> = ({
    groupedStocks, loading, selectedSymbol, favorites, onSelect, onToggleFavorite,
}) => (
    <>
        {Object.entries(groupedStocks).map(([sector, stocks]) => (
            <div key={sector} className="sector-section">
                <div className="sector-title">{sector || 'Other'}</div>
                <div className="stock-grid">
                    {stocks.map(s => (
                        <StockCard
                            key={s.ticker}
                            stock={s}
                            selected={selectedSymbol === s.ticker}
                            isFavorited={favorites.includes(s.ticker)}
                            onClick={() => onSelect(s.ticker)}
                            onToggleFavorite={onToggleFavorite}
                        />
                    ))}
                </div>
            </div>
        ))}
        {Object.keys(groupedStocks).length === 0 && !loading && (
            <div className="empty-state">No candidates found matching criteria.</div>
        )}
    </>
);

export default ScreenerTab;
