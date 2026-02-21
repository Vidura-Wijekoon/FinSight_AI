"""
FinSight AI — ChromaDB Vector Store
Persistent cosine-similarity vector store with document-level CRUD.
"""
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.embeddings.embedding_service import EmbeddingService
from src.ingestion.chunker import Chunk


class ChromaStore:
    """Wrapper around ChromaDB PersistentClient with document-level CRUD."""

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        embedding_service: EmbeddingService,
    ) -> None:
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_service,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, doc_id: str, chunks: list[Chunk]) -> int:
        """Embed and upsert all chunks for a document. Returns chunk count."""
        if not chunks:
            return 0
        self._collection.upsert(
            ids=[f"{doc_id}_chunk_{c.metadata['chunk_index']}" for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )
        return len(chunks)

    def query_by_embedding(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        filter_dict: dict | None = None,
    ) -> dict[str, Any]:
        """Similarity search using a pre-computed query embedding."""
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_dict:
            kwargs["where"] = filter_dict
        return self._collection.query(**kwargs)

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for doc_id. Returns number of chunks deleted."""
        results = self._collection.get(where={"doc_id": doc_id}, include=[])
        chunk_ids = results.get("ids", [])
        if chunk_ids:
            self._collection.delete(ids=chunk_ids)
        return len(chunk_ids)

    def get_stats(self) -> dict[str, Any]:
        """Return collection-level statistics."""
        total_chunks = self._collection.count()
        results = self._collection.get(include=["metadatas"])
        doc_ids = {m.get("doc_id") for m in (results.get("metadatas") or []) if m}
        return {
            "total_chunks": total_chunks,
            "total_documents": len(doc_ids),
            "collection_name": self._collection.name,
        }
