import React, { useState } from 'react';
import { FundamentalFilters } from '../hooks/useFundamentals';
import { FundamentalScreenResponse, FundamentalStock } from '../types';
import FundamentalCard from './FundamentalCard';

interface InvestTabProps {
    data: FundamentalScreenResponse | null;
    loading: boolean;
    error: string | null;
    filters: FundamentalFilters;
    setFilters: (f: FundamentalFilters) => void;
    selectedTicker: string | null;
    onSelect: (ticker: string) => void;
}

const STALE_AFTER_DAYS = 45;

function daysSince(dateStr: string | null): number | null {
    if (!dateStr) return null;
    const then = new Date(dateStr).getTime();
    return Math.floor((Date.now() - then) / 86_400_000);
}

// The freshness badge is the most important reliability feature in this tab
// (see plan): a stalled monthly refresh pipeline is invisible in an email
// inbox but impossible to miss here, every time you open the tab you
// actually use.
const FreshnessBadge: React.FC<{ asOf: string | null }> = ({ asOf }) => {
    const age = daysSince(asOf);
    const stale = age !== null && age > STALE_AFTER_DAYS;
    return (
        <span
            style={{
                fontSize: '0.72rem', padding: '3px 8px', borderRadius: '999px',
                background: stale ? '#3d2b0a' : '#0d2818',
                color: stale ? '#f0b429' : '#3fb950',
                border: `1px solid ${stale ? '#5a3d10' : '#1a4a2e'}`,
            }}
        >
            {asOf ? `Data per ${asOf}` : 'Belum ada data'}
            {stale && age !== null ? ` — ${age} hari lalu` : ''}
        </span>
    );
};

const InvestTab: React.FC<InvestTabProps> = ({ data, loading, error, filters, setFilters, selectedTicker, onSelect }) => {
    const [showFunnel, setShowFunnel] = useState(false);
    const [showRejected, setShowRejected] = useState(false);

    if (error) {
        return <div className="empty-state">{error}</div>;
    }
    if (loading && !data) {
        return <div className="empty-state">Memuat data fundamental…</div>;
    }
    if (!data) {
        return <div className="empty-state">Belum ada snapshot fundamental. Jalankan pipeline refresh dulu.</div>;
    }

    const sectors = Object.keys(data.groups).sort();
    const allSectors = Array.from(new Set([...sectors, ...(filters.sector ? [filters.sector] : [])]));

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '14px' }}>
                <FreshnessBadge asOf={data.as_of} />
                <span style={{ fontSize: '0.72rem', color: '#8b949e' }}>
                    {data.counts.passed}/{data.counts.evaluated} lolos syarat · config {data.config_version}
                </span>
                <button className="fund-filter-toggle" onClick={() => setShowFunnel(s => !s)}>
                    {showFunnel ? 'Sembunyikan' : 'Lihat'} corong screening
                </button>
                {data.failed.length > 0 && (
                    <button className="fund-filter-toggle" onClick={() => setShowRejected(s => !s)}>
                        {showRejected ? 'Sembunyikan' : 'Lihat'} yang gugur ({data.failed.length})
                    </button>
                )}
            </div>

            {showFunnel && (
                <div className="funnel-bar">
                    {data.funnel.map((f, i) => (
                        <span key={i} className="funnel-step">
                            {f.stage}: <strong>{f.remaining}</strong>
                            {i < data.funnel.length - 1 && <span className="funnel-arrow"> → </span>}
                        </span>
                    ))}
                </div>
            )}

            {showRejected && (
                <div className="rejected-list">
                    {data.failed.map(f => (
                        <div key={f.ticker} className="rejected-row">
                            <strong>{f.ticker}</strong> — {f.explain}
                        </div>
                    ))}
                </div>
            )}

            <div className="fund-filters">
                <label>
                    Skor min: {filters.minScore}
                    <input
                        type="range" min={0} max={100} value={filters.minScore}
                        onChange={e => setFilters({ ...filters, minScore: Number(e.target.value) })}
                    />
                </label>
                <label className="fund-checkbox">
                    <input
                        type="checkbox" checked={filters.syariahOnly}
                        onChange={e => setFilters({ ...filters, syariahOnly: e.target.checked })}
                    />
                    Syariah saja
                </label>
                <select value={filters.sector} onChange={e => setFilters({ ...filters, sector: e.target.value })}>
                    <option value="">Semua sektor</option>
                    {allSectors.map(s => (
                        <option key={s} value={s}>{s}</option>
                    ))}
                </select>
            </div>

            {Object.entries(data.groups).map(([sec, stocks]) => (
                <div key={sec} className="sector-section">
                    <div className="sector-title">{sec}</div>
                    <div className="stock-grid">
                        {(stocks as FundamentalStock[]).map(s => (
                            <FundamentalCard
                                key={s.ticker}
                                stock={s}
                                selected={selectedTicker === s.ticker}
                                onClick={() => onSelect(s.ticker)}
                            />
                        ))}
                    </div>
                </div>
            ))}
            {Object.keys(data.groups).length === 0 && (
                <div className="empty-state">Tidak ada saham yang lolos filter saat ini.</div>
            )}
        </div>
    );
};

export default InvestTab;
