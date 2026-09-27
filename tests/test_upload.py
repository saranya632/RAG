import os
import uuid

import pytest

from app.services import ChromaStorageError, ChunkingService, PDFProcessingError, PDFService
from tests.conftest import EMBEDDING_DIM, upload
from tests.pdf_factory import make_pdf, make_sample_pdf


# --- API: success -------------------------------------------------------------

def test_valid_pdf_upload_returns_201(client, sample_pdf_bytes):
    response = upload(client, sample_pdf_bytes)

    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True
    assert body["message"] == "PDF uploaded and processed successfully"
    assert body["filename"] == "sample.pdf"
    assert body["page_count"] == 3
    assert body["chunk_count"] > 3
    uuid.UUID(body["document_id"])  # valid UUID


def test_response_does_not_contain_pdf_text(client, sample_pdf_bytes):
    body = upload(client, sample_pdf_bytes).get_json()
    assert set(body) == {"success", "message", "document_id", "filename", "page_count", "chunk_count"}
    assert "enterprise retrieval" not in str(body)


def test_pdf_stored_under_server_generated_name(client, app, sample_pdf_bytes):
    body = upload(client, sample_pdf_bytes, filename="../../evil name.pdf").get_json()
    stored = os.listdir(app.config["UPLOAD_FOLDER"])
    assert stored == [f"{body['document_id']}.pdf"]
    assert body["filename"] == "evil_name.pdf"


def test_document_ids_are_unique(client, sample_pdf_bytes):
    ids = {upload(client, sample_pdf_bytes).get_json()["document_id"] for _ in range(3)}
    assert len(ids) == 3


def test_octet_stream_content_type_accepted_for_real_pdf(client, sample_pdf_bytes):
    # PowerShell's Invoke-RestMethod -Form sends application/octet-stream.
    response = upload(client, sample_pdf_bytes, content_type="application/octet-stream")
    assert response.status_code == 201


# --- API: validation errors ---------------------------------------------------

def test_missing_file_returns_400(client):
    response = upload(client, None)
    assert response.status_code == 400
    assert response.get_json() == {"success": False, "error": "No PDF file provided"}


def test_empty_filename_returns_400(client, sample_pdf_bytes):
    response = upload(client, sample_pdf_bytes, filename="")
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_non_pdf_extension_returns_415(client):
    response = upload(client, b"hello", filename="notes.txt", content_type="text/plain")
    assert response.status_code == 415
    assert response.get_json()["success"] is False


def test_wrong_content_type_returns_415(client, sample_pdf_bytes):
    response = upload(client, sample_pdf_bytes, content_type="image/png")
    assert response.status_code == 415


def test_fake_pdf_content_returns_415(client):
    response = upload(client, b"this is not really a pdf", filename="fake.pdf")
    assert response.status_code == 415
    assert "not a valid PDF" in response.get_json()["error"]


def test_empty_file_returns_400(client):
    response = upload(client, b"")
    assert response.status_code == 400
    assert response.get_json()["error"] == "Uploaded file is empty"


def test_oversized_file_returns_413(client, app):
    too_big = b"%PDF-1.4\n" + b"0" * (app.config["MAX_CONTENT_LENGTH"] + 1)
    response = upload(client, too_big)
    assert response.status_code == 413
    assert response.get_json()["success"] is False


def test_corrupt_pdf_returns_500_without_stack_trace(client, app, chroma_service):
    response = upload(client, b"%PDF-1.4\ngarbage that is not a pdf structure")
    assert response.status_code == 500
    body = response.get_json()
    assert body["success"] is False
    assert "Traceback" not in body["error"]
    assert chroma_service.count() == 0
    assert os.listdir(app.config["UPLOAD_FOLDER"]) == []


def test_pdf_without_text_returns_500(client):
    response = upload(client, make_pdf([[], []]))
    assert response.status_code == 500
    assert "no extractable text" in response.get_json()["error"]


def test_chroma_failure_returns_500(client, app, sample_pdf_bytes, monkeypatch):
    chroma = app.extensions["ingestion"]["chroma"]

    def boom(*args, **kwargs):
        raise ChromaStorageError("disk full")

    monkeypatch.setattr(chroma, "add_documents", boom)
    response = upload(client, sample_pdf_bytes)
    assert response.status_code == 500
    assert response.get_json() == {
        "success": False,
        "error": "Failed to store the document in the vector database",
    }


# --- Services -------------------------------------------------------------------

@pytest.fixture
def pdf_path(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(make_sample_pdf(page_count=10, lines_per_page=20))
    return str(path)


def test_pdf_text_extraction_preserves_pages(pdf_path):
    pages = PDFService().load_pdf(pdf_path, "doc-1", "doc.pdf")

    assert len(pages) == 10
    assert [p.metadata["page_number"] for p in pages] == list(range(1, 11))
    assert "Page 3 line 1" in pages[2].page_content
    for page in pages:
        assert page.metadata["document_id"] == "doc-1"
        assert page.metadata["filename"] == "doc.pdf"
        assert page.metadata["source"] == "doc.pdf"


def test_pdf_extraction_error_is_wrapped(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 broken")
    with pytest.raises(PDFProcessingError):
        PDFService().load_pdf(str(bad), "doc-1", "bad.pdf")


def test_chunk_generation_respects_size(pdf_path):
    pages = PDFService().load_pdf(pdf_path, "doc-1", "doc.pdf")
    chunks = ChunkingService(chunk_size=500, chunk_overlap=100).split_documents(pages)

    assert len(chunks) > len(pages)
    assert all(len(c.page_content) <= 500 for c in chunks)


def test_chunk_metadata_generation(pdf_path):
    pages = PDFService().load_pdf(pdf_path, "doc-1", "doc.pdf")
    chunks = ChunkingService(chunk_size=500, chunk_overlap=100).split_documents(pages)

    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.metadata["document_id"] == "doc-1"
        assert chunk.metadata["filename"] == "doc.pdf"
        assert chunk.metadata["source"] == "doc.pdf"
        assert 1 <= chunk.metadata["page_number"] <= 10
        assert f"Page {chunk.metadata['page_number']} line" in chunk.page_content


def test_chunking_rejects_invalid_config():
    with pytest.raises(ValueError):
        ChunkingService(chunk_size=100, chunk_overlap=100)


# --- ChromaDB ---------------------------------------------------------------------

def test_chromadb_insertion_and_record_count(client, chroma_service, sample_pdf_bytes):
    body = upload(client, sample_pdf_bytes).get_json()
    doc_id = body["document_id"]

    stored = chroma_service.collection.get(
        where={"document_id": doc_id}, include=["metadatas", "documents", "embeddings"]
    )
    assert chroma_service.count() == body["chunk_count"]
    assert len(stored["ids"]) == body["chunk_count"]
    assert sorted(stored["ids"]) == sorted(f"{doc_id}_{i}" for i in range(body["chunk_count"]))
    assert all(len(e) == EMBEDDING_DIM for e in stored["embeddings"])
    assert all(doc.strip() for doc in stored["documents"])


def test_chromadb_metadata(client, chroma_service, sample_pdf_bytes):
    body = upload(client, sample_pdf_bytes).get_json()
    metadatas = chroma_service.get_document_chunks(body["document_id"])["metadatas"]

    for meta in metadatas:
        assert meta["document_id"] == body["document_id"]
        assert meta["filename"] == "sample.pdf"
        assert meta["source"] == "sample.pdf"
        assert meta["page_number"] in (1, 2, 3)
        assert isinstance(meta["chunk_index"], int)
        assert meta["uploaded_at"]
        assert meta["file_size"] == len(sample_pdf_bytes)
        assert meta["content_type"] == "application/pdf"
    assert {m["page_number"] for m in metadatas} == {1, 2, 3}


def test_multiple_documents_do_not_overwrite_each_other(client, chroma_service, sample_pdf_bytes):
    first = upload(client, sample_pdf_bytes).get_json()
    second = upload(client, make_sample_pdf(page_count=1, lines_per_page=10)).get_json()

    assert chroma_service.count(first["document_id"]) == first["chunk_count"]
    assert chroma_service.count(second["document_id"]) == second["chunk_count"]
    assert chroma_service.count() == first["chunk_count"] + second["chunk_count"]
