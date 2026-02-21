"""
FinSight AI — Retriever
Cosine similarity top-K retrieval over ChromaDB using local embeddings.
"""
from dataclasses import dataclass, field

from src.embeddings.embedding_service import EmbeddingService
from src.vectorstore.chroma_store import ChromaStore


@dataclass
class RetrievedChunk:
    """A retrieved text chunk with relevance metadata."""
    text: str
    score: float
    doc_id: str
    chunk_index: int
    source_file: str
    metadata: dict = field(default_factory=dict)


class Retriever:
    """Top-K retriever using cosine similarity over ChromaDB."""

    def __init__(
        self,
        chroma_store: ChromaStore,
        embedding_service: EmbeddingService,
        default_top_k: int = 4,
    ) -> None:
        self._store = chroma_store
        self._embedder = embedding_service
        self._default_top_k = default_top_k

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Embed query and retrieve top-K similar chunks."""
        k = top_k if top_k is not None else self._default_top_k
        query_embedding = self._embedder.embed_single(query)
        raw = self._store.query_by_embedding(
            query_embedding=query_embedding,
            top_k=k,
            filter_dict=filters,
        )
        return self._parse_results(raw)

    def _parse_results(self, raw: dict) -> list[RetrievedChunk]:
        """Convert raw ChromaDB result into RetrievedChunk list."""
        docs_list  = raw.get("documents",  [[]])[0]
        metas_list = raw.get("metadatas",  [[]])[0]
        dists_list = raw.get("distances",  [[]])[0]

        chunks = [
            RetrievedChunk(
                text=text,
                # ChromaDB cosine distance = 1 - similarity
                score=round(max(0.0, 1.0 - dist), 4),
                doc_id=meta.get("doc_id", ""),
                chunk_index=meta.get("chunk_index", 0),
                source_file=meta.get("source_file", meta.get("original_name", "unknown")),
                metadata=meta,
            )
            for text, meta, dist in zip(docs_list, metas_list, dists_list)
        ]
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks
