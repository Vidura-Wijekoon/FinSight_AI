"""
FinSight AI — Embedding Service
Local embeddings via SentenceTransformers (all-MiniLM-L6-v2, 384-dim).
Implements ChromaDB EmbeddingFunction interface for direct integration.
No external API calls — fully local.
"""
from chromadb import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer


class EmbeddingService(EmbeddingFunction):
    """
    Local SentenceTransformers embedding service.
    Implements chromadb.EmbeddingFunction so it can be passed directly
    to ChromaDB collection creation.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self._dim = self.model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dim

    def __call__(self, input: Documents) -> Embeddings:
        """Called by ChromaDB when adding/upserting documents."""
        return self.model.encode(
            list(input),
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def embed_query(self, input: list[str]) -> list[list[float]]:
        """Called by ChromaDB when query_texts is used."""
        return self.model.encode(
            list(input),
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def embed_single(self, query: str) -> list[float]:
        """Embed a single query string. Used by Retriever."""
        return self.model.encode(
            query,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def name(self) -> str:
        return f"sentence-transformers/{self.model_name}"

    def get_config(self) -> dict:
        return {"model_name": self.model_name}
