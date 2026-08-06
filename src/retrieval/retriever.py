"""
FinSight AI — Retriever
Cosine similarity top-K retrieval over ChromaDB using local embeddings.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("finsight.retrieval")


class RetrievalError(RuntimeError):
    """
    Raised when retrieval cannot produce usable context.

    Deliberately distinct from returning no results. An empty index is a normal
    condition the pipeline handles; being unable to read the documents that were
    matched is a fault, and answering anyway would mean answering from nothing.
    """

from src.embeddings.embedding_service import EmbeddingService
from src.vectorstore.chroma_store import ChromaStore


def resolve_file_type(meta: dict) -> str:
    """
    Determine how to re-extract a source document at query time.

    Prefers the `file_type` recorded at ingestion, and falls back to the
    extension of `source_file` so that indexes written before `file_type` was
    recorded still parse correctly rather than needing re-ingestion.

    Defaulting to 'txt' is deliberately not an option. It meant PDF, DOCX and
    XLSX documents were decoded as UTF-8, so the container bytes — object
    tables, ZIP headers — were handed to the model as document text, with no
    error and no outward sign that anything was wrong.
    """
    file_type = str(meta.get("file_type") or "").strip().lstrip(".").lower()
    if file_type:
        return file_type

    suffix = Path(str(meta.get("source_file") or "")).suffix.lstrip(".").lower()
    if suffix:
        return suffix

    raise ValueError(
        f"Cannot determine the file type for doc_id={meta.get('doc_id')!r}: chunk "
        "metadata carries neither 'file_type' nor a 'source_file' extension."
    )


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

        from src.ingestion.chunker import DocumentChunker
        from src.ingestion.text_extractor import TextExtractor
        from src.security.encryption import load_and_decrypt

        # Cache for decrypted document texts to avoid redundant disk I/O
        doc_cache: dict[str, str] = {}
        unreadable: dict[str, str] = {}
        chunks: list[RetrievedChunk] = []

        # We need access to the data dir from settings or relative path
        # In this context, we'll use a pragmatic approach:
        # The metadata contains doc_id, and we know chunks were created from full text.
        # To be precise as per requirement: "decrypted in-memory before sent to LLM"

        for meta, dist in zip(metas_list, dists_list, strict=False):
            doc_id = meta.get("doc_id", "")
            chunk_idx = meta.get("chunk_index", 0)

            if doc_id in unreadable:
                continue

            if doc_id not in doc_cache:
                # This part is slightly inefficient but ensures "Precision Retrieval"
                # from the source of truth (the encrypted file).
                try:
                    # Resolve path to encrypted file
                    # We assume standard structure ./data/uploads/{doc_id}.enc
                    # NOTE: load_and_decrypt calls .exists(), so this must be a
                    # Path — passing a str raises AttributeError.
                    enc_path = Path("data") / "uploads" / f"{doc_id}.enc"
                    raw_bytes = load_and_decrypt(enc_path.resolve(), self._key)

                    extractor = TextExtractor()
                    full_text = extractor.extract(raw_bytes, resolve_file_type(meta))
                    doc_cache[doc_id] = full_text
                except Exception as exc:
                    # Broad on purpose: the extractors raise library-specific
                    # types (bad ZIP, malformed PDF) that cannot be enumerated
                    # usefully. What matters is that a failure NEVER becomes
                    # chunk text. Substituting a placeholder here previously
                    # meant an unreadable document was passed to the model as
                    # evidence and could be cited in the answer.
                    unreadable[doc_id] = f"{type(exc).__name__}: {exc}"
                    logger.error(
                        "Excluding unreadable document from retrieval: doc_id=%s source_file=%s reason=%s",
                        doc_id,
                        meta.get("source_file", "unknown"),
                        unreadable[doc_id],
                    )
                    continue

            # Re-chunk to get the specific text (since we didn't store it in Chroma)
            chunker = DocumentChunker()
            doc_chunks = chunker.chunk(doc_cache[doc_id], {"doc_id": doc_id})

            if chunk_idx >= len(doc_chunks):
                # The index and the document have diverged — the document has
                # changed since it was indexed, or chunking parameters differ
                # between ingestion and here (see KNOWN_LIMITATIONS item 16).
                # Excluded rather than padded with placeholder text.
                logger.error(
                    "Excluding chunk absent from re-derived document: doc_id=%s chunk_index=%s of %s",
                    doc_id,
                    chunk_idx,
                    len(doc_chunks),
                )
                continue

            chunks.append(
                RetrievedChunk(
                    text=doc_chunks[chunk_idx].text,
                    score=round(max(0.0, 1.0 - dist), 4),
                    doc_id=doc_id,
                    chunk_index=chunk_idx,
                    source_file=meta.get("source_file", "unknown"),
                    metadata=meta,
                )
            )

        # Matches that could not be read must fail the request rather than
        # produce a confident answer built on nothing. An index with no matches
        # at all is a different condition and returns empty as before.
        if metas_list and not chunks:
            raise RetrievalError(
                f"Retrieved {len(metas_list)} match(es) but none could be read. "
                f"Unreadable documents: {unreadable or 'none'}."
            )

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks
