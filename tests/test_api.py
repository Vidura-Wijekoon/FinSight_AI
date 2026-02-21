"""
Tests for FinSight AI — API Endpoints
Uses FastAPI TestClient with mocked services.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture with mocked services
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    """
    Create TestClient with all heavy services mocked at app.state level.
    This avoids loading SentenceTransformers + ChromaDB + Ollama in CI.
    """
    # Patch settings to avoid requiring .env file
    with patch("config.settings.Settings._settings_build_values", return_value={}):
        pass

    from src.api.main import app

    # Inject mock services into app.state before test
    mock_audit = MagicMock()
    mock_audit.log = MagicMock()
    mock_audit.get_recent_logs = MagicMock(return_value=[])
    mock_audit.search_logs = MagicMock(return_value=[])
    mock_audit.get_stats = MagicMock(return_value={"total_entries": 0, "log_size_bytes": 0})

    mock_file_handler = MagicMock()
    mock_file_handler.list_documents = MagicMock(return_value=[])
    mock_file_handler.get_document = MagicMock(return_value=None)
    mock_file_handler.delete_document = MagicMock(return_value=True)

    mock_chroma = MagicMock()
    mock_chroma.get_stats = MagicMock(return_value={
        "total_chunks": 10, "total_documents": 2, "collection_name": "finsight_docs"
    })
    mock_chroma.delete_document = MagicMock(return_value=5)

    mock_rag = MagicMock()
    from src.rag.pipeline import RAGResponse
    mock_rag.execute = AsyncMock(return_value=RAGResponse(
        answer="The revenue increased by 12% [Chunk 1].",
        citations=[{
            "chunk_num": 1, "source_file": "annual_report.pdf",
            "doc_id": "doc-001", "chunk_index": 0,
            "relevance_score": 0.92, "cited_in_answer": True,
        }],
        chunks_used=1,
        latency_ms=250.0,
        model_used="llama3.1:8b",
        query="What was the revenue growth?",
    ))

    with TestClient(app, raise_server_exceptions=True) as c:
        app.state.audit_logger = mock_audit
        app.state.file_handler = mock_file_handler
        app.state.chroma_store = mock_chroma
        app.state.rag_pipeline = mock_rag
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    """Log in as admin and return the Bearer token."""
    from config.settings import get_settings
    s = get_settings()
    resp = client.post("/auth/login", data={"username": s.ADMIN_USERNAME, "password": s.ADMIN_PASSWORD})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------
class TestAuth:
    def test_login_success(self, client):
        from config.settings import get_settings
        s = get_settings()
        resp = client.post("/auth/login", data={
            "username": s.ADMIN_USERNAME,
            "password": s.ADMIN_PASSWORD,
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client):
        resp = client.post("/auth/login", data={
            "username": "admin",
            "password": "totally_wrong",
        })
        assert resp.status_code == 401

    def test_get_me(self, client, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_refresh_token(self, client, auth_headers):
        resp = client.post("/auth/refresh", headers=auth_headers)
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Document tests
# ---------------------------------------------------------------------------
class TestDocuments:
    def test_list_documents(self, client, auth_headers):
        resp = client.get("/documents/list", headers=auth_headers)
        assert resp.status_code == 200
        assert "documents" in resp.json()

    def test_list_requires_auth(self, client):
        resp = client.get("/documents/list")
        assert resp.status_code == 401

    def test_get_missing_document(self, client, auth_headers):
        resp = client.get("/documents/nonexistent-doc-id", headers=auth_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------
class TestQuery:
    def test_rag_query_returns_cited_answer(self, client, auth_headers):
        resp = client.post(
            "/query",
            headers=auth_headers,
            json={"query": "What was the revenue growth?", "top_k": 4},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "citations" in data
        assert "model_used" in data
        assert "latency_ms" in data

    def test_query_requires_auth(self, client):
        resp = client.post("/query", json={"query": "test", "top_k": 4})
        assert resp.status_code == 401

    def test_query_short_string_rejected(self, client, auth_headers):
        resp = client.post("/query", headers=auth_headers, json={"query": "hi", "top_k": 4})
        assert resp.status_code == 422  # min_length=3 validation


# ---------------------------------------------------------------------------
# Admin tests
# ---------------------------------------------------------------------------
class TestAdmin:
    def test_stats_requires_admin(self, client, auth_headers):
        resp = client.get("/admin/stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "documents" in data
        assert "vector_store" in data

    def test_logs_endpoint(self, client, auth_headers):
        resp = client.get("/admin/logs", headers=auth_headers)
        assert resp.status_code == 200
        assert "logs" in resp.json()

    def test_log_search(self, client, auth_headers):
        resp = client.get(
            "/admin/logs/search",
            headers=auth_headers,
            params={"query": "rag_query"},
        )
        assert resp.status_code == 200

    def test_health_check(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
