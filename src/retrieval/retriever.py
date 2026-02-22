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
        encryption_key: bytes,
        default_top_k: int = 4,
    ) -> None:
        self._store = chroma_store
        self._embedder = embedding_service
        self._key = encryption_key
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
        """
        Convert raw ChromaDB result into RetrievedChunk list.
        PRECISION RETRIEVAL: Decrypts chunks from disk in-memory exactly when needed.
        """
        metas_list = raw.get("metadatas",  [[]])[0]
        dists_list = raw.get("distances",  [[]])[0]

        from src.ingestion.text_extractor import TextExtractor
        from src.ingestion.chunker import DocumentChunker
        from src.security.encryption import load_and_decrypt
        from src.api.dependencies import get_file_handler
        import os

        # Cache for decrypted document texts to avoid redundant disk I/O
        doc_cache: dict[str, str] = {}
        chunks: list[RetrievedChunk] = []

        # We need access to the data dir from settings or relative path
        # In this context, we'll use a pragmatic approach: 
        # The metadata contains doc_id, and we know chunks were created from full text.
        # To be precise as per requirement: "decrypted in-memory before sent to LLM"
        
        for meta, dist in zip(metas_list, dists_list):
            doc_id = meta.get("doc_id", "")
            chunk_idx = meta.get("chunk_index", 0)
            
            if doc_id not in doc_cache:
                # This part is slightly inefficient but ensures "Precision Retrieval"
                # from the source of truth (the encrypted file).
                try:
                    # Resolve path to encrypted file
                    # We assume standard structure ./data/uploads/{doc_id}.enc
                    enc_path = os.path.join("data", "uploads", f"{doc_id}.enc")
                    raw_bytes = load_and_decrypt(os.path.abspath(enc_path), self._key)
                    
                    extractor = TextExtractor()
                    full_text = extractor.extract(raw_bytes, meta.get("file_type", "txt"))
                    doc_cache[doc_id] = full_text
                except Exception:
                    doc_cache[doc_id] = "[ERROR: Could not decrypt or extract document content]"

            # Re-chunk to get the specific text (since we didn't store it in Chroma)
            chunker = DocumentChunker()
            doc_chunks = chunker.chunk(doc_cache[doc_id], {"doc_id": doc_id})
            
            chunk_text = "[Chunk Content Missing]"
            if chunk_idx < len(doc_chunks):
                chunk_text = doc_chunks[chunk_idx].text

            chunks.append(
                RetrievedChunk(
                    text=chunk_text,
                    score=round(max(0.0, 1.0 - dist), 4),
                    doc_id=doc_id,
                    chunk_index=chunk_idx,
                    source_file=meta.get("source_file", "unknown"),
                    metadata=meta,
                )
            )

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks
