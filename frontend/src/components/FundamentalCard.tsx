import React from 'react';
import { FundamentalStock } from '../types';

const VERDICT_CLASS: Record<string, string> = {
    STRONG: 'verdict-strong',
    GOOD: 'verdict-good',
    FAIR: 'verdict-fair',
    WEAK: 'verdict-weak',
    DATA_KURANG: 'verdict-insufficient',
};

const VERDICT_LABEL: Record<string, string> = {
    STRONG: 'Kuat',
    GOOD: 'Baik',
    FAIR: 'Cukup',
    WEAK: 'Lemah',
    DATA_KURANG: 'Data Kurang',
};

const fmtNum = (v: number | null, digits = 1) => (v === null || v === undefined ? '—' : v.toFixed(digits));

interface Props {
    stock: FundamentalStock;
    selected: boolean;
    onClick: () => void;
}

// Layout order is deliberate (see plan): verdict+score is the largest
// element, ratios come next, and if a bank-only caveat exists it's the last
// muted line -- nothing here resembles the scalper's buy/sell price ranges.
const FundamentalCard: React.FC<Props> = ({ stock, selected, onClick }) => (
    <div
        className={`fund-card ${VERDICT_CLASS[stock.verdict]} ${selected ? 'active' : ''}`}
        onClick={onClick}
    >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
                <div style={{ fontWeight: 'bold', fontSize: '1rem' }}>{stock.ticker}</div>
                <div style={{ fontSize: '0.72rem', color: '#8b949e' }}>{stock.name}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
                <div className="fund-score">{stock.score.toFixed(0)}</div>
                <div style={{ fontSize: '0.68rem', color: '#8b949e' }}>{VERDICT_LABEL[stock.verdict]}</div>
            </div>
        </div>

        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {stock.pillars.map(p => (
                <div key={p.name} className="pillar-row">
                    <span style={{ width: 70, textTransform: 'capitalize' }}>{p.name}</span>
                    <div className="pillar-bar-bg">
                        <div
                            className="pillar-bar-fill"
                            style={{ width: `${Math.min(100, p.pct)}%`, background: p.pct >= 60 ? '#3fb950' : p.pct >= 35 ? '#f0b429' : '#f85149' }}
                        />
                    </div>
                </div>
            ))}
        </div>

        <div style={{ marginTop: '10px', display: 'flex', gap: '10px', flexWrap: 'wrap', fontSize: '0.78rem', color: '#e6edf3' }}>
            <span>PER {fmtNum(stock.per)}</span>
            <span>PBV {fmtNum(stock.pbv, 2)}</span>
            <span>ROE {fmtNum(stock.roe_pct)}%</span>
            <span>Yield {fmtNum(stock.dividend.yield_pct)}%</span>
        </div>

        <div style={{ marginTop: '8px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {stock.is_syariah && <span className="signal-badge signal-syariah">Syariah</span>}
            {stock.profile === 'BANK' && (
                <span className="signal-badge" style={{ background: '#21262d', color: '#8b949e', border: '1px solid #30363d' }}>
                    Bank
                </span>
            )}
            {stock.data_quality < 0.7 && (
                <span className="signal-badge" style={{ background: '#3d2b0a', color: '#f0b429', border: '1px solid #5a3d10' }} title="Sebagian kriteria tidak bisa dihitung karena data tidak lengkap">
                    Data {Math.round(stock.data_quality * 100)}%
                </span>
            )}
        </div>
    </div>
);

export default FundamentalCard;
