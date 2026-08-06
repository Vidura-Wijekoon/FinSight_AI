"""
FinSight AI — FastAPI Application Entry Point
Initializes all services at startup via lifespan context manager.
All service instances are stored in app.state for dependency injection.
"""
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# ---------------------------------------------------------------------------
# Ensure project root is on Python path when running from src/api/main.py
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import get_settings
from src.api.rate_limit import limiter, rate_limit_handler
from src.api.routes import admin, auth, documents, health, query
from src.audit.audit_logger import AuditLogger
from src.embeddings.embedding_service import EmbeddingService
from src.ingestion.file_handler import FileHandler
from src.llm.llm_service import LLMService
from src.rag.pipeline import RAGPipeline
from src.retrieval.retriever import RetrievalError, Retriever
from src.security.encryption import generate_key, load_key
from src.vectorstore.chroma_store import ChromaStore


# ---------------------------------------------------------------------------
# Lifespan — startup & shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 1. Ensure required directories exist
    for dir_path in [
        settings.UPLOAD_DIR,
        settings.PROCESSED_DIR,
        Path(settings.LOG_FILE).parent,
        Path(settings.ENCRYPTION_KEY_PATH).parent,
        settings.CHROMA_PERSIST_DIR,
    ]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    # 2. Generate encryption key if missing (first run)
    generate_key(settings.ENCRYPTION_KEY_PATH)
    enc_key = load_key(settings.ENCRYPTION_KEY_PATH)

    # 3. Initialize AuditLogger
    audit_logger = AuditLogger(settings.LOG_FILE)
    audit_logger.log("server_startup", "system", {"version": "1.0.0"})

    # 4. Initialize EmbeddingService (downloads model on first run)
    audit_logger.log("embedding_model_loading", "system", {"model": settings.EMBEDDING_MODEL})
    embedding_service = EmbeddingService(model_name=settings.EMBEDDING_MODEL)
    audit_logger.log("embedding_model_ready", "system", {"dim": embedding_service.dimension})

    # 5. Initialize ChromaDB store
    chroma_store = ChromaStore(
        persist_dir=settings.CHROMA_PERSIST_DIR,
        collection_name=settings.CHROMA_COLLECTION,
        embedding_service=embedding_service,
    )

    # 6. Initialize FileHandler
    file_handler = FileHandler(
        upload_dir=settings.UPLOAD_DIR,
        processed_dir=settings.PROCESSED_DIR,
        encryption_key=enc_key,
    )

    # 7. Initialize LLM service
    llm_kwargs = {
        "base_url": settings.OLLAMA_BASE_URL,
        "model": settings.OLLAMA_MODEL,
    }
    if settings.LLM_PROVIDER == "gemini":
        llm_kwargs["api_key"] = settings.GEMINI_API_KEY
    llm_service = LLMService(provider=settings.LLM_PROVIDER, **llm_kwargs)
    audit_logger.log(
        "llm_initialized",
        "system",
        {"provider": settings.LLM_PROVIDER, "model": llm_service.model_name},
    )

    # 8. Initialize Retriever
    retriever = Retriever(
        chroma_store=chroma_store,
        embedding_service=embedding_service,
        encryption_key=enc_key,
        default_top_k=4,  # per architecture diagram
    )

    # 9. Initialize RAG Pipeline
    rag_pipeline = RAGPipeline(
        retriever=retriever,
        llm_service=llm_service,
        audit_logger=audit_logger,
        default_top_k=4,
    )

    # 10. Store everything in app.state for dependency injection
    app.state.audit_logger = audit_logger
    app.state.embedding_service = embedding_service
    app.state.chroma_store = chroma_store
    app.state.file_handler = file_handler
    app.state.llm_service = llm_service
    app.state.retriever = retriever
    app.state.rag_pipeline = rag_pipeline
    app.state.enc_key = enc_key

    # 11. Structured startup record.
    # This is what an operator reads to confirm they deployed what they think
    # they deployed — in particular which LLM provider is live, since a remote
    # one moves document content off the host. Emitted to stdout as well as the
    # audit log, because in a container the audit file is inside the container.
    startup_record = {
        "event": "startup",
        "version": app.version,
        "deployment_mode": settings.DEPLOYMENT_MODE,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": llm_service.model_name,
        "embedding_model": settings.EMBEDDING_MODEL,
        "rate_limit_query": settings.RATE_LIMIT_QUERY,
        "rate_limit_ingest": settings.RATE_LIMIT_INGEST,
    }
    logging.getLogger("finsight.startup").info(json.dumps(startup_record))
    audit_logger.log("server_ready", "system", startup_record)

    yield  # Application runs here

    # Shutdown
    audit_logger.log("server_shutdown", "system", {})


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FinSight AI",
    description=(
        "Enterprise Financial RAG Platform — "
        "100% local inference with llama3.1:8b + all-MiniLM-L6-v2. "
        "Encryption-at-rest, JWT auth, RBAC, and immutable audit trails."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting. The limiter is registered on app.state because slowapi's
# middleware looks it up there; the handler adds Retry-After to the 429.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RetrievalError)
async def retrieval_error_handler(request, exc: RetrievalError):
    """
    Documents matched but could not be read — a fault, not an empty result.
    Returned as 503 rather than 500 because it is usually a recoverable
    operational condition: a missing encrypted file, or a key that no longer
    decrypts it. The detail is deliberately generic; the specific document and
    reason are in the server log, not in the response.
    """
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": (
                "Matching documents could not be read, so no answer was produced. "
                "This is a server-side fault; see the service logs."
            )
        },
    )

# CORS — restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(admin.router)


@app.get("/", tags=["Health"])
async def health_check():
    """
    Service banner. Retained for backwards compatibility with existing clients
    and the current container healthcheck; /health is the liveness probe and
    /ready is the readiness probe.
    """
    return {
        "status": "healthy",
        "service": "FinSight AI",
        "version": "1.0.0",
        "docs": "/docs",
    }
