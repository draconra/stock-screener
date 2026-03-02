import React, { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Minus, AlertCircle } from 'lucide-react';
import { API_BASE } from '../config';

interface Factor {
    label: string;
    bull: boolean;
}

interface ForecastData {
    direction: 'UP' | 'DOWN' | 'NEUTRAL';
    confidence: number;
    score: number;
    factors: Factor[];
    rsi: number;
    vol_ratio: number;
    bb_pct: number;
    stoch_k: number;
    ema_uptrend: boolean;
    pullback_days: number;
    last_close: number;
    last_date: string;
    symbol: string;
    atr: number;
}

interface ForecastCardProps {
    symbol: string;
}

const directionConfig = {
    UP: {
        icon: TrendingUp,
        color: '#26a69a',
        bg: 'rgba(38,166,154,0.12)',
        border: 'rgba(38,166,154,0.4)',
        label: 'Likely UP tomorrow',
    },
    DOWN: {
        icon: TrendingDown,
        color: '#ef5350',
        bg: 'rgba(239,83,80,0.12)',
        border: 'rgba(239,83,80,0.4)',
        label: 'Likely DOWN tomorrow',
    },
    NEUTRAL: {
        icon: Minus,
        color: '#8b949e',
        bg: 'rgba(139,148,158,0.1)',
        border: 'rgba(139,148,158,0.3)',
        label: 'Direction unclear',
    },
};

const ForecastCard: React.FC<ForecastCardProps> = ({ symbol }) => {
    const [forecast, setForecast] = useState<ForecastData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchForecast = async () => {
            if (!symbol) return;
            setLoading(true);
            setError('');
            setForecast(null);
            try {
                const res = await fetch(`${API_BASE}/api/forecast/${symbol}`);
                const result = await res.json();
                if (result.status === 'success') {
                    setForecast(result.data);
                } else {
                    setError(result.detail || 'Error fetching forecast');
                }
            } catch (e) {
                setError('Could not connect to backend');
            }
            setLoading(false);
        };
        fetchForecast();
    }, [symbol]);

    if (loading) {
        return (
            <div className="forecast-card" style={{ justifyContent: 'center', alignItems: 'center', display: 'flex' }}>
                <span style={{ color: '#8b949e', fontSize: '0.85rem' }}>Analysing {symbol}…</span>
            </div>
        );
    }

    if (error || !forecast) {
        return (
            <div className="forecast-card" style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#8b949e' }}>
                <AlertCircle size={16} />
                <span style={{ fontSize: '0.8rem' }}>{error || 'No data'}</span>
            </div>
        );
    }

    const cfg = directionConfig[forecast.direction];
    const Icon = cfg.icon;

    return (
        <div className="forecast-card" style={{ borderColor: cfg.border, background: cfg.bg }}>
            {/* Header */}
            <div className="forecast-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Icon size={20} color={cfg.color} />
                    <div>
                        <div style={{ fontWeight: 700, color: cfg.color, fontSize: '0.95rem' }}>
                            {cfg.label}
                        </div>
                        <div style={{ color: '#8b949e', fontSize: '0.75rem' }}>
                            {symbol} · last close {forecast.last_close?.toLocaleString()} · {forecast.last_date}
                        </div>
                    </div>
                </div>

                {/* Confidence gauge */}
                <div style={{ textAlign: 'right', minWidth: 60 }}>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700, color: cfg.color, lineHeight: 1 }}>
                        {forecast.confidence}%
                    </div>
                    <div style={{ fontSize: '0.65rem', color: '#8b949e' }}>confidence</div>
                </div>
            </div>

            {/* Confidence bar */}
            <div className="forecast-bar-bg">
                <div
                    className="forecast-bar-fill"
                    style={{
                        width: `${forecast.confidence}%`,
                        background: cfg.color,
                    }}
                />
            </div>

            {/* Key metrics row */}
            <div className="forecast-metrics">
                {[
                    { label: 'RSI', value: forecast.rsi, warn: forecast.rsi > 65 || forecast.rsi < 30 },
                    { label: 'Stoch', value: Math.round(forecast.stoch_k), warn: forecast.stoch_k > 80 || forecast.stoch_k < 20 },
                    { label: 'Vol ×', value: forecast.vol_ratio, warn: false },
                    { label: 'BB %', value: (forecast.bb_pct * 100).toFixed(0) + '%', warn: forecast.bb_pct > 0.85 },
                    { label: 'ATR', value: forecast.atr?.toLocaleString(), warn: false },
                ].map((m) => (
                    <div key={m.label} className="forecast-metric">
                        <div style={{ color: '#8b949e', fontSize: '0.65rem' }}>{m.label}</div>
                        <div style={{ fontWeight: 600, fontSize: '0.85rem', color: m.warn ? '#f0b429' : 'white' }}>
                            {m.value}
                        </div>
                    </div>
                ))}
            </div>

            {/* Factor list */}
            <div className="forecast-factors">
                {forecast.factors.slice(0, 5).map((f, i) => (
                    <div key={i} className="forecast-factor">
                        <span style={{ color: f.bull ? '#26a69a' : '#ef5350', marginRight: 4 }}>
                            {f.bull ? '▲' : '▼'}
                        </span>
                        <span style={{ fontSize: '0.78rem', color: '#c9d1d9' }}>{f.label}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ForecastCard;
