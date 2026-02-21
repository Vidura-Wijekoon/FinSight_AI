import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { listDocuments, ingestDocument, deleteDocument } from '../api/client';

const ACCEPTED_TYPES = '.pdf,.docx,.xlsx,.csv,.txt';
const MAX_SIZE_MB = 50;

export default function DocumentsPage() {
    const { user } = useAuth();

    const [docs, setDocs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [dragOver, setDragOver] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [uploadResult, setUploadResult] = useState(null); // { success, message }
    const [deletingId, setDeletingId] = useState(null);
    const fileInputRef = useRef();

    const fetchDocs = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const data = await listDocuments();
            setDocs(data.documents ?? []);
        } catch (err) {
            setError(err.message || 'Failed to load documents.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchDocs(); }, [fetchDocs]);

    // ── File selection ──────────────────────────────────────────────────────────
    const handleFileChange = (file) => {
        if (!file) return;
        if (file.size > MAX_SIZE_MB * 1024 * 1024) {
            setUploadResult({ success: false, message: `File exceeds ${MAX_SIZE_MB} MB limit.` });
            return;
        }
        setSelectedFile(file);
        setUploadResult(null);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFileChange(file);
    };

    // ── Upload ──────────────────────────────────────────────────────────────────
    const handleUpload = async () => {
        if (!selectedFile) return;
        setUploading(true);
        setUploadResult(null);
        try {
            const data = await ingestDocument(selectedFile);
            setUploadResult({
                success: true,
                message: `✅ "${data.original_name}" indexed — ${data.chunk_count} chunks created.`,
            });
            setSelectedFile(null);
            if (fileInputRef.current) fileInputRef.current.value = '';
            await fetchDocs();
        } catch (err) {
            setUploadResult({
                success: false,
                message: `❌ Ingestion failed: ${err.message}`,
            });
        } finally {
            setUploading(false);
        }
    };

    // ── Delete ──────────────────────────────────────────────────────────────────
    const handleDelete = async (docId) => {
        if (!window.confirm('Delete this document and all its vectors? This cannot be undone.')) return;
        setDeletingId(docId);
        try {
            await deleteDocument(docId);
            await fetchDocs();
        } catch (err) {
            setError(`Delete failed: ${err.message}`);
        } finally {
            setDeletingId(null);
        }
    };

    // ── Status badge ────────────────────────────────────────────────────────────
    const statusBadge = (status) => {
        const map = {
            indexed: { cls: 'status-indexed', icon: '●', label: 'INDEXED' },
            empty: { cls: 'status-empty', icon: '○', label: 'EMPTY' },
            error: { cls: 'status-error', icon: '✕', label: 'ERROR' },
        };
        const s = map[status] ?? { cls: '', icon: '?', label: status?.toUpperCase() ?? 'UNKNOWN' };
        return (
            <span className={`status-badge ${s.cls}`}>
                {s.icon} {s.label}
            </span>
        );
    };

    return (
        <>
            <div className="page-header">
                <h1 className="page-title">📄 Document Management</h1>
                <p className="page-subtitle">Upload, manage, and monitor your financial documents.</p>
            </div>

            {/* ── Upload Section ── */}
            {(user?.role === 'admin' || user?.role === 'analyst') && (
                <div className="card mb-6">
                    <div className="card-header">
                        <span className="card-title">➕ Upload New Document</span>
                        {selectedFile && (
                            <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                                {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                            </span>
                        )}
                    </div>

                    {/* Drag & Drop zone */}
                    <div
                        id="upload-dropzone"
                        className={`upload-zone${dragOver ? ' drag-over' : ''}`}
                        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <div className="upload-icon">{selectedFile ? '📎' : '☁️'}</div>
                        <p className="upload-text">
                            {selectedFile
                                ? selectedFile.name
                                : 'Drop a file here or click to browse'}
                        </p>
                        <p className="upload-subtext">
                            PDF · DOCX · XLSX · CSV · TXT &nbsp;|&nbsp; Max {MAX_SIZE_MB} MB
                        </p>
                    </div>

                    <input
                        ref={fileInputRef}
                        type="file"
                        accept={ACCEPTED_TYPES}
                        style={{ display: 'none' }}
                        id="file-input"
                        onChange={e => handleFileChange(e.target.files[0])}
                    />

                    {uploadResult && (
                        <div className={`alert ${uploadResult.success ? 'alert-success' : 'alert-error'}`}
                            style={{ marginTop: '1rem' }}>
                            {uploadResult.message}
                        </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem', gap: '0.75rem' }}>
                        {selectedFile && (
                            <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => { setSelectedFile(null); setUploadResult(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                            >
                                ✕ Clear
                            </button>
                        )}
                        <button
                            id="ingest-btn"
                            className="btn btn-primary"
                            disabled={!selectedFile || uploading}
                            onClick={handleUpload}
                        >
                            {uploading ? <><div className="spinner" /> Indexing…</> : '📤 Ingest Document'}
                        </button>
                    </div>
                </div>
            )}

            {/* ── Error ── */}
            {error && (
                <div className="alert alert-error mb-4">⚠️ {error}</div>
            )}

            {/* ── Document List ── */}
            <div className="card">
                <div className="card-header">
                    <span className="card-title">📋 Indexed Documents</span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                        {docs.length} document{docs.length !== 1 ? 's' : ''}
                    </span>
                </div>

                {loading ? (
                    <div className="loading-center">
                        <div className="spinner" />
                        <span>Loading documents…</span>
                    </div>
                ) : docs.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">📂</div>
                        <p className="empty-state-text">No documents indexed yet. Upload your first document above.</p>
                    </div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table className="doc-table">
                            <thead>
                                <tr>
                                    <th>Document</th>
                                    <th>Status</th>
                                    <th>Chunks</th>
                                    <th>Size</th>
                                    <th>Uploaded By</th>
                                    {user?.role === 'admin' && <th>Actions</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {docs.map((doc) => (
                                    <tr key={doc.doc_id}>
                                        <td>
                                            <div className="doc-name">{doc.original_name ?? 'Unknown'}</div>
                                            <div className="doc-id">ID: {doc.doc_id?.slice(0, 16)}…</div>
                                        </td>
                                        <td>{statusBadge(doc.status)}</td>
                                        <td style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
                                            {doc.chunk_count ?? 0}
                                        </td>
                                        <td style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                                            {((doc.size_bytes ?? 0) / 1024).toFixed(1)} KB
                                        </td>
                                        <td style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                                            {doc.uploaded_by ?? '—'}
                                        </td>
                                        {user?.role === 'admin' && (
                                            <td>
                                                <button
                                                    className="btn btn-danger btn-sm"
                                                    onClick={() => handleDelete(doc.doc_id)}
                                                    disabled={deletingId === doc.doc_id}
                                                    title="Delete document"
                                                >
                                                    {deletingId === doc.doc_id ? <div className="spinner" /> : '🗑️'}
                                                </button>
                                            </td>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Refresh */}
                <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
                    <button className="btn btn-ghost btn-sm" onClick={fetchDocs} disabled={loading}>
                        🔄 Refresh
                    </button>
                </div>
            </div>
        </>
    );
}
