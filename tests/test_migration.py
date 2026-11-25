"""Tests for the SQLite migration to multi-user (schema version 0 -> 1).

Version 0 = the single-user database we had until now.
Version 1 = every expense and budget belongs to a user.
Existing data must never be lost: it is backed up first, then given to an "owner" user.
"""

import sqlite3

import pytest

from backend.db import SCHEMA_VERSION, migrate

# The exact single-user schema from before (version 0)
V0_SCHEMA = """
CREATE TABLE expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL,
    date         TEXT    NOT NULL,
    merchant     TEXT    NOT NULL DEFAULT '',
    source       TEXT    NOT NULL DEFAULT 'manual'
);
CREATE TABLE budgets (
    category    TEXT PRIMARY KEY,
    limit_cents INTEGER NOT NULL CHECK (limit_cents >= 0)
);
"""


def v0_database(path, with_data=True):
    conn = sqlite3.connect(str(path))
    conn.executescript(V0_SCHEMA)
    if with_data:
        conn.executemany(
            "INSERT INTO expenses (amount_cents, category, date, merchant, source) VALUES (?, ?, ?, ?, ?)",
            [(40000, "rent", "2026-11-01", "Rent", "manual"),
             (3460, "groceries", "2026-11-23", "Esselunga", "receipt"),
             (2000, "leisure", "2026-10-15", "Cinema", "synthetic")],
        )
        conn.executemany("INSERT INTO budgets VALUES (?, ?)", [("rent", 40000), ("groceries", 15000)])
    conn.commit()
    return conn


def rows(conn, sql):
    return [tuple(r) for r in conn.execute(sql).fetchall()]


def test_fresh_database_gets_the_multi_user_schema_without_any_user():
    conn = sqlite3.connect(":memory:")

    info = migrate(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 1
    assert info["owner_user_id"] is None
    assert rows(conn, "SELECT COUNT(*) FROM users") == [(0,)]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "sessions", "expenses", "budgets"} <= tables


def test_existing_data_is_kept_and_given_to_an_owner_user(tmp_path):
    conn = v0_database(tmp_path / "budget.db")
    before = rows(conn, "SELECT id, amount_cents, category, date, merchant, source FROM expenses ORDER BY id")

    info = migrate(conn, db_path=tmp_path / "budget.db")

    owner = info["owner_user_id"]
    assert owner
    assert rows(conn, "SELECT id, amount_cents, category, date, merchant, source FROM expenses ORDER BY id") == before
    assert rows(conn, "SELECT DISTINCT user_id FROM expenses") == [(owner,)]
    assert rows(conn, "SELECT user_id, category, limit_cents FROM budgets ORDER BY category") == [
        (owner, "groceries", 15000), (owner, "rent", 40000)]
    assert rows(conn, "SELECT label FROM users WHERE id = '%s'" % owner) == [("owner",)]


def test_a_backup_of_the_old_database_is_made_first(tmp_path):
    conn = v0_database(tmp_path / "budget.db")

    info = migrate(conn, db_path=tmp_path / "budget.db")

    backup = sqlite3.connect(str(info["backup"]))
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 0  # the untouched old version
    assert rows(backup, "SELECT COUNT(*) FROM expenses") == [(3,)]
    assert (tmp_path / "budget.db").exists()  # the original file is migrated, never deleted


def test_running_the_migration_twice_changes_nothing(tmp_path):
    conn = v0_database(tmp_path / "budget.db")
    first = migrate(conn, db_path=tmp_path / "budget.db")

    second = migrate(conn, db_path=tmp_path / "budget.db")

    assert second == {"from_version": 1, "to_version": 1, "owner_user_id": None, "backup": None}
    assert rows(conn, "SELECT COUNT(*) FROM users") == [(1,)]
    assert rows(conn, "SELECT COUNT(*) FROM expenses") == [(3,)]
    assert first["owner_user_id"]


def test_old_database_without_data_gets_no_owner(tmp_path):
    conn = v0_database(tmp_path / "budget.db", with_data=False)

    info = migrate(conn, db_path=tmp_path / "budget.db")

    assert info["owner_user_id"] is None
    assert rows(conn, "SELECT COUNT(*) FROM users") == [(0,)]


def test_new_expenses_cannot_be_ownerless():
    conn = sqlite3.connect(":memory:")
    migrate(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO expenses (amount_cents, category, date) VALUES (100, 'other', '2026-11-01')")


def test_expenses_must_belong_to_an_existing_user():
    conn = sqlite3.connect(":memory:")
    migrate(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO expenses (user_id, amount_cents, category, date) VALUES ('nobody', 100, 'other', '2026-11-01')"
        )


def test_two_users_can_each_have_a_budget_for_the_same_category():
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    conn.executemany("INSERT INTO users (id, created_at) VALUES (?, '2026-11-25')", [("a",), ("b",)])

    conn.executemany("INSERT INTO budgets (user_id, category, limit_cents) VALUES (?, 'rent', ?)",
                     [("a", 40000), ("b", 55000)])

    assert rows(conn, "SELECT user_id, limit_cents FROM budgets ORDER BY user_id") == [("a", 40000), ("b", 55000)]


def test_a_failed_migration_leaves_the_old_database_untouched(tmp_path):
    conn = v0_database(tmp_path / "budget.db")
    conn.execute("CREATE TABLE expenses_v1 (x)")  # makes the migration fail halfway
    conn.commit()

    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, db_path=tmp_path / "budget.db")

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert rows(conn, "SELECT COUNT(*) FROM expenses") == [(3,)]
    assert "users" not in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
