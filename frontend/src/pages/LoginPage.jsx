import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
    const { login } = useAuth();
    const navigate = useNavigate();

    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username || !password) {
            setError('Please enter both username and password.');
            return;
        }
        setError('');
        setLoading(true);
        try {
            await login(username, password);
            navigate('/documents', { replace: true });
        } catch (err) {
            if (err.status === 401) {
                setError('Invalid credentials. Please try again.');
            } else if (err.message.includes('fetch')) {
                setError('Cannot connect to API server. Make sure it is running on port 8000.');
            } else {
                setError(err.message || 'Login failed. Please try again.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            {/* Background glow decoration */}
            <div className="login-bg-glow" />

            <div className="login-card">
                {/* Header */}
                <div className="login-header">
                    <div className="login-icon">📊</div>
                    <h1 className="login-title">FinSight AI</h1>
                    <p className="login-subtitle">Enterprise Financial RAG Platform</p>
                </div>

                {/* Error message */}
                {error && (
                    <div className="alert alert-error" style={{ marginBottom: '1.5rem' }}>
                        <span>⚠️</span>
                        <span>{error}</span>
                    </div>
                )}

                {/* Login form */}
                <form className="login-form" onSubmit={handleSubmit} id="login-form">
                    <div className="form-group">
                        <label htmlFor="username" className="form-label">Username</label>
                        <input
                            id="username"
                            type="text"
                            className="form-input"
                            placeholder="admin"
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            autoComplete="username"
                            autoFocus
                            disabled={loading}
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="password" className="form-label">Password</label>
                        <input
                            id="password"
                            type="password"
                            className="form-input"
                            placeholder="••••••••"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            autoComplete="current-password"
                            disabled={loading}
                        />
                    </div>

                    <button
                        type="submit"
                        id="login-submit-btn"
                        className="btn btn-primary btn-lg btn-full"
                        disabled={loading}
                    >
                        {loading ? (
                            <>
                                <div className="spinner" />
                                Signing in…
                            </>
                        ) : '🔐 Sign In'}
                    </button>
                </form>

                {/* Footer note */}
                <p style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>
                    Secured with AES-128 encryption · JWT auth · Immutable audit trail
                </p>
            </div>
        </div>
    );
}
