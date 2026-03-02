import React, { type MouseEvent } from 'react';
import { Star, X } from 'lucide-react';
import { Stock } from '../types';

interface StockCardProps {
    stock: Stock;
    selected: boolean;
    isFavorited: boolean;
    showRemove?: boolean;
    onClick: () => void;
    onToggleFavorite: (stock: Stock, e: MouseEvent) => void;
    onRemove?: (ticker: string, e: MouseEvent) => void;
}

const StockCard: React.FC<StockCardProps> = ({
    stock, selected, isFavorited, showRemove = false,
    onClick, onToggleFavorite, onRemove,
}) => (
    <div className={`stock-card ${selected ? 'active' : ''}`} onClick={onClick}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
            <span style={{ fontWeight: 'bold' }}>{stock.name}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className={stock.change >= 0 ? 'price-up' : 'price-down'} style={{ fontSize: '0.9rem' }}>
                    {stock.change?.toFixed(2)}%
                </span>
                {showRemove ? (
                    <button className="fav-btn" onClick={(e) => onRemove?.(stock.ticker, e)} title="Remove from favorites">
                        <X size={16} color="#f85149" />
                    </button>
                ) : (
                    <button
                        className="fav-btn"
                        onClick={(e) => onToggleFavorite(stock, e)}
                        title={isFavorited ? 'Remove from favorites' : 'Add to favorites'}
                    >
                        <Star size={16} fill={isFavorited ? '#f0b429' : 'none'} color={isFavorited ? '#f0b429' : '#8b949e'} />
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

export default StockCard;
