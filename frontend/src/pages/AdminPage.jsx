import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getStats, getLogs, searchLogs } from '../api/client';

export default function AdminPage() {
    const { user } = useAuth();
    const navigate = useNavigate();

    const [stats, setStats] = useState(null);
    const [logs, setLogs] = useState([]);
    const [statsLoading, setStatsLoading] = useState(true);
    const [logsLoading, setLogsLoading] = useState(true);
    const [error, setError] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [logLimit, setLogLimit] = useState(50);
    const [expandedLog, setExpandedLog] = useState(null);

    // Guard: non-admins should not see this page (also handled in router)
    useEffect(() => {
        if (user && user.role !== 'admin') navigate('/documents', { replace: true });
    }, [user, navigate]);

    // ── Fetch stats ─────────────────────────────────────────────────────────────
    const fetchStats = useCallback(async () => {
        setStatsLoading(true);
        try {
            const data = await getStats();
            setStats(data);
        } catch (err) {
            setError(`Failed to load stats: ${err.message}`);
        } finally {
            setStatsLoading(false);
        }
    }, []);

    // ── Fetch logs ──────────────────────────────────────────────────────────────
    const fetchLogs = useCallback(async () => {
        setLogsLoading(true);
        try {
            let data;
            if (searchQuery.trim()) {
                data = await searchLogs(searchQuery.trim(), 'event', logLimit);
            } else {
                data = await getLogs(logLimit);
            }
            setLogs(data.logs ?? []);
        } catch (err) {
            setError(`Failed to load logs: ${err.message}`);
        } finally {
            setLogsLoading(false);
        }
    }, [searchQuery, logLimit]);

    useEffect(() => { fetchStats(); }, [fetchStats]);
    useEffect(() => { fetchLogs(); }, [fetchLogs]);

    // ── Level styling ────────────────────────────────────────────────────────────
    const levelClass = (lvl) => `level-${lvl ?? 'INFO'}`;

    // ── Status breakdown colors ──────────────────────────────────────────────────
    const statusColor = (s) => ({
        indexed: 'var(--color-success)',
        empty: 'var(--color-warning)',
        error: 'var(--color-error)',
    }[s] ?? 'var(--color-text-muted)');

    return (
        <>
            <div className="page-header">
                <h1 className="page-title">⚙️ Admin Dashboard</h1>
                <p className="page-subtitle">System statistics, document status, and audit logs.</p>
            </div>

            {error && <div className="alert alert-error mb-4">⚠️ {error}</div>}

            {/* ── Stats Row ── */}
            {statsLoading ? (
                <div className="loading-center" style={{ minHeight: '120px' }}>
                    <div className="spinner" /><span>Loading stats…</span>
                </div>
            ) : stats && (
                <>
                    <div className="metrics-grid">
                        <div className="metric-card">
                            <div className="metric-icon">📄</div>
                            <div className="metric-value">{stats.documents?.total ?? 0}</div>
                            <div className="metric-label">Total Documents</div>
                        </div>
                        <div className="metric-card">
                            <div className="metric-icon">🧩</div>
                            <div className="metric-value">{stats.vector_store?.total_chunks ?? 0}</div>
                            <div className="metric-label">Vector Chunks</div>
                        </div>
                        <div className="metric-card">
                            <div className="metric-icon">📋</div>
                            <div className="metric-value">{stats.audit_log?.total_entries ?? 0}</div>
                            <div className="metric-label">Audit Entries</div>
                        </div>
                        <div className="metric-card">
                            <div className="metric-icon">📁</div>
                            <div className="metric-value">
                                {((stats.audit_log?.log_size_bytes ?? 0) / 1024).toFixed(1)}<span style={{ fontSize: '1rem', color: 'var(--color-text-muted)' }}>KB</span>
                            </div>
                            <div className="metric-label">Log Size</div>
                        </div>
                    </div>

                    {/* Status breakdown */}
                    {stats.documents?.by_status && Object.keys(stats.documents.by_status).length > 0 && (
                        <div className="card mb-6">
                            <div className="section-title">Document Status Breakdown</div>
                            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                                {Object.entries(stats.documents.by_status).map(([s, count]) => (
                                    <div key={s} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                                        <span style={{ color: statusColor(s), fontWeight: 700 }}>●</span>
                                        <span style={{ color: 'var(--color-text-secondary)' }}>{s.toUpperCase()}: </span>
                                        <strong style={{ color: 'var(--color-text-primary)' }}>{count}</strong>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* ── Audit Log Viewer ── */}
            <div className="card">
                <div className="section-title">📋 Audit Log Viewer</div>

                <div className="search-bar-row">
                    <div className="form-group" style={{ flex: 1 }}>
                        <label className="form-label" htmlFor="log-search">Search logs</label>
                        <input
                            id="log-search"
                            className="form-input"
                            placeholder="e.g. rag_query, document_ingested, login…"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && fetchLogs()}
                        />
                    </div>
                    <div className="form-group" style={{ width: '120px' }}>
                        <label className="form-label" htmlFor="log-limit">Entries</label>
                        <input
                            id="log-limit"
                            type="number"
                            className="form-input"
                            min={10}
                            max={500}
                            value={logLimit}
                            onChange={e => setLogLimit(Number(e.target.value))}
                        />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                        <button
                            id="search-logs-btn"
                            className="btn btn-primary btn-sm"
                            onClick={fetchLogs}
                            disabled={logsLoading}
                        >
                            {logsLoading ? <div className="spinner" /> : '🔍 Search'}
                        </button>
                    </div>
                </div>

                {logsLoading ? (
                    <div className="loading-center">
                        <div className="spinner" /><span>Loading logs…</span>
                    </div>
                ) : logs.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">📋</div>
                        <p className="empty-state-text">No audit log entries found.</p>
                    </div>
                ) : (
                    <div id="audit-log-list">
                        {[...logs].reverse().map((entry, idx) => {
                            const ts = entry.timestamp?.slice(0, 19).replace('T', ' ') ?? '';
                            const isExpanded = expandedLog === idx;
                            return (
                                <div
                                    key={idx}
                                    className="audit-log-entry"
                                    onClick={() => setExpandedLog(isExpanded ? null : idx)}
                                >
                                    <div className="audit-log-header">
                                        <span className="audit-event">{entry.event}</span>
                                        <span className="audit-ts">{ts}</span>
                                        <span className="audit-user">{entry.user}</span>
                                        <span className={`audit-level ${levelClass(entry.level)}`}>
                                            {entry.level ?? 'INFO'}
                                        </span>
                                        <span style={{ color: 'var(--color-text-dim)', fontSize: '0.8rem' }}>
                                            {isExpanded ? '▲' : '▼'}
                                        </span>
                                    </div>

                                    {isExpanded && entry.detail && (
                                        <div className="audit-detail">
                                            {JSON.stringify(entry.detail, null, 2)}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}

                <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
                    <button className="btn btn-ghost btn-sm" onClick={fetchLogs} disabled={logsLoading}>
                        🔄 Refresh
                    </button>
                </div>
            </div>
        </>
    );
}
