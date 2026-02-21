"""
FinSight AI — Query Route
POST /query — Submit a question and receive a citation-backed answer from the RAG pipeline.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_audit_logger, get_current_user, get_rag_pipeline
from src.security.auth import UserInDB

router = APIRouter(prefix="/query", tags=["RAG Query"])


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, description="Natural language question")
    top_k: int = Field(4, ge=1, le=20, description="Number of context chunks to retrieve")


class CitationItem(BaseModel):
    chunk_num: int
    source_file: str
    doc_id: str
    chunk_index: int
    relevance_score: float
    cited_in_answer: bool


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationItem]
    chunks_used: int
    latency_ms: float
    model_used: str
    query: str


@router.post("", response_model=QueryResponse, summary="Ask a question over ingested documents")
async def rag_query(
    body: QueryRequest,
    current_user: UserInDB = Depends(get_current_user),  # All authenticated users can query
    rag_pipeline=Depends(get_rag_pipeline),
    audit_logger=Depends(get_audit_logger),
):
    """
    Run the full RAG pipeline:
    1. Embed query with all-MiniLM-L6-v2 (same model as ingestion)
    2. Retrieve top-K contextually similar chunks from ChromaDB
    3. Build prompt with [Chunk X] citation markers
    4. Generate answer with llama3.1:8b via Ollama (local, no API key)
    5. Return structured response with citations and source documents
    """
    result = await rag_pipeline.execute(
        query=body.query,
        user=current_user.username,
        top_k=body.top_k,
    )

    # Log the query access
    audit_logger.log(
        "query_served",
        current_user.username,
        {
            "query_length": len(body.query),
            "top_k": body.top_k,
            "model": result.model_used,
            "latency_ms": result.latency_ms,
        },
    )

    return QueryResponse(
        answer=result.answer,
        citations=[CitationItem(**c) for c in result.citations],
        chunks_used=result.chunks_used,
        latency_ms=result.latency_ms,
        model_used=result.model_used,
        query=result.query,
    )
