"""
FinSight AI — Centralized Settings
All configuration is loaded from environment variables / .env file.
"""
import ipaddress
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hostnames that denote the local machine or a container peer on the same host.
# Not resolved via DNS: resolution at configuration time is unreliable, and a
# name that resolves locally today may not tomorrow.
_LOCAL_HOSTNAMES = frozenset(
    {"localhost", "host.docker.internal", "ollama", "host.containers.internal"}
)


def is_local_endpoint(url: str) -> bool:
    """
    True if `url` points at this host or at the private network around it.

    Private ranges are accepted because Ollama running on an internal server is
    still inside the enterprise boundary, which is what sovereignty means here.
    Anything routable on the public internet is not.
    """
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return False
    if host in _LOCAL_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A hostname that is not a known-local name and not an IP literal. It
        # could resolve anywhere, so it is not treated as local.
        return False
    return address.is_loopback or address.is_private or address.is_link_local


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Security ---
    SECRET_KEY: str = Field(..., description="JWT signing secret key")
    JWT_ALGORITHM: str = Field("HS256")
    JWT_EXPIRY_MINUTES: int = Field(60)

    # --- Admin ---
    ADMIN_USERNAME: str = Field("admin")
    ADMIN_PASSWORD: str = Field(..., description="Admin account password")

    # --- LLM ---
    LLM_PROVIDER: Literal["ollama", "gemini"] = Field("ollama")
    GEMINI_API_KEY: str | None = Field(None)
    OLLAMA_BASE_URL: str = Field("http://localhost:11434")
    OLLAMA_MODEL: str = Field("qwen2.5")

    # --- Embedding ---
    EMBEDDING_MODEL: str = Field("all-MiniLM-L6-v2")

    # --- ChromaDB ---
    CHROMA_PERSIST_DIR: str = Field("./chroma_db")
    CHROMA_COLLECTION: str = Field("finsight_docs")

    # --- File Paths ---
    UPLOAD_DIR: str = Field("./data/uploads")
    PROCESSED_DIR: str = Field("./data/processed")
    LOG_FILE: str = Field("./logs/rag_audit.log")
    ENCRYPTION_KEY_PATH: str = Field("./keys/secret.key")

    # --- Ingestion Limits ---
    MAX_FILE_SIZE_MB: int = Field(50)

    # --- Deployment ---
    DEPLOYMENT_MODE: Literal["sovereign", "hybrid"] = Field(
        "sovereign",
        description=(
            "'sovereign' forbids any remote LLM provider. 'hybrid' permits one "
            "and accepts that document content leaves the host."
        ),
    )

    # --- Rate limiting (slowapi syntax, e.g. '30/minute') ---
    RATE_LIMIT_QUERY: str = Field("30/minute")
    RATE_LIMIT_INGEST: str = Field("10/minute")

    @model_validator(mode="after")
    def _enforce_sovereign_provider(self) -> "Settings":
        """
        Refuse to construct a configuration that silently defeats the data
        sovereignty guarantee.

        LLM_PROVIDER=gemini sends document content to a third-party API. That is
        a legitimate choice, but it must be a declared one: it is validated here
        rather than at request time so that a misconfigured deployment fails to
        start instead of running and quietly exfiltrating.
        """
        if self.DEPLOYMENT_MODE != "sovereign":
            return self

        if self.LLM_PROVIDER != "ollama":
            raise ValueError(
                f"LLM_PROVIDER='{self.LLM_PROVIDER}' is incompatible with "
                f"DEPLOYMENT_MODE='sovereign'. A remote provider sends document "
                f"content off the host, which is what sovereign mode exists to "
                f"prevent. Either set LLM_PROVIDER=ollama, or set "
                f"DEPLOYMENT_MODE=hybrid to declare that remote inference is "
                f"intended."
            )

        # Checking the provider name alone is not enough. OLLAMA_BASE_URL is the
        # actual destination, so pointing it at a public host exfiltrates every
        # prompt while LLM_PROVIDER is still 'ollama' and the check above passes.
        if not is_local_endpoint(self.OLLAMA_BASE_URL):
            raise ValueError(
                f"OLLAMA_BASE_URL='{self.OLLAMA_BASE_URL}' is not a local or "
                f"private-network address, so it is incompatible with "
                f"DEPLOYMENT_MODE='sovereign'. Prompts sent there leave the "
                f"enterprise boundary regardless of LLM_PROVIDER. Point it at "
                f"localhost, a private-range address, or a container host name, "
                f"or set DEPLOYMENT_MODE=hybrid to declare the intent."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance (singleton)."""
    return Settings()
