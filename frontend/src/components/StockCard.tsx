import React, { type MouseEvent } from 'react';
import { Star, X } from 'lucide-react';
import { Stock } from '../types';

const fmt = (p: number) =>
    p > 0 ? p.toLocaleString('id-ID') : '—';

const fmtTime = (ts?: number) => {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleString('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

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
        {stock.update_time && (
            <div style={{ fontSize: '0.7rem', color: '#6e7681' }}>Last trade: {fmtTime(stock.update_time)}</div>
        )}
        <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span className={`signal-badge ${
                    stock.signal === 'STRONG BUY' ? 'signal-strong-buy' :
                    stock.signal === 'WATCH'      ? 'signal-watch' :
                    stock.signal === 'SCALP'      ? 'signal-scalp' :
                    stock.signal === 'REVERSAL'   ? 'signal-reversal' :
                    'signal-buy'
                }`}>
                    {stock.signal}
                </span>
                {stock.is_syariah && (
                    <span className="signal-badge signal-syariah">Syariah</span>
                )}
            </div>
            <span style={{ color: '#8b949e', fontSize: '0.75rem' }}>RSI: {Math.round(stock.RSI || 0)}</span>
        </div>

        {/* Price ranges */}
        {stock.buy_low > 0 && (
            <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                <div className="price-range-row price-range-buy">
                    <span className="price-range-label">Buy</span>
                    <span>{fmt(stock.buy_low)} – {fmt(stock.buy_high)}</span>
                </div>
                <div className="price-range-row price-range-sell">
                    <span className="price-range-label">Target</span>
                    <span>{fmt(stock.sell_low)} – {fmt(stock.sell_high)}</span>
                </div>
            </div>
        )}
    </div>
);

export default StockCard;
