import React, { useState, useRef, useEffect } from 'react';
import { BarChart2, Lock, Eye, EyeOff, ArrowRight, AlertCircle } from 'lucide-react';

interface LoginPageProps {
    onLogin: (password: string) => boolean;
}

export default function LoginPage({ onLogin }: LoginPageProps) {
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [isShaking, setIsShaking] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!password.trim()) {
            setError('Enter your access code');
            triggerShake();
            return;
        }
        setIsLoading(true);

        // Brief delay for visual feedback
        setTimeout(() => {
            const success = onLogin(password);
            if (!success) {
                setError('Invalid access code');
                setPassword('');
                setIsLoading(false);
                triggerShake();
                inputRef.current?.focus();
            }
        }, 400);
    };

    const triggerShake = () => {
        setIsShaking(true);
        setTimeout(() => setIsShaking(false), 500);
    };

    return (
        <div className="login-page">
            {/* Animated background grid */}
            <div className="login-grid-bg" />

            {/* Floating particles */}
            <div className="login-particles">
                {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="login-particle" style={{
                        left: `${15 + i * 14}%`,
                        animationDelay: `${i * 0.8}s`,
                        animationDuration: `${6 + i * 1.5}s`,
                    }} />
                ))}
            </div>

            <div className={`login-card ${isShaking ? 'login-shake' : ''}`}>
                {/* Logo / Brand */}
                <div className="login-brand">
                    <div className="login-logo">
                        <div className="login-logo-icon">
                            <BarChart2 size={28} strokeWidth={2.5} />
                        </div>
                    </div>
                    <h1 className="login-title">IDX Scalper</h1>
                    <p className="login-subtitle">
                        Real-time Indonesian Stock Exchange screener & trading signals
                    </p>
                </div>

                {/* Divider with pulse */}
                <div className="login-divider">
                    <div className="login-divider-line" />
                    <Lock size={14} className="login-divider-icon" />
                    <div className="login-divider-line" />
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="login-form">
                    <label className="login-label" htmlFor="access-code">
                        Access Code
                    </label>
                    <div className={`login-input-wrapper ${error ? 'login-input-error' : ''}`}>
                        <input
                            ref={inputRef}
                            id="access-code"
                            type={showPassword ? 'text' : 'password'}
                            value={password}
                            onChange={(e) => { setPassword(e.target.value); setError(''); }}
                            placeholder="Enter your access code"
                            className="login-input"
                            autoComplete="off"
                            spellCheck={false}
                            disabled={isLoading}
                        />
                        <button
                            type="button"
                            className="login-toggle-vis"
                            onClick={() => setShowPassword(v => !v)}
                            tabIndex={-1}
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                        >
                            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                    </div>

                    {error && (
                        <div className="login-error">
                            <AlertCircle size={13} />
                            <span>{error}</span>
                        </div>
                    )}

                    <button
                        type="submit"
                        className="login-submit"
                        disabled={isLoading}
                    >
                        {isLoading ? (
                            <span className="login-spinner" />
                        ) : (
                            <>
                                Access Dashboard
                                <ArrowRight size={16} />
                            </>
                        )}
                    </button>
                </form>

                {/* Market badges */}
                <div className="login-badges">
                    <span className="login-badge">🇮🇩 IDX Exchange</span>
                    <span className="login-badge">📊 4 Signal Types</span>
                    <span className="login-badge">🤖 AI Calibrated</span>
                </div>
            </div>

            {/* Footer */}
            <div className="login-footer">
                <span>IDX Scalper Grid &middot; Quantitative Stock Screener</span>
            </div>
        </div>
    );
}
