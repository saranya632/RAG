"""POST /chat: validates the question and runs the RAG pipeline."""
import logging
import time

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.routes.upload_routes import error_response
from app.services import (
    ChromaQueryError,
    EmbeddingError,
    LLMServiceError,
    NoRelevantDocumentsError,
)

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat", methods=["POST"])
@jwt_required()  # 401 unless the request carries a valid token of an active user
def chat():
    started = time.perf_counter()

    # --- Validation -------------------------------------------------------
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", 400)

    question = payload.get("question")
    if question is None:
        return error_response("Question is required", 400)
    if not isinstance(question, str):
        return error_response("Invalid question: must be a string", 400)
    question = question.strip()
    if not question:
        return error_response("Question is required", 400)
    max_length = current_app.config["MAX_QUESTION_LENGTH"]
    if len(question) > max_length:
        return error_response(f"Invalid question: longer than {max_length} characters", 400)

    document_id = payload.get("document_id")
    if document_id is not None:
        if not isinstance(document_id, str) or not document_id.strip():
            return error_response("Invalid document_id: must be a non-empty string", 400)
        document_id = document_id.strip()

    # Question text is not logged: it may contain user data.
    logger.info(
        "Chat request received question_chars=%d document_id=%s", len(question), document_id
    )

    # --- RAG pipeline -----------------------------------------------------
    rag = current_app.extensions["rag"]
    try:
        result = rag.answer(question, document_id)
    except NoRelevantDocumentsError as exc:
        return error_response(str(exc), 404)
    except EmbeddingError:
        logger.exception("Query embedding failed")
        return error_response("Failed to process the question", 500)
    except ChromaQueryError:
        logger.exception("ChromaDB query failed")
        return error_response("The document store is temporarily unavailable", 503)
    except LLMServiceError as exc:
        # The message was written for end users; details are only in the log.
        return error_response(str(exc), exc.status_code)
    except Exception:
        logger.exception("Unexpected chat error")
        return error_response("Internal server error while answering the question", 500)

    logger.info(
        "Chat answered sources=%d duration_ms=%.0f",
        len(result["sources"]), (time.perf_counter() - started) * 1000,
    )
    return jsonify({
        "success": True,
        "question": question,
        "answer": result["answer"],
        "sources": result["sources"],
    }), 200
