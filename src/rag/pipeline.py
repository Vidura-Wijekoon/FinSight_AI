"""
FinSight AI — RAG Pipeline
End-to-end orchestration: query → retrieve → build prompt → generate → audit.
Returns a structured RAGResponse with citation-backed answer.
"""
import re
import time
from dataclasses import dataclass, field

from src.audit.audit_logger import AuditLogger
from src.llm.llm_service import LLMService
from src.retrieval.retriever import RetrievedChunk, Retriever


@dataclass
class RAGResponse:
    """Structured response from the RAG pipeline."""
    answer: str
    citations: list[dict]       # [{source_file, chunk_index, relevance_score, chunk_num}]
    chunks_used: int
    latency_ms: float
    model_used: str
    query: str


class RAGPipeline:
    """
    Full RAG orchestration:
    1. Retrieve top-K context chunks (cosine similarity)
    2. Build formatted prompt with [Chunk X] citation markers
    3. Generate answer via LLM (Ollama llama3.1:8b by default)
    4. Extract and verify citations in response
    5. Audit log every query event
    """

    def __init__(
        self,
        retriever: Retriever,
        llm_service: LLMService,
        audit_logger: AuditLogger,
        default_top_k: int = 4,
    ) -> None:
        self._retriever = retriever
        self._llm = llm_service
        self._audit = audit_logger
        self._default_top_k = default_top_k

    async def execute(
        self,
        query: str,
        user: str,
        top_k: int | None = None,
    ) -> RAGResponse:
        """
        Run the full RAG pipeline for a user query.

        Args:
            query: The natural language question.
            user: Username for audit logging.
            top_k: Override default top-K chunks if provided.

        Returns:
            RAGResponse with cited answer and performance metrics.
        """
        k = top_k if top_k is not None else self._default_top_k
        start_time = time.perf_counter()

        # Step 1 — Retrieve context chunks
        chunks: list[RetrievedChunk] = self._retriever.retrieve(query, top_k=k)

        if not chunks:
            # No documents indexed yet
            answer = (
                "No documents have been ingested into FinSight AI yet. "
                "Please upload financial documents first."
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            response = RAGResponse(
                answer=answer,
                citations=[],
                chunks_used=0,
                latency_ms=round(latency_ms, 2),
                model_used=self._llm.model_name,
                query=query,
            )
            self._log_query(user, query, response)
            return response

        # Step 2 — Build prompt with [Chunk X] citation markers
        prompt = self._llm.build_rag_prompt(query, chunks)

        # Step 3 — Generate LLM answer
        answer = await self._llm.generate(prompt)

        # Step 4 — Build citation list
        citations = self._build_citations(answer, chunks)

        latency_ms = (time.perf_counter() - start_time) * 1000
        response = RAGResponse(
            answer=answer,
            citations=citations,
            chunks_used=len(chunks),
            latency_ms=round(latency_ms, 2),
            model_used=self._llm.model_name,
            query=query,
        )

        # Step 5 — Audit log
        self._log_query(user, query, response)
        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_citations(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> list[dict]:
        """
        Extract which [Chunk X] markers appear in the answer
        and map them back to source metadata.
        """
        cited_indices: set[int] = set()
        for match in re.finditer(r"\[Chunk\s+(\d+)\]", answer, re.IGNORECASE):
            cited_indices.add(int(match.group(1)))

        citations = []
        for i, chunk in enumerate(chunks, start=1):
            cited = i in cited_indices
            citations.append({
                "chunk_num": i,
                "source_file": chunk.source_file,
                "doc_id": chunk.doc_id,
                "chunk_index": chunk.chunk_index,
                "relevance_score": chunk.score,
                "cited_in_answer": cited,
            })
        return citations

    def _log_query(self, user: str, query: str, response: RAGResponse) -> None:
        self._audit.log(
            event="rag_query",
            user=user,
            detail={
                "query": query[:200],           # Truncate for log readability
                "chunks_retrieved": response.chunks_used,
                "model": response.model_used,
                "latency_ms": response.latency_ms,
                "citations_count": len(response.citations),
            },
        )
