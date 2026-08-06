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

    def test_stored_vectors_differ_between_chunks(self, chroma_store):
        """
        Regression test for the defect where every stored vector was the
        embedding of the empty string.

        ChromaDB applies its embedding_function to `documents`, and this store
        blanks `documents` so no plaintext is persisted. Unless embeddings are
        supplied explicitly, every chunk embeds "" and all vectors become
        identical — which no other test detects, because results are still
        returned and scores still fall between 0 and 1.
        """
        chroma_store.add_documents("doc-vec", make_chunks("doc-vec", [
            "Quarterly revenue rose to $450 million on strong cloud demand.",
            "The board appointed a new chair of the audit committee.",
        ]))

        stored = chroma_store._collection.get(include=["embeddings"])
        first, second = stored["embeddings"][0], stored["embeddings"][1]

        # Embeddings are L2-normalised, so the dot product is the cosine.
        cosine = float(sum(a * b for a, b in zip(first, second, strict=True)))
        assert cosine < 0.99, (
            f"stored vectors are near-identical (cosine {cosine:.4f}); "
            "chunk text was not embedded"
        )

    def test_retrieval_ranks_by_meaning(self, chroma_store, embedding_service):
        """
        The property the whole system depends on: a query must rank the chunk
        that answers it above one that does not. This fails on a tie-break.
        """
        chroma_store.add_documents("doc-rank", make_chunks("doc-rank", [
            "Total revenue for the quarter was $450.2 million, up 14% year over year.",
            "The annual general meeting will be held at the registered office in March.",
            "Employees are reminded to submit expense claims before the month end.",
        ]))

        results = query_text(chroma_store, embedding_service, "how much revenue did we make", top_k=3)
        top_index = results["metadatas"][0][0]["chunk_index"]

        assert top_index == 0, "the revenue chunk did not rank first for a revenue query"

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


@pytest.fixture
def indexed_document(tmp_path, monkeypatch, chroma_store, encryption_key):
    """
    Index a document AND write its encrypted source, which is what the retriever
    actually needs — it reconstructs chunk text by decrypting that file.

    Indexing chunks without the source on disk does not exercise retrieval; it
    only used to appear to, because unreadable sources were silently replaced
    with placeholder text.
    """
    from src.security.encryption import encrypt_and_save

    monkeypatch.chdir(tmp_path)
    uploads = tmp_path / "data" / "uploads"
    uploads.mkdir(parents=True)

    doc_id = "doc-live"
    text = "\n\n".join([
        "The company's annual revenue reached 3.2 billion dollars this year, "
        "driven by sustained demand across every operating region. " * 3,
        "Operating cash flow was positive at 850 million dollars for the period, "
        "comfortably covering capital expenditure and interest. " * 3,
        "The board approved a 500 million dollar share buyback programme, "
        "citing confidence in the long-term trajectory of the business. " * 3,
    ])
    encrypt_and_save(text.encode("utf-8"), uploads / f"{doc_id}.enc", encryption_key)

    chunks = DocumentChunker(chunk_size=512, chunk_overlap=50).chunk(
        text, {"doc_id": doc_id, "source_file": "live.txt", "file_type": "txt"}
    )
    chroma_store.add_documents(doc_id, chunks)
    return doc_id, len(chunks)


class TestRetriever:
    def test_retrieve_returns_relevant_chunks(self, retriever, indexed_document):
        results = retriever.retrieve("annual revenue figures")
        assert len(results) > 0
        assert results[0].score > 0
        # Real reconstructed text, not a placeholder.
        assert "revenue" in results[0].text.lower()

    def test_retrieve_scores_are_valid(self, retriever, indexed_document):
        results = retriever.retrieve("operating cash flow")
        assert results
        for chunk in results:
            assert 0.0 <= chunk.score <= 1.0

    def test_retrieve_respects_top_k(self, retriever, indexed_document):
        _, chunk_count = indexed_document
        assert chunk_count >= 3, "fixture should produce several chunks"
        results = retriever.retrieve("share buyback programme", top_k=2)
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

    def test_binary_format_is_reconstructed_with_the_right_extractor(
        self, tmp_path, monkeypatch, chroma_store, retriever, encryption_key
    ):
        """
        Regression test: chunk metadata omitted file_type and the retriever
        defaulted to 'txt', so container-based formats were decoded as UTF-8 and
        their raw bytes were handed to the model as document text.

        DOCX is used because python-docx can build one; a ZIP container decoded
        as text is the same failure as a PDF decoded as text.
        """
        import io

        import docx

        from src.ingestion.text_extractor import TextExtractor
        from src.security.encryption import encrypt_and_save

        monkeypatch.chdir(tmp_path)
        uploads = tmp_path / "data" / "uploads"
        uploads.mkdir(parents=True)

        document = docx.Document()
        for _ in range(6):
            document.add_paragraph(
                "Consolidated revenue for fiscal year 2024 was 3.20 billion dollars, "
                "an increase of 12.4 per cent year over year."
            )
        buf = io.BytesIO()
        document.save(buf)
        docx_bytes = buf.getvalue()

        doc_id = "doc-docx"
        encrypt_and_save(docx_bytes, uploads / f"{doc_id}.enc", encryption_key)

        extracted = TextExtractor().extract(docx_bytes, "docx")
        # file_type is deliberately absent, reproducing the metadata that
        # ingestion actually wrote. Under the old code this fell back to 'txt'
        # and the ZIP bytes were decoded as UTF-8.
        chunks = DocumentChunker(chunk_size=512, chunk_overlap=50).chunk(
            extracted,
            {"doc_id": doc_id, "source_file": "fy2024.docx"},
        )
        chroma_store.add_documents(doc_id, chunks)

        results = retriever.retrieve("consolidated revenue", top_k=2)

        assert results, "retriever returned no chunks"
        assert "PK" != results[0].text[:2], "raw ZIP container bytes reached the model"
        assert "Consolidated revenue" in results[0].text

    def test_unreadable_source_raises_rather_than_answering(
        self, tmp_path, monkeypatch, chroma_store, retriever
    ):
        """
        A match whose source cannot be decrypted must fail the request. The
        previous behaviour substituted '[ERROR: Could not decrypt...]' as the
        chunk text, which was then formatted into the prompt as evidence and
        could be cited in the answer.
        """
        from src.retrieval.retriever import RetrievalError

        monkeypatch.chdir(tmp_path)  # no data/uploads here, so nothing decrypts
        chroma_store.add_documents(
            "doc-missing", make_chunks("doc-missing", ["Revenue rose sharply this quarter."])
        )

        with pytest.raises(RetrievalError, match="none could be read"):
            retriever.retrieve("revenue", top_k=2)

    def test_unreadable_document_is_excluded_not_substituted(
        self, tmp_path, monkeypatch, chroma_store, retriever, encryption_key
    ):
        """With one readable and one unreadable document, answer from the readable one."""
        from src.security.encryption import encrypt_and_save

        monkeypatch.chdir(tmp_path)
        uploads = tmp_path / "data" / "uploads"
        uploads.mkdir(parents=True)

        readable = "Consolidated revenue for fiscal year 2024 was 3.20 billion dollars. " * 4
        encrypt_and_save(readable.encode("utf-8"), uploads / "doc-ok.enc", encryption_key)
        chroma_store.add_documents(
            "doc-ok",
            DocumentChunker(512, 50).chunk(
                readable, {"doc_id": "doc-ok", "source_file": "ok.txt", "file_type": "txt"}
            ),
        )
        # Indexed, but its encrypted file was never written.
        chroma_store.add_documents(
            "doc-gone",
            make_chunks("doc-gone", ["Consolidated revenue figures are discussed here."]),
        )

        results = retriever.retrieve("consolidated revenue", top_k=4)

        assert results, "readable document should still be returned"
        assert {c.doc_id for c in results} == {"doc-ok"}
        for chunk in results:
            assert "ERROR" not in chunk.text
            assert "Chunk Content Missing" not in chunk.text

    def test_file_type_falls_back_to_the_source_file_extension(self):
        """Indexes written before file_type was recorded must still parse."""
        from src.retrieval.retriever import resolve_file_type

        assert resolve_file_type({"file_type": "pdf"}) == "pdf"
        assert resolve_file_type({"source_file": "report.PDF"}) == "pdf"
        assert resolve_file_type({"file_type": "", "source_file": "a.docx"}) == "docx"

    def test_unknown_file_type_raises_rather_than_guessing(self):
        """Silently assuming 'txt' is what caused the defect this guards."""
        from src.retrieval.retriever import resolve_file_type

        with pytest.raises(ValueError, match="Cannot determine the file type"):
            resolve_file_type({"doc_id": "d1", "source_file": "no_extension"})
