/**
 * FinSight AI — API Client
 * All API calls to the FastAPI backend.
 * Token is stored in localStorage under 'finsight_token'.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

// ── helpers ──────────────────────────────────────────────────────────────────

function getToken() {
    return localStorage.getItem('finsight_token');
}

function authHeaders(extra = {}) {
    const token = getToken();
    return {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...extra,
    };
}

async function handleResponse(res) {
    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const body = await res.json();
            detail = body.detail ?? JSON.stringify(body);
        } catch { /* ignore */ }
        const err = new Error(detail);
        err.status = res.status;
        throw err;
    }
    return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

/**
 * POST /auth/login — exchange username/password for a JWT.
 * Uses OAuth2PasswordRequestForm (form-encoded body).
 */
export async function login(username, password) {
    const body = new URLSearchParams({ username, password });
    const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        body,
    });
    return handleResponse(res); // { access_token, token_type }
}

/**
 * GET /auth/me — fetch the current user's profile.
 */
export async function getMe() {
    const res = await fetch(`${API_BASE}/auth/me`, {
        headers: authHeaders(),
    });
    return handleResponse(res); // { username, role, disabled }
}

/**
 * POST /auth/refresh — issue fresh JWT using existing token.
 */
export async function refreshToken() {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: authHeaders(),
    });
    return handleResponse(res);
}

// ── Documents ─────────────────────────────────────────────────────────────────

/**
 * GET /documents/list — list all ingested documents.
 */
export async function listDocuments() {
    const res = await fetch(`${API_BASE}/documents/list`, {
        headers: authHeaders(),
    });
    return handleResponse(res); // { total, documents: [...] }
}

/**
 * POST /documents/ingest — upload and index a document.
 * @param {File} file
 * @param {function} onProgress  — optional progress callback (not supported via fetch without XHR)
 */
export async function ingestDocument(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/documents/ingest`, {
        method: 'POST',
        headers: authHeaders(), // no Content-Type; browser sets multipart boundary
        body: formData,
    });
    return handleResponse(res);
}

/**
 * DELETE /documents/{doc_id} — delete a document (admin only).
 */
export async function deleteDocument(docId) {
    const res = await fetch(`${API_BASE}/documents/${docId}`, {
        method: 'DELETE',
        headers: authHeaders(),
    });
    return handleResponse(res);
}

// ── Query ─────────────────────────────────────────────────────────────────────

/**
 * POST /query — run the RAG pipeline and return a cited answer.
 */
export async function ragQuery(query, topK = 4) {
    const res = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ query, top_k: topK }),
    });
    return handleResponse(res);
}

// ── Admin ─────────────────────────────────────────────────────────────────────

/**
 * GET /admin/stats — system statistics.
 */
export async function getStats() {
    const res = await fetch(`${API_BASE}/admin/stats`, {
        headers: authHeaders(),
    });
    return handleResponse(res);
}

/**
 * GET /admin/logs?n=N — recent audit log entries.
 */
export async function getLogs(n = 100) {
    const res = await fetch(`${API_BASE}/admin/logs?n=${n}`, {
        headers: authHeaders(),
    });
    return handleResponse(res);
}

/**
 * GET /admin/logs/search?query=Q&field=F&limit=L — search audit logs.
 */
export async function searchLogs(query, field = 'event', limit = 100) {
    const params = new URLSearchParams({ query, field, limit });
    const res = await fetch(`${API_BASE}/admin/logs/search?${params}`, {
        headers: authHeaders(),
    });
    return handleResponse(res);
}
