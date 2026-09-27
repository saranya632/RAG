"""PostgreSQL tables (SQLAlchemy models)."""
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    # Stored lowercase (see user_service), so uniqueness is case-insensitive.
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    # Never the password itself: a salted one-way hash (Werkzeug uses scrypt).
    password_hash = db.Column(db.String(255), nullable=False)
    # False = account disabled: login and existing tokens stop working.
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        """Public view of the user. Never includes password_hash."""
        return {"id": self.id, "username": self.username, "email": self.email}

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
