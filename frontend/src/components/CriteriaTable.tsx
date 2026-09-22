import React from 'react';
import { Criterion } from '../types';

const STATUS_GLYPH: Record<string, string> = {
    pass: '✓',
    fail: '✗',
    warn: '!',
    skipped: '−',
    missing: '?',
};

// Explainability, level 2 from the plan: every criterion is one row here.
// "skipped" and "missing" are rendered distinctly from "fail" on purpose --
// a bank's D/E showing up as a bare 0 (like the old xlsx coerced it) is
// exactly the bug this table exists to make impossible to miss.
const CriteriaTable: React.FC<{ criteria: Criterion[] }> = ({ criteria }) => {
    const gates = criteria.filter(c => c.is_gate);
    const scored = criteria.filter(c => !c.is_gate);

    const row = (c: Criterion) => (
        <div key={c.id} className={`criteria-row ${c.is_gate ? 'is-gate' : ''}`}>
            <span className={`criteria-status-${c.status}`}>{STATUS_GLYPH[c.status] || '·'}</span>
            <span>{c.explain}</span>
            <span style={{ color: '#6e7681', fontSize: '0.7rem' }}>
                {c.max_points > 0 ? `${c.points.toFixed(1)}/${c.max_points.toFixed(0)}` : ''}
            </span>
        </div>
    );

    return (
        <div className="criteria-table">
            {gates.length > 0 && (
                <>
                    <div className="criteria-group-title">Syarat (gate)</div>
                    {gates.map(row)}
                </>
            )}
            {scored.length > 0 && (
                <>
                    <div className="criteria-group-title">Skor</div>
                    {scored.map(row)}
                </>
            )}
        </div>
    );
};

export default CriteriaTable;
