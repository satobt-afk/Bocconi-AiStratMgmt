"""Database schema and migrations.

The schema version is stored in SQLite itself (`PRAGMA user_version`):
    0 = single-user database (expenses and budgets belong to nobody in particular)
    1 = multi-user: users, sessions, and a user_id on every expense and budget
    2 = personal access links (one use, short-lived) to sign a browser in

`migrate(conn)` brings any database to the latest version. It is safe to run
on every start: an up-to-date database is left untouched. Before changing an
existing file it makes a backup copy, and existing data is kept and given to
an "owner" user (claimed later from the owner's browser).
"""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

SCHEMA_VERSION = 2

USERS = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,             -- random, never chosen by the browser
    created_at TEXT NOT NULL,
    label      TEXT                          -- "owner" for data from before multi-user
)
"""

SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,             -- SHA-256 of the cookie token, never the token itself
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    last_seen  TEXT NOT NULL
)
"""

EXPENSES_V1 = """
CREATE TABLE {name} (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL,
    date         TEXT    NOT NULL,          -- ISO format YYYY-MM-DD
    merchant     TEXT    NOT NULL DEFAULT '',
    source       TEXT    NOT NULL DEFAULT 'manual'
);
"""

BUDGETS_V1 = """
CREATE TABLE {name} (
    user_id     TEXT    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT    NOT NULL,
    limit_cents INTEGER NOT NULL CHECK (limit_cents >= 0),
    PRIMARY KEY (user_id, category)
);
"""

ACCESS_LINKS = """
CREATE TABLE IF NOT EXISTS access_links (
    token_hash TEXT PRIMARY KEY,             -- SHA-256 of the link's secret, never the secret itself
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at    TEXT                          -- set when redeemed: a link works only once
)
"""

INDEXES = "CREATE INDEX IF NOT EXISTS expenses_by_user_and_date ON expenses (user_id, date);"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tables(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def backup_database(conn: sqlite3.Connection, db_path: Union[str, Path]) -> Path:
    """Copy the whole database next to it (budget.backup-20261125-181500.db) and return the copy's path."""
    db_path = Path(db_path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = db_path.with_name(f"{db_path.stem}.backup-{stamp}{db_path.suffix}")
    copy = sqlite3.connect(str(target))
    with copy:
        conn.backup(copy)  # SQLite's own online backup: consistent even while the app is running
    copy.close()
    return target


def migrate(conn: sqlite3.Connection, db_path: Optional[Union[str, Path]] = None) -> dict:
    """Bring the database to SCHEMA_VERSION, one numbered step at a time.

    Returns {"from_version", "to_version", "owner_user_id", "backup"}:
    owner_user_id is set when existing data was given to a new owner user;
    backup is the path of the copy made before changing an existing file database.
    All steps run in one transaction: on any error, nothing changes.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    info = {"from_version": version, "to_version": SCHEMA_VERSION, "owner_user_id": None, "backup": None}
    if version >= SCHEMA_VERSION:
        return info

    has_tables = "expenses" in _tables(conn)
    if has_tables and db_path is not None and str(db_path) != ":memory:":
        info["backup"] = backup_database(conn, db_path)

    conn.execute("PRAGMA foreign_keys = OFF")  # tables may be rebuilt below; re-enabled at the end
    try:
        conn.execute("BEGIN")  # all or nothing; statements one by one (executescript() would commit midway)
        # A step runs if the database is older than it and the target includes it.
        if version < 1 <= SCHEMA_VERSION:
            info["owner_user_id"] = _to_version_1(conn, is_old_single_user=has_tables)
        if version < 2 <= SCHEMA_VERSION:
            conn.execute(ACCESS_LINKS)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    return info


def _to_version_1(conn: sqlite3.Connection, is_old_single_user: bool) -> Optional[str]:
    """0 -> 1: add users and sessions, give every expense and budget a user. Returns the owner id, if any."""
    conn.execute(USERS)
    conn.execute(SESSIONS)
    owner = None
    if is_old_single_user:
        has_data = conn.execute(
            "SELECT (SELECT COUNT(*) FROM expenses) + (SELECT COUNT(*) FROM budgets)"
        ).fetchone()[0] > 0
        if has_data:
            owner = uuid.uuid4().hex
            conn.execute("INSERT INTO users (id, created_at, label) VALUES (?, ?, 'owner')", (owner, _now()))

        # SQLite cannot add a NOT NULL column or change a primary key in place:
        # build the new tables, copy every row, then swap them in.
        conn.execute(EXPENSES_V1.format(name="expenses_v1"))
        if owner:
            conn.execute(
                "INSERT INTO expenses_v1 (id, user_id, amount_cents, category, date, merchant, source) "
                "SELECT id, ?, amount_cents, category, date, merchant, source FROM expenses",
                (owner,),
            )
        conn.execute("DROP TABLE expenses")
        conn.execute("ALTER TABLE expenses_v1 RENAME TO expenses")

        conn.execute(BUDGETS_V1.format(name="budgets_v1"))
        if owner:
            conn.execute(
                "INSERT INTO budgets_v1 (user_id, category, limit_cents) SELECT ?, category, limit_cents FROM budgets",
                (owner,),
            )
        conn.execute("DROP TABLE budgets")
        conn.execute("ALTER TABLE budgets_v1 RENAME TO budgets")
    else:
        conn.execute(EXPENSES_V1.format(name="expenses"))
        conn.execute(BUDGETS_V1.format(name="budgets"))
    conn.execute(INDEXES)
    return owner


def create_user(conn: sqlite3.Connection, user_id: Optional[str] = None, label: Optional[str] = None) -> str:
    """Create a user and return its id: random unless a test gives one. Never take it from a browser."""
    user_id = user_id or uuid.uuid4().hex
    with conn:
        conn.execute("INSERT INTO users (id, created_at, label) VALUES (?, ?, ?)", (user_id, _now(), label))
    return user_id


GUEST_HOURS = 24  # demo sandboxes live this long


def delete_expired_guests(conn: sqlite3.Connection, now: Optional[datetime] = None,
                          hours: int = GUEST_HOURS) -> int:
    """Delete demo sandboxes (label "guest") older than `hours`, with all their data.

    Only "guest" users are ever deleted: real accounts (owner, or created with an
    access link) are kept however old they are. Their expenses, budgets, sessions
    and access links go too (ON DELETE CASCADE). Returns how many were deleted.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    old = [row[0] for row in conn.execute("SELECT id, created_at FROM users WHERE label = 'guest'")
           if datetime.fromisoformat(row[1]) < cutoff]
    with conn:
        conn.execute("PRAGMA foreign_keys = ON")  # needed for the cascade
        conn.executemany("DELETE FROM users WHERE id = ? AND label = 'guest'", [(u,) for u in old])
    return len(old)
