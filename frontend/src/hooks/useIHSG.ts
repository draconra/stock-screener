import { useState, useEffect } from 'react';
import { API_BASE } from '../config';

interface IHSGData {
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

export function useIHSG() {
    const [data, setData] = useState<IHSGData | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchIHSG = async () => {
        try {
            const res    = await fetch(`${API_BASE}/api/ihsg`);
            const result = await res.json();
            if (result.status === 'success') {
                setData(result.data);
            }
        } catch {
            // silently fail — IHSG widget is non-critical
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchIHSG();
        const interval = setInterval(fetchIHSG, 60_000);
        return () => clearInterval(interval);
    }, []);

    return { data, loading };
}
