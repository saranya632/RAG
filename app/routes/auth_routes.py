"""POST /register, POST /login and GET /me."""
import logging

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, current_user, jwt_required

from app.routes.upload_routes import error_response
from app.services.user_service import UserServiceError, authenticate, register_user

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def _json_body():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


@auth_bp.route("/register", methods=["POST"])
def register():
    payload = _json_body()
    if payload is None:
        return error_response("Request body must be a JSON object", 400)

    try:
        user = register_user(
            payload.get("username"),
            payload.get("email"),
            payload.get("password"),
            min_password_length=current_app.config["PASSWORD_MIN_LENGTH"],
        )
    except UserServiceError as exc:
        return error_response(str(exc), exc.status_code)

    return jsonify({
        "success": True,
        "message": "User registered successfully",
        "user": user.to_dict(),
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    payload = _json_body()
    if payload is None:
        return error_response("Request body must be a JSON object", 400)

    try:
        user = authenticate(payload.get("username"), payload.get("password"))
    except UserServiceError as exc:
        return error_response(str(exc), exc.status_code)

    # The token's subject ("sub") is the user id. It is signed, not encrypted:
    # anyone holding the token can read it, so it carries no secrets.
    access_token = create_access_token(identity=str(user.id))
    expires = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]

    return jsonify({
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": int(expires.total_seconds()),
        "user": {"id": user.id, "username": user.username},
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """Who does this token belong to? Lets the frontend check a stored token."""
    return jsonify({"success": True, "user": current_user.to_dict()}), 200
