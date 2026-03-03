import { useState, useEffect } from 'react';
import { API_BASE } from '../config';

export interface QuoteData {
    ticker: string;
    price: number;
    change: number;
    change_pct: number;
    open: number;
    day_high: number;
    day_low: number;
    market_time: number;
    delayed_by: number;
    market_status: 'open' | 'pre-market' | 'closed';
}

export function useQuote(symbol: string) {
    const [data, setData] = useState<QuoteData | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!symbol) return;
        let cancelled = false;

        const fetch_ = async () => {
            setLoading(true);
            try {
                const ticker = symbol.split(':')[1] || symbol;
                const res    = await fetch(`${API_BASE}/api/quote/${ticker}`);
                const result = await res.json();
                if (!cancelled && result.status === 'success') {
                    setData(result.data);
                }
            } catch {
                // non-critical
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        fetch_();
        const interval = setInterval(fetch_, 30_000);
        return () => { cancelled = true; clearInterval(interval); };
    }, [symbol]);

    return { data, loading };
}
