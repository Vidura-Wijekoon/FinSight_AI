"""
FinSight AI — Document Chunker
Uses LangChain RecursiveCharacterTextSplitter.
chunk_size=512, overlap=50 (per architecture diagram)
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter


class Chunk:
    """Lightweight chunk container (avoids LangChain Document import in other modules)."""

    def __init__(self, text: str, metadata: dict) -> None:
        self.text = text
        self.metadata = metadata

    def __repr__(self) -> str:
        return f"Chunk(len={len(self.text)}, meta={self.metadata})"


class DocumentChunker:
    """Split extracted text into overlapping chunks with metadata."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk(self, text: str, base_metadata: dict) -> list[Chunk]:
        """
        Split text and attach metadata to each chunk.

        Args:
            text: Plain text to split.
            base_metadata: Dict containing at least 'doc_id' and 'source_file'.

        Returns:
            List of Chunk objects.
        """
        if not text or not text.strip():
            return []

        raw_chunks = self._splitter.split_text(text)
        chunks: list[Chunk] = []

        for idx, chunk_text in enumerate(raw_chunks):
            if not chunk_text.strip():
                continue
            meta = {
                **base_metadata,
                "chunk_index": idx,
                "chunk_count": len(raw_chunks),
                "chunk_size": len(chunk_text),
            }
            chunks.append(Chunk(text=chunk_text, metadata=meta))

        return chunks
