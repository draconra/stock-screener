import React from 'react';
import { FundamentalStock } from '../types';
import CriteriaTable from './CriteriaTable';

const VERDICT_LABEL: Record<string, string> = {
    STRONG: 'Kuat', GOOD: 'Baik', FAIR: 'Cukup', WEAK: 'Lemah', DATA_KURANG: 'Data Kurang',
};

// Explainability level 2-3 from the plan: the full criteria breakdown plus
// dividend detail and (for banks) the honest list of metrics yfinance simply
// cannot provide. Intentionally does NOT import ForecastCard or anything
// from calibration.py -- no price targets, no buy/sell ranges here.
const FundamentalDetail: React.FC<{ stock: FundamentalStock | null }> = ({ stock }) => {
    if (!stock) {
        return <div className="empty-state">Pilih saham di kiri untuk lihat rincian.</div>;
    }

    const d = stock.dividend;

    return (
        <div className="fund-detail">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div>
                    <div style={{ fontWeight: 'bold', fontSize: '1.1rem' }}>{stock.ticker}</div>
                    <div style={{ fontSize: '0.78rem', color: '#8b949e' }}>{stock.name} · {stock.sector}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div className="fund-score" style={{ fontSize: '1.4rem' }}>{stock.score.toFixed(0)}</div>
                    <div style={{ fontSize: '0.7rem', color: '#8b949e' }}>{VERDICT_LABEL[stock.verdict]}</div>
                </div>
            </div>

            {!stock.gates_passed && (
                <div style={{ marginTop: '10px', padding: '8px', background: '#3d0f0f', border: '1px solid #5a1a1a', borderRadius: '6px', fontSize: '0.78rem', color: '#f85149' }}>
                    Tidak lolos syarat: {stock.failed_gates.join(', ')}
                </div>
            )}

            <div style={{ marginTop: '14px' }}>
                <div className="detail-section-title">Dividen</div>
                <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', fontSize: '0.8rem' }}>
                    <span>Yield: {d.yield_pct ?? '—'}%</span>
                    <span>Payout: {d.payout_pct ?? '—'}% ({d.payout_band})</span>
                    <span>Beruntun: {d.streak_years} th</span>
                    <span>Terakhir: {d.last_payment ?? '—'}</span>
                </div>
            </div>

            {stock.bank_metrics && (
                <div style={{ marginTop: '14px' }}>
                    <div className="detail-section-title">Metrik Bank</div>
                    <div style={{ fontSize: '0.8rem', display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
                        <span>ROA: {stock.bank_metrics.roa_pct ?? '—'}%</span>
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#6e7681', marginTop: '6px' }}>
                        Tidak tersedia dari sumber data ini: {stock.bank_metrics.unavailable.join(', ')}.{' '}
                        {stock.bank_metrics.note}
                    </div>
                </div>
            )}

            {stock.penalties.length > 0 && (
                <div style={{ marginTop: '14px' }}>
                    <div className="detail-section-title">Penalti</div>
                    {stock.penalties.map((p, i) => (
                        <div key={i} style={{ fontSize: '0.78rem', color: '#f85149' }}>{p.label}: {p.points}</div>
                    ))}
                </div>
            )}

            <div style={{ marginTop: '14px' }}>
                <div className="detail-section-title">Rincian kriteria</div>
                <CriteriaTable criteria={stock.criteria} />
            </div>
        </div>
    );
};

export default FundamentalDetail;
