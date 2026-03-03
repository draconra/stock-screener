import { useState, useEffect } from 'react';
import { API_BASE } from '../config';
import { Stock, GroupedStocks } from '../types';

export function useStocks() {
    const [groupedStocks, setGroupedStocks] = useState<GroupedStocks>({});
    const [allStocks, setAllStocks] = useState<Stock[]>([]);
    const [loading, setLoading] = useState(true);
    const [lastUpdated, setLastUpdated] = useState<string>('');

    const fetchStocks = async () => {
        setLoading(true);
        const minDelay = new Promise(r => setTimeout(r, 800));
        try {
            const res    = await fetch(`${API_BASE}/api/candidates`);
            const result = await res.json();
            if (result.status === 'success') {
                setGroupedStocks(result.data);
                setAllStocks(Object.values(result.data as GroupedStocks).flat());
                setLastUpdated(new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
            }
        } catch (err) {
            console.error('Error fetching stocks:', err);
        }
        await minDelay;
        setLoading(false);
    };

    useEffect(() => {
        fetchStocks();
        const interval = setInterval(fetchStocks, 60_000);
        return () => clearInterval(interval);
    }, []);

    return { groupedStocks, allStocks, loading, lastUpdated, fetchStocks };
}
