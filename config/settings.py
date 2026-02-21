"""
FinSight AI — Centralized Settings
All configuration is loaded from environment variables / .env file.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    OLLAMA_MODEL: str = Field("llama3.1:8b")

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance (singleton)."""
    return Settings()
