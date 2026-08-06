"""
Tests for FinSight AI — Operability

Covers the provider gate, the liveness and readiness probes, and rate limiting.
Services are injected into app.state directly rather than through the lifespan,
for the reason documented in tests/test_api.py.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

BASE_ENV = {
    "SECRET_KEY": "test-secret-key",
    "ADMIN_PASSWORD": "test-admin-password",
}


# ---------------------------------------------------------------------------
# Provider gate
# ---------------------------------------------------------------------------
class TestProviderGate:
    """A remote provider in sovereign mode must prevent construction entirely."""

    def test_sovereign_mode_rejects_remote_provider(self):
        from config.settings import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(**BASE_ENV, DEPLOYMENT_MODE="sovereign", LLM_PROVIDER="gemini")

        message = str(exc_info.value)
        # The operator must be told what to do, not merely that something failed.
        assert "sovereign" in message
        assert "DEPLOYMENT_MODE=hybrid" in message

    def test_sovereign_mode_accepts_ollama(self):
        from config.settings import Settings

        settings = Settings(**BASE_ENV, DEPLOYMENT_MODE="sovereign", LLM_PROVIDER="ollama")
        assert settings.LLM_PROVIDER == "ollama"

    def test_hybrid_mode_permits_remote_provider(self):
        """Remote inference is allowed, but only when declared explicitly."""
        from config.settings import Settings

        settings = Settings(**BASE_ENV, DEPLOYMENT_MODE="hybrid", LLM_PROVIDER="gemini")
        assert settings.LLM_PROVIDER == "gemini"

    def test_sovereign_mode_rejects_a_remote_ollama_endpoint(self):
        """
        The gate must check the destination, not only the provider name.
        LLM_PROVIDER stays 'ollama' here, so a name-only check passes while
        every prompt is sent to a third party.
        """
        from config.settings import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                **BASE_ENV,
                DEPLOYMENT_MODE="sovereign",
                LLM_PROVIDER="ollama",
                OLLAMA_BASE_URL="https://ollama.example.com",
            )
        assert "OLLAMA_BASE_URL" in str(exc_info.value)

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://host.docker.internal:11434",  # API in a container, Ollama on the host
            "http://10.0.4.20:11434",             # Ollama on an internal server
            "http://192.168.1.50:11434",
        ],
    )
    def test_sovereign_mode_accepts_local_and_private_endpoints(self, url):
        from config.settings import Settings

        settings = Settings(**BASE_ENV, DEPLOYMENT_MODE="sovereign", OLLAMA_BASE_URL=url)
        assert settings.OLLAMA_BASE_URL == url

    def test_hybrid_mode_permits_a_remote_endpoint(self):
        from config.settings import Settings

        settings = Settings(
            **BASE_ENV,
            DEPLOYMENT_MODE="hybrid",
            OLLAMA_BASE_URL="https://ollama.example.com",
        )
        assert settings.OLLAMA_BASE_URL == "https://ollama.example.com"

    def test_sovereign_is_the_default(self):
        """Omitting the variable must not silently permit a remote provider."""
        from config.settings import Settings

        assert Settings(**BASE_ENV).DEPLOYMENT_MODE == "sovereign"


# ---------------------------------------------------------------------------
# Health and readiness
# ---------------------------------------------------------------------------
def _client(*, chroma_ok=True, embedding_ok=True, llm_ok=True) -> TestClient:
    """Build a client whose dependencies succeed or fail as requested."""
    from src.api.main import app

    chroma = MagicMock()
    chroma.heartbeat = (
        MagicMock(return_value=12) if chroma_ok
        else MagicMock(side_effect=RuntimeError("chroma unreachable"))
    )

    embedding = MagicMock()
    if embedding_ok:
        type(embedding).dimension = property(lambda self: 384)
    else:
        type(embedding).dimension = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("model not loaded"))
        )

    llm = MagicMock()
    llm.health = (
        AsyncMock(return_value=True) if llm_ok
        else AsyncMock(side_effect=ConnectionError("ollama down"))
    )

    app.state.chroma_store = chroma
    app.state.embedding_service = embedding
    app.state.llm_service = llm
    return TestClient(app, raise_server_exceptions=True)


class TestHealth:
    def test_health_is_200_with_no_dependencies(self):
        """
        Liveness must not consult dependencies. With every one of them failing,
        the process is still alive and must not be restarted.
        """
        client = _client(chroma_ok=False, embedding_ok=False, llm_ok=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_requires_no_auth(self):
        resp = _client().get("/health")
        assert resp.status_code == 200


class TestReadiness:
    def test_ready_is_200_when_all_dependencies_pass(self):
        resp = _client().get("/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert all(c["ok"] for c in body["checks"].values())

    def test_ready_is_503_when_llm_is_down(self):
        """Acceptance criterion: /ready fails when Ollama is stopped."""
        resp = _client(llm_ok=False).get("/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["llm"]["ok"] is False
        assert body["checks"]["vector_store"]["ok"] is True

    def test_ready_names_the_failing_dependency(self):
        """A probe that says only 'not ready' makes an operator go looking."""
        resp = _client(chroma_ok=False).get("/ready")
        assert resp.status_code == 503
        assert "chroma unreachable" in resp.json()["checks"]["vector_store"]["error"]

    def test_ready_reports_every_failure_not_just_the_first(self):
        resp = _client(chroma_ok=False, llm_ok=False).get("/ready")
        checks = resp.json()["checks"]
        assert checks["vector_store"]["ok"] is False
        assert checks["llm"]["ok"] is False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class TestRateLimiting:
    def test_limiter_keys_on_user_not_address(self):
        """
        Behind a reverse proxy every caller shares one address, so limiting by
        address would let one user throttle everyone else.
        """
        from src.api.rate_limit import user_key
        from src.security.auth import create_access_token

        token = create_access_token("analyst_a", "analyst")
        request = MagicMock()
        request.headers = {"authorization": f"Bearer {token}"}
        assert user_key(request) == "user:analyst_a"

    def test_limiter_falls_back_to_address_without_a_token(self):
        """Omitting the token must not be a way to escape the limit."""
        from src.api.rate_limit import user_key

        request = MagicMock()
        request.headers = {}
        request.client.host = "203.0.113.7"
        assert user_key(request) == "addr:203.0.113.7"

    def test_limiter_falls_back_to_address_on_a_forged_token(self):
        from src.api.rate_limit import user_key

        request = MagicMock()
        request.headers = {"authorization": "Bearer not-a-real-jwt"}
        request.client.host = "203.0.113.7"
        assert user_key(request) == "addr:203.0.113.7"
