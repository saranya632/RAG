"""PDF loading: PDF file -> page-level LangChain Documents."""
import logging

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class PDFProcessingError(Exception):
    """Raised when a PDF cannot be read or contains no extractable text."""


class PDFService:
    def load_pdf(self, file_path: str, document_id: str, filename: str) -> list[Document]:
        """Load a PDF into one Document per page, with normalised metadata.

        page_number is 1-based (PyPDFLoader's own "page" metadata is 0-based).
        """
        try:
            pages = PyPDFLoader(file_path).load()
        except Exception as exc:
            raise PDFProcessingError("Unable to read PDF file") from exc

        if not pages:
            raise PDFProcessingError("PDF contains no pages")

        documents = []
        for index, page in enumerate(pages):
            page_number = int(page.metadata.get("page", index)) + 1
            documents.append(
                Document(
                    page_content=page.page_content or "",
                    metadata={
                        "document_id": document_id,
                        "filename": filename,
                        "source": filename,
                        "page_number": page_number,
                    },
                )
            )

        if not any(doc.page_content.strip() for doc in documents):
            raise PDFProcessingError(
                "PDF contains no extractable text (it may be scanned or image-only)"
            )

        logger.info(
            "PDF loaded document_id=%s pages=%d", document_id, len(documents)
        )
        return documents
