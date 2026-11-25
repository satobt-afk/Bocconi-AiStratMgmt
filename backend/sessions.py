"""Server-side sessions: who is the browser making this request?

A session is a random token (32 bytes from `secrets`, the OS's cryptographic
random source). The browser keeps it in a cookie; the database keeps only its
SHA-256 hash, so a leaked database does not leak usable sessions.

The browser never says who it is: the server looks the token up. A missing,
made-up or deleted token means "nobody", never another user.

Cookie settings:
    HttpOnly  page JavaScript cannot read it (an XSS bug cannot steal it)
    SameSite  "lax": not sent with POSTs coming from other websites (CSRF)
    Secure    only sent over HTTPS; on when APP_ENV=production (the local
              dev server runs over plain http, where a Secure cookie is dropped)
"""

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

COOKIE_NAME = "session"
SESSION_DAYS = 365  # stays signed in on the same browser between visits


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_session(conn: sqlite3.Connection, user_id: str) -> str:
    """Open a session for user_id and return the token to put in the cookie (shown only once)."""
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, last_seen) VALUES (?, ?, ?, ?)",
            (_hash(token), user_id, _now(), _now()),
        )
    return token


def user_for_token(conn: sqlite3.Connection, token: Optional[str]) -> Optional[str]:
    """The user a token belongs to, or None for a missing, unknown or revoked token."""
    if not token:
        return None
    row = conn.execute("SELECT user_id FROM sessions WHERE token_hash = ?", (_hash(token),)).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (_now(), _hash(token)))
    return row[0]


def revoke(conn: sqlite3.Connection, token: str) -> None:
    with conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))


def cookie_settings() -> dict:
    """Keyword arguments for FastAPI's response.set_cookie()."""
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "secure": os.environ.get("APP_ENV") == "production",
        "max_age": SESSION_DAYS * 24 * 3600,
        "path": "/",
    }
