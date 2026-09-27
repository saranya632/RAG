from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import User
from tests.conftest import create_user, make_test_app, token_for, upload

VALID = {"username": "saranya", "email": "saranya@example.com", "password": "TestPassword123"}


@pytest.fixture
def anon(app):
    """A client with no token."""
    return app.test_client()


def register(client, **overrides):
    return client.post("/register", json={**VALID, **overrides})


def login(client, username="saranya", password="TestPassword123"):
    return client.post("/login", json={"username": username, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- POST /register -----------------------------------------------------------

def test_register_success(anon):
    response = register(anon)

    assert response.status_code == 201
    body = response.get_json()
    assert body["message"] == "User registered successfully"
    assert body["user"]["username"] == "saranya"
    assert body["user"]["email"] == "saranya@example.com"
    assert isinstance(body["user"]["id"], int)
    assert "password" not in str(body) and "hash" not in str(body)


def test_password_is_stored_hashed(anon, app):
    register(anon)
    with app.app_context():
        user = User.query.filter_by(username="saranya").one()
        assert user.password_hash != VALID["password"]
        assert user.password_hash.startswith("scrypt:")
        assert user.check_password(VALID["password"])
        assert user.is_active and user.created_at is not None


def test_username_and_email_are_normalised(anon):
    body = register(anon, username="  Saranya ", email="Saranya@Example.COM").get_json()
    assert body["user"]["username"] == "saranya"
    assert body["user"]["email"] == "saranya@example.com"


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"username": None}, "username is required"),
        ({"username": "  "}, "username is required"),
        ({"email": ""}, "email is required"),
        ({"password": None}, "password is required"),
        ({"password": "short"}, "at least 8 characters"),
        ({"password": "x" * 129}, "at most 128 characters"),
        ({"email": "not-an-email"}, "not a valid email"),
        ({"username": "ab"}, "3-50 characters"),
        ({"username": "has space"}, "3-50 characters"),
        ({"username": 123}, "must be a string"),
    ],
)
def test_register_validation(anon, overrides, error):
    response = register(anon, **overrides)
    assert response.status_code == 400
    assert error in response.get_json()["error"]


def test_register_rejects_non_json(anon):
    response = anon.post("/register", data="username=x", content_type="text/plain")
    assert response.status_code == 400


def test_duplicate_username_returns_409(anon):
    register(anon)
    response = register(anon, username="SARANYA", email="other@example.com")
    assert response.status_code == 409
    assert response.get_json()["error"] == "username is already registered"


def test_duplicate_email_returns_409(anon):
    register(anon)
    response = register(anon, username="other", email="SARANYA@example.com")
    assert response.status_code == 409
    assert response.get_json()["error"] == "email is already registered"


# --- POST /login --------------------------------------------------------------

def test_login_success_returns_token(anon):
    register(anon)
    response = login(anon)

    assert response.status_code == 200
    body = response.get_json()
    assert body["message"] == "Login successful"
    assert body["access_token"].count(".") == 2  # header.payload.signature
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["username"] == "saranya"
    assert "password" not in str(body) and "hash" not in str(body)


def test_login_with_email_and_any_case(anon):
    register(anon)
    assert login(anon, username="Saranya@Example.com").status_code == 200
    assert login(anon, username="SARANYA").status_code == 200


def test_wrong_password_and_unknown_user_give_same_401(anon):
    register(anon)
    wrong = login(anon, password="WrongPassword1")
    unknown = login(anon, username="nobody")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json()["error"] == unknown.get_json()["error"] == "Invalid username or password"


def test_login_missing_fields(anon):
    assert anon.post("/login", json={"username": "saranya"}).status_code == 400
    assert anon.post("/login", json={"password": "x"}).status_code == 400
    assert anon.post("/login", data="nope", content_type="text/plain").status_code == 400


def test_inactive_user_cannot_log_in(anon, app):
    create_user(app, username="disabled", email="d@example.com", password="password123",
                is_active=False)
    response = login(anon, username="disabled", password="password123")
    assert response.status_code == 403
    assert response.get_json()["error"] == "This account is disabled"


# --- Protected endpoints ------------------------------------------------------

def test_me_returns_current_user(anon):
    register(anon)
    token = login(anon).get_json()["access_token"]

    response = anon.get("/me", headers=bearer(token))
    assert response.status_code == 200
    assert response.get_json()["user"]["username"] == "saranya"


@pytest.mark.parametrize("path", ["/upload-pdf", "/chat", "/me"])
def test_protected_endpoints_require_token(anon, path):
    method = anon.get if path == "/me" else anon.post
    response = method(path)
    assert response.status_code == 401
    assert "Authentication required" in response.get_json()["error"]


def test_invalid_token_rejected(anon):
    response = anon.post("/chat", json={"question": "hi"}, headers=bearer("not.a.token"))
    assert response.status_code == 401
    assert response.get_json()["error"] == "Invalid access token"


def test_token_signed_with_other_secret_rejected(app, tmp_path, anon):
    other = create_app(config_overrides={
        "JWT_SECRET_KEY": "a-completely-different-secret-key-of-32-bytes",
        "SQLALCHEMY_DATABASE_URI": "sqlite://", "UPLOAD_FOLDER": str(tmp_path / "u2"),
        "RERANKER_PRELOAD": False,  # only the JWT secret matters here; skip the model
    })
    forged = token_for(other, 1)
    assert anon.post("/chat", json={"question": "hi"}, headers=bearer(forged)).status_code == 401


def test_expired_token_rejected(app, anon):
    user_id = create_user(app)
    token = token_for(app, user_id, expires_delta=timedelta(seconds=-1))

    response = anon.post("/chat", json={"question": "hi"}, headers=bearer(token))
    assert response.status_code == 401
    assert "expired" in response.get_json()["error"]


def test_token_stops_working_when_user_disabled(app, anon):
    user_id = create_user(app)
    token = token_for(app, user_id)
    assert anon.get("/me", headers=bearer(token)).status_code == 200

    with app.app_context():
        db.session.get(User, user_id).is_active = False
        db.session.commit()

    response = anon.get("/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.get_json()["error"] == "User account not found or disabled"


def test_login_token_works_for_upload(anon, sample_pdf_bytes):
    register(anon)
    token = login(anon).get_json()["access_token"]
    anon.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    assert upload(anon, sample_pdf_bytes).status_code == 201


# --- Configuration / infrastructure -------------------------------------------

def test_app_refuses_to_start_without_jwt_secret(tmp_path):
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is not set"):
        create_app(config_overrides={"JWT_SECRET_KEY": "", "UPLOAD_FOLDER": str(tmp_path)})


def test_database_unavailable_returns_503(tmp_path, chroma_service, embedding_service):
    # Nothing listens on port 1, so the connection is refused immediately.
    app = create_app(
        config_overrides={
            "TESTING": True,
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://postgres@127.0.0.1:1/rag_database",
            "JWT_SECRET_KEY": "test-only-jwt-secret-key-at-least-32-bytes-long",
            "RERANKER_PRELOAD": False,
        },
        services={"chroma": chroma_service, "embedding": embedding_service},
    )
    response = app.test_client().post("/register", json=VALID)
    assert response.status_code == 503
    assert response.get_json()["error"] == "The user database is unavailable"
