"""Inspect what is stored in ChromaDB.

Usage (from the project root):
    python scripts/verify_chroma.py                  # summary of all documents
    python scripts/verify_chroma.py <document_id>    # chunk IDs + metadata for one document

Chunk text is shown only as a short preview, never the full PDF contents.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.services.chroma_service import ChromaService  # noqa: E402

PREVIEW_CHARS = 80


def main() -> None:
    chroma = ChromaService(Config.CHROMA_PERSIST_DIRECTORY, Config.CHROMA_COLLECTION_NAME)
    print(f"Persist directory : {Config.CHROMA_PERSIST_DIRECTORY}")
    print(f"Collection        : {Config.CHROMA_COLLECTION_NAME}")
    print(f"Total records     : {chroma.collection.count()}  (collection.count())")

    if len(sys.argv) < 2:
        metadatas = chroma.collection.get(include=["metadatas"])["metadatas"]
        per_doc = Counter((m["document_id"], m["filename"]) for m in metadatas)
        print(f"Documents         : {len(per_doc)}\n")
        for (doc_id, filename), count in per_doc.items():
            print(f"  {doc_id}  {filename}  chunks={count}")
        return

    document_id = sys.argv[1]
    result = chroma.get_document_chunks(document_id)
    rows = sorted(
        zip(result["ids"], result["metadatas"], result["documents"]),
        key=lambda row: row[1]["chunk_index"],
    )
    print(f"Document ID       : {document_id}")
    print(f"Stored chunks     : {len(rows)}\n")
    for chunk_id, meta, text in rows:
        preview = " ".join(text.split())[:PREVIEW_CHARS]
        print(f"- {chunk_id}")
        print(f"    metadata: {meta}")
        print(f"    preview : {preview}...")


if __name__ == "__main__":
    main()
