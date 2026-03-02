import { useState, useEffect, useRef } from 'react';
import { API_BASE } from '../config';
import { Stock } from '../types';

export function useSearch() {
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<Stock[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        if (timeout.current) clearTimeout(timeout.current);
        if (searchQuery.trim().length < 2) {
            setSearchResults([]);
            return;
        }
        timeout.current = setTimeout(async () => {
            setSearchLoading(true);
            try {
                const res    = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(searchQuery)}`);
                const result = await res.json();
                if (result.status === 'success') setSearchResults(result.data);
            } catch (err) {
                console.error('Search error:', err);
            }
            setSearchLoading(false);
        }, 350);
    }, [searchQuery]);

    const clearSearch = () => {
        setSearchQuery('');
        setSearchResults([]);
    };

    return { searchQuery, setSearchQuery, searchResults, searchLoading, clearSearch };
}
