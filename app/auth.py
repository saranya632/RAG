"""JWT callbacks: how a token maps to a user, and what failed checks return.

Flask-JWT-Extended does the token work (signing, expiry, verification).
These callbacks only plug in our User table and our JSON error format.
"""
from flask import jsonify

from app.extensions import db
from app.models import User


def _unauthorized(message: str):
    return jsonify({"success": False, "error": message}), 401


def register_jwt_callbacks(jwt) -> None:
    @jwt.user_lookup_loader
    def load_user(_jwt_header, jwt_data):
        """Runs on every protected request, after the signature is verified.

        Returning None rejects the request, so a token stops working as soon
        as its user is deleted or disabled, even before the token expires.
        """
        user = db.session.get(User, int(jwt_data["sub"]))
        return user if user is not None and user.is_active else None

    @jwt.user_lookup_error_loader
    def user_not_found(_jwt_header, _jwt_data):
        return _unauthorized("User account not found or disabled")

    @jwt.unauthorized_loader
    def missing_token(_reason):
        return _unauthorized(
            "Authentication required: send the header 'Authorization: Bearer <access_token>'"
        )

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return _unauthorized("Invalid access token")

    @jwt.expired_token_loader
    def expired_token(_jwt_header, _jwt_data):
        return _unauthorized("Access token has expired. Please log in again")
