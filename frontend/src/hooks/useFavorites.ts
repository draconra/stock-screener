import { useState, useEffect, type MouseEvent } from 'react';
import { Stock } from '../types';

export function useFavorites(allStocks: Stock[]) {
    const [favorites, setFavorites] = useState<string[]>(() => {
        const saved = localStorage.getItem('idx-favorites');
        return saved ? JSON.parse(saved) : [];
    });

    const [customStocks, setCustomStocks] = useState<Record<string, Stock>>(() => {
        const saved = localStorage.getItem('idx-custom-stocks');
        return saved ? JSON.parse(saved) : {};
    });

    useEffect(() => {
        localStorage.setItem('idx-favorites', JSON.stringify(favorites));
    }, [favorites]);

    useEffect(() => {
        localStorage.setItem('idx-custom-stocks', JSON.stringify(customStocks));
    }, [customStocks]);

    const screenerMap = Object.fromEntries(allStocks.map(s => [s.ticker, s]));
    const favoriteStocks = favorites
        .map(t => screenerMap[t] || customStocks[t])
        .filter(Boolean) as Stock[];

    const toggleFavorite = (stock: Stock, e?: MouseEvent) => {
        e?.stopPropagation();
        const { ticker } = stock;
        setFavorites(prev => {
            if (prev.includes(ticker)) return prev.filter(t => t !== ticker);
            setCustomStocks(cs => ({ ...cs, [ticker]: stock }));
            return [...prev, ticker];
        });
    };

    const removeFavorite = (ticker: string, e?: MouseEvent) => {
        e?.stopPropagation();
        setFavorites(prev => prev.filter(t => t !== ticker));
    };

    return { favorites, favoriteStocks, toggleFavorite, removeFavorite };
}
