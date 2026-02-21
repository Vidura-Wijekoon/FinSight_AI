import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const NAV_ITEMS = [
    { to: '/documents', icon: '📄', label: 'Documents' },
    { to: '/query', icon: '💬', label: 'Query' },
];

const ADMIN_NAV = { to: '/admin', icon: '⚙️', label: 'Admin' };

export default function Sidebar() {
    const { user, logout, isAuthenticated } = useAuth();
    const navigate = useNavigate();

    if (!isAuthenticated) return null;

    const handleLogout = () => {
        logout();
        navigate('/login', { replace: true });
    };

    const navItems = user?.role === 'admin'
        ? [...NAV_ITEMS, ADMIN_NAV]
        : NAV_ITEMS;

    return (
        <aside className="sidebar">
            {/* Logo */}
            <div className="sidebar-logo">
                <div className="sidebar-logo-icon">📊</div>
                <div className="sidebar-logo-title">FinSight AI</div>
                <div className="sidebar-logo-subtitle">Enterprise RAG Platform</div>
            </div>

            <hr className="sidebar-divider" />

            {/* User info */}
            <div className="sidebar-user">
                <div className="sidebar-username">
                    <span>👤</span>
                    <span>{user?.username}</span>
                </div>
                <span className={`role-badge ${user?.role ?? 'viewer'}`}>
                    ● {user?.role?.toUpperCase()}
                </span>
            </div>

            <hr className="sidebar-divider" />

            {/* Navigation */}
            <nav className="sidebar-nav">
                {navItems.map(({ to, icon, label }) => (
                    <NavLink
                        key={to}
                        to={to}
                        className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                    >
                        <span className="nav-link-icon">{icon}</span>
                        <span className="nav-link-text">{label}</span>
                        {/* The NavLink component will pass isActive; we render the indicator inline */}
                    </NavLink>
                ))}
            </nav>

            {/* Sign out */}
            <div className="sidebar-footer">
                <button
                    className="btn btn-ghost btn-full btn-sm"
                    onClick={handleLogout}
                >
                    🚪 Sign Out
                </button>
            </div>
        </aside>
    );
}
