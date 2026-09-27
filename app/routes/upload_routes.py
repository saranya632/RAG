"""POST /upload-pdf: validates the upload and orchestrates the ingestion services."""
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from app.services import (
    ChromaStorageError,
    EmbeddingError,
    PDFProcessingError,
)

logger = logging.getLogger(__name__)

upload_bp = Blueprint("upload", __name__)

ALLOWED_EXTENSIONS = {".pdf"}
# Browsers send application/pdf; curl/PowerShell may send octet-stream.
# The real check is the %PDF- magic-byte signature below.
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
PDF_SIGNATURE = b"%PDF-"


def error_response(message: str, status: int):
    return jsonify({"success": False, "error": message}), status


def _file_size(file_storage) -> int:
    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def _has_pdf_signature(file_storage) -> bool:
    # The spec allows up to 1024 bytes of junk before the header.
    head = file_storage.stream.read(1024)
    file_storage.stream.seek(0)
    return PDF_SIGNATURE in head


def _remove_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("Could not remove file path=%s", path, exc_info=True)


@upload_bp.route("/upload-pdf", methods=["POST"])
@jwt_required()  # 401 unless the request carries a valid token of an active user
def upload_pdf():
    started = time.perf_counter()

    # --- Validation -------------------------------------------------------
    if "file" not in request.files:
        return error_response("No PDF file provided", 400)

    upload = request.files["file"]
    original_name = upload.filename or ""
    if not original_name.strip():
        return error_response("No file selected (empty filename)", 400)

    if os.path.splitext(original_name)[1].lower() not in ALLOWED_EXTENSIONS:
        return error_response("Invalid file type: only .pdf files are allowed", 415)

    content_type = (upload.mimetype or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        return error_response(f"Invalid content type: {content_type or 'unknown'}", 415)

    file_size = _file_size(upload)
    if file_size == 0:
        return error_response("Uploaded file is empty", 400)
    if file_size > current_app.config["MAX_CONTENT_LENGTH"]:
        return error_response("File exceeds the maximum allowed upload size", 413)

    if not _has_pdf_signature(upload):
        return error_response("Invalid file: content is not a valid PDF", 415)

    # --- Storage ------------------------------------------------------------
    document_id = str(uuid.uuid4())
    # Display name only; never used as a filesystem path.
    filename = secure_filename(original_name) or "document.pdf"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    stored_path = os.path.join(upload_folder, f"{document_id}.pdf")

    logger.info(
        "Upload received document_id=%s filename=%s size_bytes=%d content_type=%s",
        document_id, filename, file_size, content_type,
    )

    services = current_app.extensions["ingestion"]
    stored_in_chroma = False

    try:
        os.makedirs(upload_folder, exist_ok=True)
        upload.save(stored_path)

        # --- Ingestion pipeline ---------------------------------------------
        pages = services["pdf"].load_pdf(stored_path, document_id, filename)
        chunks = services["chunking"].split_documents(pages)
        if not chunks:
            raise PDFProcessingError("PDF produced no text chunks")

        t0 = time.perf_counter()
        vectors = services["embedding"].embed_documents([c.page_content for c in chunks])
        logger.info(
            "Embeddings generated document_id=%s count=%d model=%s duration_ms=%.0f",
            document_id, len(vectors), services["embedding"].model_name,
            (time.perf_counter() - t0) * 1000,
        )

        ids = services["chroma"].add_documents(
            chunks,
            vectors,
            extra_metadata={
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "file_size": file_size,
                "content_type": content_type,
                "embedding_model": services["embedding"].model_name,
            },
        )
        stored_in_chroma = True

    except PDFProcessingError as exc:
        logger.warning("PDF processing failed document_id=%s reason=%s", document_id, exc)
        _remove_file(stored_path)
        return error_response(f"Failed to process PDF: {exc}", 500)
    except EmbeddingError:
        logger.exception("Embedding failed document_id=%s", document_id)
        _remove_file(stored_path)
        return error_response("Failed to generate embeddings for the PDF", 500)
    except ChromaStorageError:
        logger.exception("ChromaDB insertion failed document_id=%s", document_id)
        _cleanup_chroma(services["chroma"], document_id)
        _remove_file(stored_path)
        return error_response("Failed to store the document in the vector database", 500)
    except Exception:
        logger.exception("Unexpected ingestion error document_id=%s", document_id)
        _remove_file(stored_path)
        return error_response("Internal server error while processing the PDF", 500)
    finally:
        if stored_in_chroma and not current_app.config["KEEP_UPLOADED_FILES"]:
            _remove_file(stored_path)

    logger.info(
        "Upload processed document_id=%s pages=%d chunks=%d records=%d duration_ms=%.0f",
        document_id, len(pages), len(chunks), len(ids),
        (time.perf_counter() - started) * 1000,
    )

    return jsonify({
        "success": True,
        "message": "PDF uploaded and processed successfully",
        "document_id": document_id,
        "filename": filename,
        "page_count": len(pages),
        "chunk_count": len(chunks),
    }), 201


def _cleanup_chroma(chroma_service, document_id: str) -> None:
    try:
        chroma_service.delete_document(document_id)
    except Exception:
        logger.warning("Chroma cleanup failed document_id=%s", document_id, exc_info=True)
