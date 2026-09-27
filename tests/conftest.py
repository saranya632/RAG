import io
import sys
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token
from langchain_core.embeddings import DeterministicFakeEmbedding

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402
from app.services import ChromaService, EmbeddingService, RerankerService  # noqa: E402
from tests.pdf_factory import make_sample_pdf  # noqa: E402

EMBEDDING_DIM = 32
TEST_JWT_SECRET = "test-only-jwt-secret-key-at-least-32-bytes-long"


class KeywordCrossEncoder:
    """Stands in for the real cross-encoder: raw score = how often `keyword`
    occurs in the chunk. Same rerank(query, documents) interface as FastEmbed's
    TextCrossEncoder, so tests never download a model."""

    def __init__(self, keyword: str = "Page 1"):
        self.keyword = keyword

    def rerank(self, query, documents):
        return [float(text.count(self.keyword)) for text in documents]


def fake_reranker(keyword: str = "Page 1") -> RerankerService:
    return RerankerService(model_name="fake-reranker", cross_encoder=KeywordCrossEncoder(keyword))


def make_test_app(tmp_path, services: dict, **config):
    """App wired for tests: temp upload folder, temp SQLite user database
    (instead of PostgreSQL), fixed JWT secret, injected services."""
    services = {"reranker": fake_reranker(), **services}
    app = create_app(
        config_overrides={
            "TESTING": True,
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "MAX_CONTENT_LENGTH": 1024 * 1024,
            "KEEP_UPLOADED_FILES": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'users.db'}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "JWT_SECRET_KEY": TEST_JWT_SECRET,
            **config,
        },
        services=services,
    )
    with app.app_context():
        db.create_all()
    return app


def create_user(app, username="tester", email="tester@example.com",
                password="password123", is_active=True) -> int:
    with app.app_context():
        user = User(username=username, email=email, is_active=is_active)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def token_for(app, user_id: int, **kwargs) -> str:
    with app.app_context():
        return create_access_token(identity=str(user_id), **kwargs)


def authenticated_client(app):
    """Test client that sends a valid token with every request."""
    client = app.test_client()
    user_id = create_user(app)
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token_for(app, user_id)}"
    return client


@pytest.fixture
def chroma_service(tmp_path):
    return ChromaService(str(tmp_path / "chroma"), "test_pdf_documents")


@pytest.fixture
def embedding_service():
    # Fake embeddings: tests never download a model or call an external API.
    return EmbeddingService(
        provider="fake",
        model_name="fake-embedding",
        embeddings=DeterministicFakeEmbedding(size=EMBEDDING_DIM),
    )


@pytest.fixture
def app(tmp_path, chroma_service, embedding_service):
    return make_test_app(
        tmp_path, services={"chroma": chroma_service, "embedding": embedding_service}
    )


@pytest.fixture
def client(app):
    return authenticated_client(app)


@pytest.fixture
def sample_pdf_bytes():
    return make_sample_pdf(page_count=3, lines_per_page=40)


def upload(client, data: bytes | None, filename="sample.pdf", content_type="application/pdf"):
    form = {}
    if data is not None:
        form["file"] = (io.BytesIO(data), filename, content_type)
    return client.post("/upload-pdf", data=form, content_type="multipart/form-data")
