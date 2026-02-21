/**
 * AuthContext — JWT auth state management.
 * Provides: user, token, login(), logout(), loading
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { login as apiLogin, getMe } from '../api/client';

const AuthContext = createContext(null);

const TOKEN_KEY = 'finsight_token';

export function AuthProvider({ children }) {
    const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
    const [user, setUser] = useState(null);       // { username, role, disabled }
    const [loading, setLoading] = useState(!!localStorage.getItem(TOKEN_KEY));

    // Restore session from localStorage on mount
    useEffect(() => {
        if (!token) { setLoading(false); return; }
        getMe()
            .then(setUser)
            .catch(() => {
                // Token invalid/expired — clear session
                localStorage.removeItem(TOKEN_KEY);
                setToken(null);
                setUser(null);
            })
            .finally(() => setLoading(false));
    }, [token]);

    /** Sign in — calls POST /auth/login then GET /auth/me */
    const login = useCallback(async (username, password) => {
        const { access_token } = await apiLogin(username, password);
        localStorage.setItem(TOKEN_KEY, access_token);
        setToken(access_token);
        const profile = await getMe();
        setUser(profile);
    }, []);

    /** Sign out — clears localStorage and state */
    const logout = useCallback(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setUser(null);
    }, []);

    return (
        <AuthContext.Provider value={{ user, token, login, logout, loading, isAuthenticated: !!user }}>
            {children}
        </AuthContext.Provider>
    );
}

/** Hook to consume AuthContext */
export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
    return ctx;
}
