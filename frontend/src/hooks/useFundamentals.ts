import { useState, useEffect } from 'react';
import { API_BASE } from '../config';
import { FundamentalScreenResponse } from '../types';

export interface FundamentalFilters {
    minScore: number;
    syariahOnly: boolean;
    sector: string;
}

// Deliberately NO setInterval / polling here, unlike useStocks.ts (which
// refreshes every 60s for the scalper). Fundamentals update quarterly at
// best -- refreshing on a timer would train exactly the wrong reflex for a
// multi-year holding decision. Data is re-fetched only on mount and when
// the filters change.
export function useFundamentals(filters: FundamentalFilters) {
    const [data, setData] = useState<FundamentalScreenResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchFundamentals = async () => {
        setLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams();
            if (filters.minScore > 0) params.set('min_score', String(filters.minScore));
            if (filters.syariahOnly) params.set('syariah_only', 'true');
            if (filters.sector) params.set('sector', filters.sector);

            const res = await fetch(`${API_BASE}/api/fundamental/screen?${params.toString()}`);
            const result = await res.json();
            if (result.status === 'success') {
                setData(result.data);
            } else {
                setError(result.message || 'Gagal memuat data fundamental');
            }
        } catch (err) {
            setError('Tidak bisa terhubung ke server');
            console.error('Error fetching fundamentals:', err);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchFundamentals();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters.minScore, filters.syariahOnly, filters.sector]);

    return { data, loading, error, refetch: fetchFundamentals };
}
