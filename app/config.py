"""Application configuration, loaded from environment variables (.env)."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


def _get_float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _get_optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


def _get_optional_bool(name: str) -> bool | None:
    value = os.getenv(name, "").strip()
    return _get_bool(name) if value else None


def _resolve_path(value: str) -> str:
    """Resolve relative paths against the project root, not the CWD."""
    path = Path(value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path.resolve())


def _postgres_url() -> str:
    """Build the SQLAlchemy URL from the POSTGRES_* variables.

    URL.create() escapes special characters and omits an empty password
    (e.g. postgresql+psycopg://postgres@localhost:5432/rag_database).
    """
    return URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD") or None,
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=_get_int("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "rag_database"),
    ).render_as_string(hide_password=False)


class Config:
    DEBUG = _get_bool("FLASK_DEBUG")

    UPLOAD_FOLDER = _resolve_path(os.getenv("UPLOAD_FOLDER", "./uploads"))
    # Flask enforces this automatically and raises 413 RequestEntityTooLarge.
    MAX_CONTENT_LENGTH = _get_int("MAX_CONTENT_LENGTH", "52428800")
    # Keep the uploaded PDF on disk after ingestion (false = delete once stored in Chroma).
    KEEP_UPLOADED_FILES = _get_bool("KEEP_UPLOADED_FILES", "true")

    CHUNK_SIZE = _get_int("CHUNK_SIZE", "1000")
    CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", "200")

    CHROMA_PERSIST_DIRECTORY = _resolve_path(
        os.getenv("CHROMA_PERSIST_DIRECTORY", "./data/chroma")
    )
    CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "pdf_documents")

    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "fastembed")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    EMBEDDING_BATCH_SIZE = _get_int("EMBEDDING_BATCH_SIZE", "64")
    # Where local embedding models are downloaded/cached.
    EMBEDDING_CACHE_DIR = _resolve_path(os.getenv("EMBEDDING_CACHE_DIR", "./data/models"))

    # --- Stage 2: retrieval + Qwen via Ollama (/chat) ----------------------
    # Candidate chunks fetched from ChromaDB per question (input to the reranker).
    RETRIEVAL_TOP_K = _get_int("RETRIEVAL_TOP_K", "10")
    # Chunks kept after reranking; only these are sent to Qwen.
    RERANK_TOP_K = _get_int("RERANK_TOP_K", "4")

    # Cross-encoder that scores (question, chunk) pairs. Runs locally via
    # FastEmbed/ONNX and is cached in EMBEDDING_CACHE_DIR. Smaller, faster,
    # English-only alternative: Xenova/ms-marco-MiniLM-L-6-v2 (~80 MB).
    RERANKER_ENABLED = _get_bool("RERANKER_ENABLED", "true")
    RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
    # true = load the model when the app starts, so the first /chat is not slow.
    # false = load it on the first /chat request instead (faster startup).
    RERANKER_PRELOAD = _get_bool("RERANKER_PRELOAD", "true")
    # Cosine-distance cutoff (0 = identical meaning, 2 = opposite). Chunks
    # farther away than this are treated as irrelevant; if none are left, /chat
    # returns 404 without calling the LLM. Empty = no cutoff. Tune it on your
    # own data: the retrieval log line prints the distances.
    RETRIEVAL_MAX_DISTANCE = _get_optional_float("RETRIEVAL_MAX_DISTANCE")
    MAX_QUESTION_LENGTH = _get_int("MAX_QUESTION_LENGTH", "2000")

    # Local LLM served by Ollama (no API key).
    QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen:1.8b")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Low temperature keeps answers close to the retrieved text.
    LLM_TEMPERATURE = _get_float("LLM_TEMPERATURE", "0.1")
    LLM_MAX_TOKENS = _get_int("LLM_MAX_TOKENS", "384")
    # >1 penalises repeated words; stops small models looping on one sentence.
    LLM_REPEAT_PENALTY = _get_float("LLM_REPEAT_PENALTY", "1.15")
    # Tokens the model can see at once (prompt + answer). 4 chunks of ~1000
    # characters plus the instructions fit in ~1500 tokens; bigger values
    # use more RAM.
    OLLAMA_NUM_CTX = _get_int("OLLAMA_NUM_CTX", "4096")
    # Local models can be slow, especially on CPU and on the first request.
    OLLAMA_TIMEOUT_SECONDS = _get_float("OLLAMA_TIMEOUT_SECONDS", "120")
    # Thinking mode, only for models that have one (e.g. qwen3: set false for
    # faster answers). Leave empty for models without it, such as qwen:1.8b.
    QWEN_REASONING = _get_optional_bool("QWEN_REASONING")

    # --- Stage 3: users (PostgreSQL) + JWT authentication -------------------
    SQLALCHEMY_DATABASE_URI = _postgres_url()
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Check a pooled connection is still alive before using it (survives
        # a PostgreSQL restart without a Flask restart).
        "pool_pre_ping": True,
        # Fail fast (-> 503) when PostgreSQL is down, instead of hanging for
        # minutes while Windows retries the connection.
        "connect_args": {"connect_timeout": _get_int("POSTGRES_CONNECT_TIMEOUT", "5")},
    }

    # Signs the tokens. Anyone with this key can forge a login, so it lives
    # only in .env. The app refuses to start without it.
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=_get_int("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60")
    )
    JWT_TOKEN_LOCATION = ["headers"]  # "Authorization: Bearer <token>"
    PASSWORD_MIN_LENGTH = _get_int("PASSWORD_MIN_LENGTH", "8")

    # --- Stage 4: React frontend -----------------------------------------------
    # Browser origins allowed to call this API (comma-separated). The React dev
    # server runs on another port, so the browser treats it as another site.
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
