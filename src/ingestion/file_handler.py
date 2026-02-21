"""
FinSight AI — File Handler
Handles upload validation, encryption-at-rest, metadata storage,
document listing, and deletion.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile, HTTPException, status

from src.security.encryption import encrypt_and_save, load_and_decrypt

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}


class FileHandler:
    def __init__(self, upload_dir: str, processed_dir: str, encryption_key: bytes) -> None:
        self._upload_dir = Path(upload_dir)
        self._processed_dir = Path(processed_dir)
        self._key = encryption_key
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._processed_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    async def handle_upload(
        self,
        file: UploadFile,
        user: str,
        max_size_mb: int = 50,
    ) -> dict[str, Any]:
        """
        Validate → encrypt → save file, write metadata JSON.
        Returns the metadata dict on success.
        """
        # 1. Extension validation
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type '{suffix}' not supported. Allowed: {ALLOWED_EXTENSIONS}",
            )

        # 2. Read bytes
        raw_bytes = await file.read()

        # 3. Size validation
        max_bytes = max_size_mb * 1024 * 1024
        if len(raw_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum size of {max_size_mb} MB.",
            )

        # 4. Generate unique doc_id
        doc_id = str(uuid.uuid4())

        # 5. Encrypt and save to uploads/{doc_id}.enc
        enc_path = self._upload_dir / f"{doc_id}.enc"
        encrypt_and_save(raw_bytes, enc_path, self._key)

        # 6. Write metadata
        metadata: dict[str, Any] = {
            "doc_id": doc_id,
            "original_name": file.filename,
            "file_type": suffix.lstrip("."),
            "size_bytes": len(raw_bytes),
            "uploaded_by": user,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploaded",
            "chunk_count": 0,
        }
        self._save_metadata(doc_id, metadata)

        return metadata

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def list_documents(self) -> list[dict]:
        """Return all document metadata records."""
        docs = []
        for json_path in sorted(self._processed_dir.glob("*.json")):
            try:
                docs.append(json.loads(json_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return docs

    def get_document(self, doc_id: str) -> dict | None:
        """Return metadata for a single document, or None if not found."""
        path = self._processed_dir / f"{doc_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Retrieval (for ingestion pipeline)
    # ------------------------------------------------------------------
    def get_document_bytes(self, doc_id: str) -> bytes:
        """Load and decrypt a document's raw bytes."""
        enc_path = self._upload_dir / f"{doc_id}.enc"
        return load_and_decrypt(enc_path, self._key)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------
    def delete_document(self, doc_id: str) -> bool:
        """Remove encrypted file and metadata JSON. Returns True if found."""
        enc_path = self._upload_dir / f"{doc_id}.enc"
        meta_path = self._processed_dir / f"{doc_id}.json"
        found = False
        for p in (enc_path, meta_path):
            if p.exists():
                p.unlink()
                found = True
        return found

    # ------------------------------------------------------------------
    # Metadata update (called by ingestion pipeline after chunking)
    # ------------------------------------------------------------------
    def update_metadata(self, doc_id: str, updates: dict) -> None:
        """Merge updates into an existing metadata record."""
        path = self._processed_dir / f"{doc_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Metadata not found for doc_id: {doc_id}")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata.update(updates)
        self._save_metadata(doc_id, metadata)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _save_metadata(self, doc_id: str, metadata: dict) -> None:
        path = self._processed_dir / f"{doc_id}.json"
        path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
