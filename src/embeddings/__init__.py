"""V1 embeddings. BGE-small via sentence-transformers in production;
deterministic hash-based stub for offline dev + unit tests."""

from src.embeddings.api import Embedding, EmbeddingService
from src.embeddings.hash_embedder import HashEmbeddingService

__all__ = ["Embedding", "EmbeddingService", "HashEmbeddingService"]
