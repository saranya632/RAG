"""Embedding generation, independent of the LLM.

Wraps any LangChain `Embeddings` implementation so the model/provider can be
swapped via configuration without touching routes or other services.
"""
import logging

from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embeddings cannot be generated."""


def _build_embeddings(
    provider: str, model_name: str, batch_size: int, cache_dir: str | None
) -> Embeddings:
    provider = provider.lower()
    if provider == "fastembed":
        # Local ONNX model; downloaded once and cached, no API key required.
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

        return FastEmbedEmbeddings(
            model_name=model_name, batch_size=batch_size, cache_dir=cache_dir
        )
    if provider == "huggingface":
        # Optional: requires `pip install langchain-huggingface sentence-transformers`.
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=model_name, cache_folder=cache_dir)
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")


class EmbeddingService:
    def __init__(
        self,
        provider: str,
        model_name: str,
        batch_size: int = 64,
        cache_dir: str | None = None,
        embeddings: Embeddings | None = None,
    ):
        self.provider = provider
        self.model_name = model_name
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        # An Embeddings instance can be injected (e.g. in tests); otherwise the
        # model is created lazily on first use so app startup stays fast.
        self._embeddings = embeddings

    @property
    def embeddings(self) -> Embeddings:
        if self._embeddings is None:
            logger.info(
                "Loading embedding model provider=%s model=%s",
                self.provider, self.model_name,
            )
            self._embeddings = _build_embeddings(
                self.provider, self.model_name, self.batch_size, self.cache_dir
            )
        return self._embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = self.embeddings.embed_documents(texts)
        except Exception as exc:
            raise EmbeddingError("Embedding generation failed") from exc
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"Embedding count mismatch: {len(vectors)} vectors for {len(texts)} texts"
            )
        return [list(map(float, v)) for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query with the same model used for the stored chunks.

        Some models (e.g. BGE) embed queries slightly differently from passages,
        which is why this is a separate call from embed_documents().
        """
        try:
            return list(map(float, self.embeddings.embed_query(text)))
        except Exception as exc:
            raise EmbeddingError("Query embedding failed") from exc
