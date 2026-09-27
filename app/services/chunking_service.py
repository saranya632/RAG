"""Chunking: page-level Documents -> overlapping text chunks with metadata."""
import logging

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class ChunkingService:
    def __init__(self, chunk_size: int, chunk_overlap: int):
        if chunk_size <= 0:
            raise ValueError("CHUNK_SIZE must be positive")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("CHUNK_OVERLAP must be >= 0 and smaller than CHUNK_SIZE")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """Split pages into chunks, preserving page metadata.

        chunk_index is sequential across the whole document (0..n-1), so
        "<document_id>_<chunk_index>" is a unique, deterministic ID.
        """
        chunks = [
            chunk
            for chunk in self._splitter.split_documents(documents)
            if chunk.page_content.strip()
        ]
        for chunk_index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = chunk_index

        logger.info(
            "Chunking complete pages=%d chunks=%d chunk_size=%d chunk_overlap=%d",
            len(documents), len(chunks), self.chunk_size, self.chunk_overlap,
        )
        return chunks
