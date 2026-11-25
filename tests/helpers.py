"""Shared test helpers: an in-memory database with one test user."""

from backend.db import create_user
from backend.transactions import connect

USER = "test-user"


def new_db():
    """Fresh in-memory database (latest schema) with USER already created."""
    conn = connect(":memory:")
    create_user(conn, user_id=USER)
    return conn
