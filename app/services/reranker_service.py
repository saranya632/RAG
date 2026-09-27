"""Reranking: score each retrieved chunk against the question, keep the best.

Why a second scoring step?
    ChromaDB compares two vectors that were computed *separately* (one for the
    question, one for the chunk). That is fast, but coarse.
    A cross-encoder reranker reads the question and the chunk *together* in one
    pass and outputs a single relevance score, so it can tell "mentions the
    same words" apart from "actually answers the question".

    It is too slow to run over every chunk in the database, so the pipeline is:
        ChromaDB (fast, coarse)  -> 10 candidates
        Reranker (slow, precise) -> sorted by score -> best 4 go to Qwen

The model runs locally through FastEmbed (ONNX Runtime), the same library that
already produces the embeddings, so no PyTorch or API key is needed.
"""
import logging
import math
import threading

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class RerankerError(Exception):
    """Raised when the reranking model cannot be loaded or cannot score."""


class RerankerService:
    def __init__(
        self,
        model_name: str,
        cache_dir: str | None = None,
        cross_encoder=None,
    ):
        self.model_name = model_name
        self.cache_dir = cache_dir
        # A model can be injected (e.g. a fake in tests); otherwise it is
        # created by load(), once, and then reused by every /chat request.
        self._cross_encoder = cross_encoder
        # Flask serves requests in threads: the lock stops two simultaneous
        # first requests from both loading the ~1 GB model.
        self._lock = threading.Lock()

    def load(self):
        """Load the model once. Later calls return the already-loaded model."""
        if self._cross_encoder is None:
            with self._lock:
                if self._cross_encoder is None:
                    logger.info("Loading reranker model=%s", self.model_name)
                    try:
                        from fastembed.rerank.cross_encoder import TextCrossEncoder

                        self._cross_encoder = TextCrossEncoder(
                            model_name=self.model_name, cache_dir=self.cache_dir
                        )
                    except Exception as exc:
                        raise RerankerError("Failed to load the reranker model") from exc
                    logger.info("Reranker model loaded")
        return self._cross_encoder

    def score(self, question: str, texts: list[str]) -> list[float]:
        """One relevance score per text, in the same order as `texts`.

        Conceptually: [reranker(question, text) for text in texts].
        The cross-encoder returns raw scores (any real number); a sigmoid maps
        them to 0..1 so they are easy to read in logs. It does not change the
        ranking.
        """
        if not texts:
            return []
        cross_encoder = self.load()
        try:
            raw_scores = list(cross_encoder.rerank(question, texts))
        except Exception as exc:
            raise RerankerError("Reranking failed") from exc
        return [1 / (1 + math.exp(-float(raw))) for raw in raw_scores]

    def rerank(self, question: str, documents: list[Document], top_k: int) -> list[Document]:
        """Sort documents by relevance to the question and return the best top_k.

        Each returned document gets its score in metadata["rerank_score"].
        """
        scores = self.score(question, [d.page_content for d in documents])
        for document, score in zip(documents, scores):
            document.metadata["rerank_score"] = score

        ranked = sorted(documents, key=lambda d: d.metadata["rerank_score"], reverse=True)
        return ranked[:top_k]
