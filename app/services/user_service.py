"""User registration and login checks (PostgreSQL via SQLAlchemy)."""
import logging
import re

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,50}$")
# Deliberately simple: real verification would send a confirmation email.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MAX_LENGTH = 128

# Compared against when the username doesn't exist, so a login for an unknown
# user takes as long as one with a wrong password (no timing hint either way).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


class UserServiceError(Exception):
    """Base error; status_code is the HTTP status the route returns."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)


class UserValidationError(UserServiceError):
    status_code = 400


class DuplicateUserError(UserServiceError):
    status_code = 409


class InvalidCredentialsError(UserServiceError):
    status_code = 401


class InactiveUserError(UserServiceError):
    status_code = 403


def _require_text(value, field: str) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise UserValidationError(f"{field} is required")
    if not isinstance(value, str):
        raise UserValidationError(f"{field} must be a string")
    return value


def register_user(username, email, password, min_password_length: int = 8) -> User:
    username = _require_text(username, "username").strip().lower()
    email = _require_text(email, "email").strip().lower()
    password = _require_text(password, "password")  # not stripped: spaces are allowed

    if not USERNAME_PATTERN.match(username):
        raise UserValidationError(
            "username must be 3-50 characters: letters, digits, '.', '_' or '-'"
        )
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        raise UserValidationError("email is not a valid email address")
    if len(password) < min_password_length:
        raise UserValidationError(
            f"password must be at least {min_password_length} characters"
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise UserValidationError(f"password must be at most {PASSWORD_MAX_LENGTH} characters")

    # Friendly duplicate check first...
    existing = User.query.filter(or_(User.username == username, User.email == email)).first()
    if existing is not None:
        field = "username" if existing.username == username else "email"
        raise DuplicateUserError(f"{field} is already registered")

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError as exc:
        # ...and the UNIQUE constraints as the real guarantee, for the rare
        # case where two identical registrations arrive at the same moment.
        db.session.rollback()
        raise DuplicateUserError("username or email is already registered") from exc

    logger.info("User registered user_id=%s", user.id)
    return user


def authenticate(username, password) -> User:
    """Return the user if the credentials are valid, otherwise raise.

    `username` may also be the account's email address.
    """
    username = _require_text(username, "username").strip().lower()
    password = _require_text(password, "password")

    field = User.email if "@" in username else User.username
    user = User.query.filter(field == username).first()

    if user is None:
        check_password_hash(_DUMMY_HASH, password)  # equalise timing
        raise InvalidCredentialsError("Invalid username or password")
    if not user.check_password(password):
        logger.info("Login failed: wrong password user_id=%s", user.id)
        raise InvalidCredentialsError("Invalid username or password")
    # Checked after the password, so the response doesn't reveal to a stranger
    # that a disabled account exists.
    if not user.is_active:
        raise InactiveUserError("This account is disabled")

    logger.info("Login succeeded user_id=%s", user.id)
    return user
