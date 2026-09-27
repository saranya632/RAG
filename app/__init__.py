"""Flask application factory."""
import copy
import logging
import os

import click
from flask import Flask, jsonify, render_template
from flask.cli import with_appcontext
from flask_cors import CORS
from sqlalchemy.exc import OperationalError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from app.auth import register_jwt_callbacks
from app.config import BASE_DIR, Config
from app.extensions import db, jwt
from app.services import (
    ChromaService,
    ChunkingService,
    EmbeddingService,
    LLMService,
    PDFService,
    RAGService,
    RerankerError,
    RerankerService,
)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # Third-party request logging (model downloads, telemetry) is noise at INFO.
    for noisy in ("httpx", "httpcore", "huggingface_hub", "chromadb.telemetry"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def create_app(config_overrides: dict | None = None, services: dict | None = None) -> Flask:
    """Create the app.

    `services` lets tests inject replacements for any of the services:
    keys "pdf", "chunking", "embedding", "chroma", "llm", "reranker".
    """
    # Existing templates/ folder at the project root is reused for "/".
    # No static folder: uploaded PDFs are never publicly served.
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=None,
    )
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    # Flask-SQLAlchemy edits this dict in place (e.g. adds SQLite-only
    # connect_args); copy it so one app can never change another's settings.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = copy.deepcopy(
        app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {})
    )

    _configure_logging(app.config["LOG_LEVEL"])
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # --- Users + authentication (PostgreSQL, JWT) -------------------------
    if not app.config.get("JWT_SECRET_KEY"):
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Add a long random value to .env, e.g. the output of: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    db.init_app(app)   # connects lazily: the app starts even if PostgreSQL is down
    jwt.init_app(app)
    register_jwt_callbacks(jwt)
    app.cli.add_command(init_db_command)

    # Let the React frontend (a different origin in development) call the API
    # and send the Authorization header. Only the listed origins are allowed.
    CORS(app, origins=app.config["CORS_ORIGINS"], allow_headers=["Content-Type", "Authorization"])

    services = dict(services or {})
    if "pdf" not in services:
        services["pdf"] = PDFService()
    if "chunking" not in services:
        services["chunking"] = ChunkingService(
            app.config["CHUNK_SIZE"], app.config["CHUNK_OVERLAP"]
        )
    if "embedding" not in services:
        services["embedding"] = EmbeddingService(
            provider=app.config["EMBEDDING_PROVIDER"],
            model_name=app.config["EMBEDDING_MODEL"],
            batch_size=app.config["EMBEDDING_BATCH_SIZE"],
            cache_dir=app.config["EMBEDDING_CACHE_DIR"],
        )
    if "chroma" not in services:
        os.makedirs(app.config["CHROMA_PERSIST_DIRECTORY"], exist_ok=True)
        services["chroma"] = ChromaService(
            app.config["CHROMA_PERSIST_DIRECTORY"], app.config["CHROMA_COLLECTION_NAME"]
        )
    llm = services.pop("llm", None) or LLMService(
        model=app.config["QWEN_MODEL"],
        base_url=app.config["OLLAMA_BASE_URL"],
        temperature=app.config["LLM_TEMPERATURE"],
        max_tokens=app.config["LLM_MAX_TOKENS"],
        repeat_penalty=app.config["LLM_REPEAT_PENALTY"],
        num_ctx=app.config["OLLAMA_NUM_CTX"],
        timeout=app.config["OLLAMA_TIMEOUT_SECONDS"],
        reasoning=app.config["QWEN_REASONING"],
    )
    # One RerankerService for the whole app: the model is loaded once and every
    # /chat request reuses it (loading it per request would add seconds each time).
    reranker = services.pop("reranker", None)
    if reranker is None and app.config["RERANKER_ENABLED"]:
        reranker = RerankerService(
            model_name=app.config["RERANKER_MODEL"],
            cache_dir=app.config["EMBEDDING_CACHE_DIR"],
        )
        if app.config["RERANKER_PRELOAD"]:
            try:
                reranker.load()
            except RerankerError:
                # e.g. no internet for the first download: start anyway and
                # retry on the first /chat request.
                logging.getLogger(__name__).exception("Reranker preload failed")

    app.extensions["ingestion"] = services
    # /chat reuses the same embedding and Chroma instances as /upload-pdf, so
    # questions are embedded with exactly the model that embedded the chunks.
    app.extensions["rag"] = RAGService(
        embedding_service=services["embedding"],
        chroma_service=services["chroma"],
        llm_service=llm,
        reranker=reranker,
        retrieval_top_k=app.config["RETRIEVAL_TOP_K"],
        rerank_top_k=app.config["RERANK_TOP_K"],
        max_distance=app.config["RETRIEVAL_MAX_DISTANCE"],
    )

    from app.routes import auth_bp, chat_bp, upload_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(chat_bp)

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error):
        return jsonify({
            "success": False,
            "error": "File exceeds the maximum allowed upload size "
                     f"({app.config['MAX_CONTENT_LENGTH']} bytes)",
        }), 413

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify({"success": False, "error": error.description}), error.code

    @app.errorhandler(OperationalError)
    def handle_database_down(_error):
        # PostgreSQL unreachable, wrong credentials or missing database.
        app.logger.exception("PostgreSQL connection failed")
        return jsonify({"success": False, "error": "The user database is unavailable"}), 503

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        app.logger.exception("Unhandled error")
        return jsonify({"success": False, "error": "Internal server error"}), 500

    return app


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create missing tables (users) in PostgreSQL. Never drops or alters data."""
    from app import models  # noqa: F401  (registers the User table)

    try:
        db.create_all()
    except OperationalError as exc:
        raise click.ClickException(
            f"Could not connect to PostgreSQL: {exc.orig}\n"
            "Check that PostgreSQL is running and that POSTGRES_DB exists (see README)."
        ) from exc
    click.echo(f"Tables ready: {', '.join(sorted(db.metadata.tables))}")
