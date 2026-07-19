"""
Authentication service for AegisBot.

Real password hashing via werkzeug.security (ships with Flask -- no new
dependency). generate_password_hash uses a salted PBKDF2-HMAC-SHA256 digest by
default, so plaintext passwords are never stored.

Sessions are opaque bearer tokens: on login we mint a random token, store it in
the sessions table against the user_id with an expiry, and hand it back. Each
authenticated request presents it in the Authorization header; resolve_token()
turns it back into a user_id. Logout deletes the row.

PROTOTYPE NOTES (state these in the report's limitations):
  - Opaque server-side tokens (not signed JWTs) are used for simplicity and easy
    revocation.
  - Tokens are sent as a Bearer header; over plain HTTP in local dev they are not
    encrypted. A deployment would serve this over HTTPS.
"""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

# How long a login token stays valid.
TOKEN_TTL = timedelta(days=7)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def create_user(db: sqlite3.Connection, full_name: str, email: str,
                password: str) -> dict:
    """Create a user with a hashed password. Caller commits.

    Raises ValueError with a clear message on bad input or duplicate email, so
    the route can map it to a 400/409. The raw password is hashed immediately
    and never stored.
    """
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()

    if not full_name:
        raise ValueError("full_name is required.")
    if "@" not in email or "." not in email:
        raise ValueError("A valid email is required.")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    existing = db.execute(
        "SELECT user_id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if existing is not None:
        raise ValueError("That email is already registered.")

    pw_hash = generate_password_hash(password)
    cur = db.execute(
        """
        INSERT INTO users (full_name, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (full_name, email, pw_hash, _iso(_utcnow())),
    )
    return {"user_id": cur.lastrowid, "full_name": full_name, "email": email}


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
def verify_login(db: sqlite3.Connection, email: str, password: str) -> dict | None:
    """Return the user dict if email+password are valid, else None.

    Uses check_password_hash for a constant-time comparison against the stored
    salted hash. We deliberately return None (not distinct errors) for both
    'no such email' and 'wrong password' so the API doesn't reveal which emails
    are registered.
    """
    email = (email or "").strip().lower()
    row = db.execute(
        "SELECT user_id, full_name, email, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    if row is None or not row["password_hash"]:
        return None
    if not check_password_hash(row["password_hash"], password or ""):
        return None
    return {"user_id": row["user_id"], "full_name": row["full_name"],
            "email": row["email"]}


def issue_token(db: sqlite3.Connection, user_id: int) -> dict:
    """Mint and store a random session token for user_id. Caller commits."""
    token = secrets.token_urlsafe(32)
    now = _utcnow()
    expires = now + TOKEN_TTL
    db.execute(
        """
        INSERT INTO sessions (token, user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (token, user_id, _iso(now), _iso(expires)),
    )
    return {"token": token, "expires_at": _iso(expires)}


def resolve_token(db: sqlite3.Connection, token: str) -> int | None:
    """Return the user_id for a valid, unexpired token, else None.

    An expired token is treated as invalid (and quietly deleted).
    """
    if not token:
        return None
    row = db.execute(
        "SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    if row is None:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (TypeError, ValueError):
        return None
    if expires < _utcnow():
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        # caller may or may not commit; the delete is best-effort cleanup
        return None
    return row["user_id"]


def revoke_token(db: sqlite3.Connection, token: str) -> bool:
    """Delete a session token (logout). Returns True if a row was removed.
    Caller commits."""
    cur = db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    return cur.rowcount > 0
