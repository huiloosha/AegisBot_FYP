"""
Authentication endpoints.

  POST /api/register
      Body: {"full_name": "...", "email": "...", "password": "..."}
      Creates a user (hashed password) and logs them in, returning a token.
      -> 201 {"user": {...}, "token": "...", "expires_at": "..."}

  POST /api/login
      Body: {"email": "...", "password": "..."}
      -> 200 {"user": {...}, "token": "...", "expires_at": "..."}
      -> 401 on bad credentials (without revealing which part was wrong).

  POST /api/logout
      Header: Authorization: Bearer <token>
      Revokes the token. -> 200

  GET  /api/me
      Header: Authorization: Bearer <token>
      -> 200 {"user_id": ..., "full_name": ..., "email": ...} or 401.

The token returned here is what the frontend stores and sends on later requests
(notably POST /api/assessments) so the server derives user_id from the token,
never from the request body.
"""
from flask import Blueprint, jsonify, request

from app.models.db import get_db
from app.routes.auth_helpers import current_user_id
from app.services import auth

auth_bp = Blueprint("auth", __name__, url_prefix="/api")


@auth_bp.route("/register", methods=["POST"])
def register():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    db = get_db()
    try:
        user = auth.create_user(
            db,
            full_name=body.get("full_name", ""),
            email=body.get("email", ""),
            password=body.get("password", ""),
        )
    except ValueError as e:
        # Duplicate email is a conflict; other validation issues are 400.
        msg = str(e)
        status = 409 if "already registered" in msg else 400
        return jsonify({"error": msg}), status

    # Log the new user straight in.
    session = auth.issue_token(db, user["user_id"])
    db.commit()
    return jsonify({"user": user, **session}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    db = get_db()
    user = auth.verify_login(db, body.get("email", ""), body.get("password", ""))
    if user is None:
        return jsonify({"error": "Invalid email or password."}), 401

    session = auth.issue_token(db, user["user_id"])
    db.commit()
    return jsonify({"user": user, **session}), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    from app.routes.auth_helpers import _bearer_token
    token = _bearer_token()
    if not token:
        return jsonify({"error": "No token provided."}), 400
    db = get_db()
    revoked = auth.revoke_token(db, token)
    db.commit()
    return jsonify({"revoked": revoked}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    uid = current_user_id()
    if uid is None:
        return jsonify({"error": "Authentication required."}), 401
    db = get_db()
    row = db.execute(
        "SELECT user_id, full_name, email FROM users WHERE user_id = ?", (uid,)
    ).fetchone()
    if row is None:
        return jsonify({"error": "User not found."}), 404
    return jsonify(dict(row)), 200

@auth_bp.route("/public-config", methods=["GET"])
def public_config():
    """Public frontend configuration. No secrets are exposed here."""
    return jsonify({
        "google_client_id": current_app.config.get("GOOGLE_CLIENT_ID", "")
    }), 200


@auth_bp.route("/google-login", methods=["POST"])
def google_login():
    body = request.get_json(silent=True)
    credential = body.get("credential") if isinstance(body, dict) else None
    client_id = current_app.config.get("GOOGLE_CLIENT_ID", "")

    if not client_id:
        return jsonify({"error": "Google Sign-In is not configured on the server."}), 503
    if not credential:
        return jsonify({"error": "Google credential is required."}), 400

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            credential, google_requests.Request(), client_id
        )
    except Exception:
        return jsonify({"error": "Invalid Google sign-in credential."}), 401

    if not claims.get("email_verified"):
        return jsonify({"error": "Google email is not verified."}), 401

    db = get_db()
    try:
        user = auth.find_or_create_google_user(
            db,
            full_name=claims.get("name", "Google User"),
            email=claims.get("email", ""),
        )
        session = auth.issue_token(db, user["user_id"])
        db.commit()
    except ValueError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"user": user, **session}), 200
