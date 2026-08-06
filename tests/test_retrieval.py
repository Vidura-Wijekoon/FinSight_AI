"""
Tests for FinSight AI — Retrieval Pipeline
Tests embedding → ChromaDB store → retrieval roundtrip using a temp ChromaDB.

These tests also pin the project's headline security property: ChromaDB holds
only IDs, vectors and metadata, and chunk text is reconstructed by decrypting
the source document in memory at query time.
"""
import pytest

from src.ingestion.chunker import Chunk, DocumentChunker


@pytest.fixture(scope="module")
def embedding_service():
    from src.embeddings.embedding_service import EmbeddingService
    return EmbeddingService(model_name="all-MiniLM-L6-v2")


@pytest.fixture(scope="module")
def encryption_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key()


@pytest.fixture
def chroma_store(tmp_path, embedding_service):
    from src.vectorstore.chroma_store import ChromaStore
    return ChromaStore(
        persist_dir=str(tmp_path / "chroma"),
        collection_name="test_collection",
        embedding_service=embedding_service,
    )


@pytest.fixture
def retriever(chroma_store, embedding_service, encryption_key):
    from src.retrieval.retriever import Retriever
    return Retriever(
        chroma_store=chroma_store,
        embedding_service=embedding_service,
        encryption_key=encryption_key,
        default_top_k=4,
    )


def make_chunks(doc_id: str, texts: list[str]) -> list[Chunk]:
    return [
        Chunk(
            text=text,
            metadata={
                "doc_id": doc_id,
                "chunk_index": i,
                "source_file": f"{doc_id}.pdf",
                "file_type": "txt",
                "chunk_count": len(texts),
                "chunk_size": len(text),
                "uploaded_by": "test_user",
            },
        )
        for i, text in enumerate(texts)
    ]


def query_text(store, embedding_service, text: str, top_k: int = 4):
    """
    ChromaStore exposes only query_by_embedding — embedding is always performed
    by the caller so the store never has to touch raw query text.
    """
    return store.query_by_embedding(
        query_embedding=embedding_service.embed_single(text),
        top_k=top_k,
    )


class TestChromaStore:
    def test_add_documents_returns_count(self, chroma_store):
        chunks = make_chunks("doc-001", ["Revenue grew 12% YoY", "EBITDA margin improved"])
        count = chroma_store.add_documents("doc-001", chunks)
        assert count == 2

    def test_query_returns_results(self, chroma_store, embedding_service):
        chunks = make_chunks("doc-002", [
            "The company reported net income of $500M in Q3.",
            "Operating expenses increased by 8% due to headcount growth.",
        ])
        chroma_store.add_documents("doc-002", chunks)
        results = query_text(chroma_store, embedding_service, "net income", top_k=2)
        assert len(results["metadatas"][0]) > 0

    def test_no_plaintext_is_persisted(self, chroma_store, embedding_service):
        """
        Core security guarantee: the vector store must never hold chunk text.
        See README "Sovereign Embeddings & Secure Vector Store".
        """
        secret = "Project Halberd will be divested for $1.4B in January."
        chroma_store.add_documents("doc-secret", make_chunks("doc-secret", [secret]))

        results = query_text(chroma_store, embedding_service, "divestiture", top_k=4)

        for document in results["documents"][0]:
            assert document == "", "ChromaDB returned chunk text; it must store none"
        for meta in results["metadatas"][0]:
            assert secret not in " ".join(str(v) for v in meta.values())

    def test_delete_removes_chunks(self, chroma_store, embedding_service):
        chunks = make_chunks("doc-del", ["Delete me chunk 1", "Delete me chunk 2"])
        chroma_store.add_documents("doc-del", chunks)
        deleted = chroma_store.delete_document("doc-del")
        assert deleted == 2
        # Verify gone
        results = query_text(chroma_store, embedding_service, "Delete me", top_k=5)
        for meta in results.get("metadatas", [[]])[0]:
            assert meta.get("doc_id") != "doc-del"

    def test_empty_collection_query(self, tmp_path, embedding_service):
        """Query on empty collection should not raise."""
        from src.vectorstore.chroma_store import ChromaStore
        empty_store = ChromaStore(
            persist_dir=str(tmp_path / "empty_chroma"),
            collection_name="empty_col",
            embedding_service=embedding_service,
        )
        # Should return valid structure, not raise
        results = query_text(empty_store, embedding_service, "any query", top_k=4)
        assert "documents" in results

    def test_get_stats(self, chroma_store):
        chunks = make_chunks("doc-stats", ["Stats chunk one", "Stats chunk two", "Stats chunk three"])
        chroma_store.add_documents("doc-stats", chunks)
        stats = chroma_store.get_stats()
        assert "total_chunks" in stats
        assert stats["total_chunks"] >= 3

    def test_upsert_idempotent(self, chroma_store):
        """Re-ingesting the same doc_id should not duplicate chunks."""
        chunks = make_chunks("doc-upsert", ["Revenue data chunk"])
        chroma_store.add_documents("doc-upsert", chunks)
        initial_stats = chroma_store.get_stats()
        chroma_store.add_documents("doc-upsert", chunks)  # Second upsert
        final_stats = chroma_store.get_stats()
        assert final_stats["total_chunks"] == initial_stats["total_chunks"]


class TestRetriever:
    def test_retrieve_returns_relevant_chunks(self, retriever, chroma_store):
        chunks = make_chunks("doc-ret", [
            "The company's annual revenue reached $3.2 billion.",
            "Operating cash flow was positive at $850 million.",
            "The board approved a $500M share buyback program.",
        ])
        chroma_store.add_documents("doc-ret", chunks)
        results = retriever.retrieve("annual revenue figures")
        assert len(results) > 0
        # Top result should be about revenue
        assert results[0].score > 0

    def test_retrieve_scores_are_valid(self, retriever, chroma_store):
        chunks = make_chunks("doc-score", ["Earnings per share: $4.20"])
        chroma_store.add_documents("doc-score", chunks)
        results = retriever.retrieve("earnings per share")
        for chunk in results:
            assert 0.0 <= chunk.score <= 1.0

    def test_retrieve_respects_top_k(self, retriever, chroma_store):
        many_chunks = make_chunks("doc-topk", [f"Financial item number {i}" for i in range(10)])
        chroma_store.add_documents("doc-topk", many_chunks)
        results = retriever.retrieve("financial item", top_k=2)
        assert len(results) <= 2

    def test_chunk_text_is_decrypted_from_disk(
        self, tmp_path, monkeypatch, chroma_store, retriever, encryption_key
    ):
        """
        End-to-end proof of the retrieval design: the text handed to the LLM is
        absent from ChromaDB and comes from decrypting the source document.

        Retriever resolves ./data/uploads/{doc_id}.enc relative to the process
        working directory, so the test chdirs into a temp root.
        """
        from src.security.encryption import encrypt_and_save

        monkeypatch.chdir(tmp_path)
        uploads = tmp_path / "data" / "uploads"
        uploads.mkdir(parents=True)

        doc_id = "doc-e2e"
        document = (
            "FinSight Holdings reported consolidated revenue of $3.20 billion for "
            "fiscal year 2024, an increase of 12.4% year over year. "
        ) * 6
        encrypt_and_save(document.encode("utf-8"), uploads / f"{doc_id}.enc", encryption_key)

        # Index with the same parameters ingestion uses (see routes/documents.py)
        chunks = DocumentChunker(chunk_size=512, chunk_overlap=50).chunk(
            document,
            {"doc_id": doc_id, "source_file": "fy2024.txt", "file_type": "txt"},
        )
        chroma_store.add_documents(doc_id, chunks)

        results = retriever.retrieve("consolidated revenue for fiscal 2024", top_k=2)

        assert results, "retriever returned no chunks"
        assert "consolidated revenue" in results[0].text
        assert "ERROR" not in results[0].text
