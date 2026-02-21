"""
FinSight AI — Document Routes
POST   /documents/ingest      — Upload, encrypt, extract, chunk, embed, store
GET    /documents/list         — List all ingested documents
GET    /documents/{doc_id}     — Get single document metadata
DELETE /documents/{doc_id}     — Delete document (admin only)
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from config.settings import get_settings
from src.api.dependencies import (
    get_audit_logger,
    get_chroma_store,
    get_current_user,
    get_file_handler,
    require_role,
)
from src.security.auth import UserInDB

router = APIRouter(prefix="/documents", tags=["Documents"])
settings = get_settings()


class IngestResponse(BaseModel):
    doc_id: str
    original_name: str
    file_type: str
    size_bytes: int
    chunk_count: int
    status: str
    message: str


@router.post("/ingest", response_model=IngestResponse, summary="Ingest a financial document")
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(require_role("analyst")),
    file_handler=Depends(get_file_handler),
    audit_logger=Depends(get_audit_logger),
    chroma_store=Depends(get_chroma_store),
):
    """
    Full ingestion pipeline:
    Upload → encrypt → extract text → chunk → embed → store in ChromaDB.
    Requires analyst or admin role.
    """
    from src.ingestion.text_extractor import TextExtractor
    from src.ingestion.chunker import DocumentChunker

    # 1. Validate, encrypt, save
    metadata = await file_handler.handle_upload(
        file=file,
        user=current_user.username,
        max_size_mb=settings.MAX_FILE_SIZE_MB,
    )
    doc_id = metadata["doc_id"]

    # 2. Extract text from decrypted bytes
    raw_bytes = file_handler.get_document_bytes(doc_id)
    extractor = TextExtractor()
    text = extractor.extract(raw_bytes, metadata["file_type"])

    if not text.strip():
        audit_logger.log("ingest_empty_document", current_user.username, {"doc_id": doc_id})
        file_handler.update_metadata(doc_id, {"status": "empty", "chunk_count": 0})
        return IngestResponse(
            doc_id=doc_id,
            original_name=metadata["original_name"],
            file_type=metadata["file_type"],
            size_bytes=metadata["size_bytes"],
            chunk_count=0,
            status="empty",
            message="No extractable text found in document.",
        )

    # 3. Chunk text
    chunker = DocumentChunker(chunk_size=512, chunk_overlap=50)
    chunks = chunker.chunk(
        text,
        base_metadata={
            "doc_id": doc_id,
            "source_file": metadata["original_name"],
            "uploaded_by": current_user.username,
        },
    )

    # 4. Store chunks in ChromaDB (embedding happens inside ChromaStore)
    chunk_count = chroma_store.add_documents(doc_id, chunks)

    # 5. Update metadata with final status
    file_handler.update_metadata(
        doc_id,
        {"status": "indexed", "chunk_count": chunk_count},
    )

    # 6. Audit log
    audit_logger.log(
        "document_ingested",
        current_user.username,
        {
            "doc_id": doc_id,
            "file": metadata["original_name"],
            "chunks": chunk_count,
            "size_bytes": metadata["size_bytes"],
        },
    )

    return IngestResponse(
        doc_id=doc_id,
        original_name=metadata["original_name"],
        file_type=metadata["file_type"],
        size_bytes=metadata["size_bytes"],
        chunk_count=chunk_count,
        status="indexed",
        message=f"Successfully indexed {chunk_count} chunks.",
    )


@router.get("/list", summary="List all ingested documents")
async def list_documents(
    current_user: UserInDB = Depends(get_current_user),
    file_handler=Depends(get_file_handler),
):
    """Return all document metadata records. Accessible by all authenticated users."""
    docs = file_handler.list_documents()
    return {"total": len(docs), "documents": docs}


@router.get("/{doc_id}", summary="Get document metadata by ID")
async def get_document(
    doc_id: str,
    current_user: UserInDB = Depends(get_current_user),
    file_handler=Depends(get_file_handler),
):
    """Retrieve metadata for a specific document."""
    doc = file_handler.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/{doc_id}", summary="Delete document (admin only)")
async def delete_document(
    doc_id: str,
    current_user: UserInDB = Depends(require_role("admin")),
    file_handler=Depends(get_file_handler),
    chroma_store=Depends(get_chroma_store),
    audit_logger=Depends(get_audit_logger),
):
    """
    Delete encrypted file, metadata JSON, and all ChromaDB vectors for a document.
    Requires admin role.
    """
    # Delete from vector store
    deleted_chunks = chroma_store.delete_document(doc_id)

    # Delete encrypted file + metadata
    found = file_handler.delete_document(doc_id)

    if not found and deleted_chunks == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    audit_logger.log(
        "document_deleted",
        current_user.username,
        {"doc_id": doc_id, "chunks_removed": deleted_chunks},
    )

    return {
        "doc_id": doc_id,
        "deleted": True,
        "chunks_removed": deleted_chunks,
        "message": "Document and all associated vectors deleted.",
    }
