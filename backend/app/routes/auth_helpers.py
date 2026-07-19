"""
Auth request helpers.

current_user_id(): read the Bearer token from the Authorization header and
resolve it to a user_id (or None if absent/invalid). Routes use this instead of
trusting a user_id in the request body, so a caller cannot act as another user
by guessing an id.

Usage in a route:
    uid = current_user_id()
    if uid is None:
        return jsonify({"error": "Authentication required."}), 401
"""
from flask import request

from app.models.db import get_db
from app.services import auth


def _bearer_token() -> str | None:
    """Extract the token from an 'Authorization: Bearer <token>' header."""
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    # Also tolerate a bare token without the "Bearer " prefix.
    return header.strip() or None


def current_user_id() -> int | None:
    """Return the authenticated user's id, or None if the request is anonymous
    or the token is invalid/expired."""
    token = _bearer_token()
    if not token:
        return None
    return auth.resolve_token(get_db(), token)
