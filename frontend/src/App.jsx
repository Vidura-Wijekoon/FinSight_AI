import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import LoginPage from './pages/LoginPage';
import DocumentsPage from './pages/DocumentsPage';
import QueryPage from './pages/QueryPage';
import AdminPage from './pages/AdminPage';

// ── Loading Splash ────────────────────────────────────────────────────────────
function LoadingSplash() {
    return (
        <div className="loading-center" style={{ minHeight: '100vh' }}>
            <div className="spinner spinner-lg" />
            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                Loading FinSight AI…
            </span>
        </div>
    );
}

// ── Authenticated App Shell (sidebar + routes) ────────────────────────────────
function AppShell() {
    const { user } = useAuth();
    return (
        <div className="app-shell">
            <Sidebar />
            <main className="main-content">
                <Routes>
                    <Route path="/" element={<Navigate to="/documents" replace />} />
                    <Route path="/documents" element={<DocumentsPage />} />
                    <Route path="/query" element={<QueryPage />} />
                    <Route
                        path="/admin"
                        element={
                            user?.role === 'admin'
                                ? <AdminPage />
                                : <Navigate to="/documents" replace />
                        }
                    />
                    <Route path="*" element={<Navigate to="/documents" replace />} />
                </Routes>
            </main>
        </div>
    );
}

// ── Route Guard ───────────────────────────────────────────────────────────────
function AppRouter() {
    const { isAuthenticated, loading } = useAuth();

    if (loading) return <LoadingSplash />;

    return (
        <Routes>
            {/* Public: login page */}
            <Route
                path="/login"
                element={
                    isAuthenticated
                        ? <Navigate to="/documents" replace />
                        : <LoginPage />
                }
            />

            {/* Protected: everything else */}
            <Route
                path="/*"
                element={
                    isAuthenticated
                        ? <AppShell />
                        : <Navigate to="/login" replace />
                }
            />
        </Routes>
    );
}

// ── Root Export ───────────────────────────────────────────────────────────────
export default function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <AppRouter />
            </BrowserRouter>
        </AuthProvider>
    );
}
