"""Store and list student expenses in a local SQLite database.

Money is stored as integer cents: floats cannot represent most decimal
amounts exactly (0.1 + 0.2 != 0.3), and budgets must add up to the cent.
"""

import os
import sqlite3
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import List, Optional, Union

from backend.db import migrate

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "budget.db"

CATEGORIES = ("rent", "groceries", "restaurant", "transport", "leisure", "travel", "other")
# Where an expense came from. "synthetic" marks demo data so it is never shown as real.
SOURCES = ("manual", "receipt", "synthetic")

Amount = Union[int, float, str, Decimal]


def default_db_path() -> Path:
    """data/budget.db, unless the BUDGET_DB environment variable points elsewhere (e.g. the demo database)."""
    return Path(os.environ["BUDGET_DB"]) if os.environ.get("BUDGET_DB") else DEFAULT_DB_PATH


def connect(path: Union[str, Path, None] = None) -> sqlite3.Connection:
    """Open the database (":memory:" for tests) and bring it to the latest schema (see db.py)."""
    path = default_db_path() if path is None else path
    # FastAPI may run a request on a different thread than the one that opened it.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    migrate(conn, db_path=path)  # no-op when up to date; backs up an old file before migrating it
    return conn


def to_cents(amount: Amount) -> int:
    """34.6 -> 3460, rounding half up to the nearest cent."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_euros(cents: int) -> float:
    return cents / 100


def check_category(category: str) -> None:
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category {category!r}; expected one of {CATEGORIES}")


def check_month(month: str) -> None:
    """Accept only YYYY-MM, e.g. "2026-11"."""
    try:
        date.fromisoformat(month + "-01")
    except (TypeError, ValueError):
        raise ValueError(f"Month must look like 2026-11, got {month!r}") from None


def add_expense(
    conn: sqlite3.Connection,
    user_id: str,
    amount: Amount,
    category: str,
    expense_date: str,
    merchant: str = "",
    source: str = "manual",
) -> int:
    """Validate and save one expense for `user_id`; return its id."""
    cents = to_cents(amount)
    if cents <= 0:
        raise ValueError("Amount must be greater than 0")
    check_category(category)
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}; expected one of {SOURCES}")
    try:
        day = date.fromisoformat(expense_date)
    except (TypeError, ValueError):
        raise ValueError(f"Date must be a real day in YYYY-MM-DD format, got {expense_date!r}") from None

    with conn:  # commits on success, rolls back on error
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount_cents, category, date, merchant, source) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, cents, category, day.isoformat(), merchant.strip(), source),
        )
    return cursor.lastrowid


def list_expenses(conn: sqlite3.Connection, user_id: str, month: Optional[str] = None) -> List[dict]:
    """The user's expenses, oldest first; only those of `month` (YYYY-MM) if given."""
    query = "SELECT id, amount_cents, category, date, merchant, source FROM expenses WHERE user_id = ?"
    params: tuple = (user_id,)
    if month is not None:
        check_month(month)
        query += " AND substr(date, 1, 7) = ?"
        params = (user_id, month)
    rows = conn.execute(query + " ORDER BY date, id", params).fetchall()
    return [
        {
            "id": r["id"],
            "amount": to_euros(r["amount_cents"]),
            "category": r["category"],
            "date": r["date"],
            "merchant": r["merchant"],
            "source": r["source"],
        }
        for r in rows
    ]


def delete_expense(conn: sqlite3.Connection, user_id: str, expense_id: int) -> bool:
    """Delete one of the user's expenses. Returns False if it does not exist OR belongs to someone else:
    the WHERE on user_id is what stops anyone from deleting another user's expense by changing the id."""
    with conn:
        cursor = conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
    return cursor.rowcount == 1
