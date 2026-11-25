"""Tests for storing and listing expenses."""

import pytest

from backend.transactions import add_expense, connect, list_expenses
from tests.helpers import USER, new_db


@pytest.fixture
def conn():
    # ":memory:" = a throwaway database that lives only during the test.
    return new_db()


def test_added_expense_can_be_listed(conn):
    add_expense(conn, USER, 34.60, "groceries", "2026-11-23", merchant="Esselunga")

    expenses = list_expenses(conn, USER)

    assert len(expenses) == 1
    assert expenses[0]["amount"] == 34.60
    assert expenses[0]["category"] == "groceries"
    assert expenses[0]["date"] == "2026-11-23"
    assert expenses[0]["merchant"] == "Esselunga"
    assert expenses[0]["source"] == "manual"


def test_list_can_be_filtered_by_month(conn):
    add_expense(conn, USER, 10, "transport", "2026-10-31")
    add_expense(conn, USER, 20, "transport", "2026-11-01")

    november = list_expenses(conn, USER, month="2026-11")

    assert [e["amount"] for e in november] == [20]


def test_synthetic_expenses_are_labelled(conn):
    add_expense(conn, USER, 5, "other", "2026-11-02", source="synthetic")

    assert list_expenses(conn, USER)[0]["source"] == "synthetic"


@pytest.mark.parametrize(
    "amount, category, date, source",
    [
        (0, "groceries", "2026-11-23", "manual"),        # amount must be > 0
        (-5, "groceries", "2026-11-23", "manual"),       # no negative expenses
        (10, "casino", "2026-11-23", "manual"),          # unknown category
        (10, "groceries", "23/11/2026", "manual"),       # date must be YYYY-MM-DD
        (10, "groceries", "2026-02-30", "manual"),       # date must exist
        (10, "groceries", "2026-11-23", "bank"),         # unknown source
    ],
)
def test_invalid_expenses_are_rejected(conn, amount, category, date, source):
    with pytest.raises(ValueError):
        add_expense(conn, USER, amount, category, date, source=source)
    assert list_expenses(conn, USER) == []
