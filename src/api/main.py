"""
FinSight AI — FastAPI Application Entry Point
Initializes all services at startup via lifespan context manager.
All service instances are stored in app.state for dependency injection.
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Ensure project root is on Python path when running from src/api/main.py
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import get_settings
from src.audit.audit_logger import AuditLogger
from src.embeddings.embedding_service import EmbeddingService
from src.ingestion.file_handler import FileHandler
from src.llm.llm_service import LLMService
from src.rag.pipeline import RAGPipeline
from src.retrieval.retriever import Retriever
from src.security.encryption import generate_key, load_key
from src.vectorstore.chroma_store import ChromaStore
from src.api.routes import auth, documents, query, admin


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

    audit_logger.log("server_ready", "system", {"llm": llm_service.model_name})

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

# CORS — restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(admin.router)


@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "FinSight AI",
        "version": "1.0.0",
        "docs": "/docs",
    }
