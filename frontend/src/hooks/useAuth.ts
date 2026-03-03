import { useState, useCallback } from 'react';

const AUTH_STORAGE_KEY = 'idx_authenticated';
const AUTH_EXPIRY_KEY = 'idx_auth_expiry';

// Session duration: 24 hours
const SESSION_DURATION_MS = 24 * 60 * 60 * 1000;

/**
 * Checks if a valid auth session exists in localStorage.
 * Returns false if the session has expired.
 */
function isSessionValid(): boolean {
    try {
        const authed = localStorage.getItem(AUTH_STORAGE_KEY);
        const expiry = localStorage.getItem(AUTH_EXPIRY_KEY);
        if (authed !== 'true' || !expiry) return false;
        return Date.now() < Number(expiry);
    } catch {
        return false;
    }
}

/**
 * Hook that manages authentication state.
 * Uses localStorage to persist sessions across page reloads.
 */
export function useAuth() {
    const [isAuthenticated, setIsAuthenticated] = useState(isSessionValid);

    const login = useCallback((password: string): boolean => {
        // Simple passphrase check — not a security boundary,
        // just a casual gate to keep the dashboard private.
        const passphrase = import.meta.env.VITE_AUTH_PASSPHRASE || 'idxscalper2025';
        if (password === passphrase) {
            const expiry = Date.now() + SESSION_DURATION_MS;
            localStorage.setItem(AUTH_STORAGE_KEY, 'true');
            localStorage.setItem(AUTH_EXPIRY_KEY, String(expiry));
            setIsAuthenticated(true);
            return true;
        }
        return false;
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        localStorage.removeItem(AUTH_EXPIRY_KEY);
        setIsAuthenticated(false);
    }, []);

    return { isAuthenticated, login, logout };
}
