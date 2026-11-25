"""Deleting an expense (to fix mistakes): only ever your own.

This is the first endpoint that acts on ONE expense chosen by its id, so it is
where an IDOR could appear: changing the number in the URL must never let
someone delete another user's expense.
"""

import pytest
from fastapi.testclient import TestClient

from backend.db import create_user
from backend.main import app, get_conn
from backend.sessions import COOKIE_NAME, new_session
from backend.transactions import add_expense, connect, delete_expense, list_expenses


@pytest.fixture
def conn():
    conn = connect(":memory:")
    for user in ("alice", "bob"):
        create_user(conn, user_id=user)
    app.dependency_overrides[get_conn] = lambda: conn
    yield conn
    app.dependency_overrides.clear()


def browser_for(conn, user_id):
    browser = TestClient(app)
    browser.cookies.set(COOKIE_NAME, new_session(conn, user_id))
    return browser


def test_delete_removes_only_that_expense(conn):
    keep = add_expense(conn, "alice", 10, "other", "2026-11-01", merchant="KEEP")
    typo = add_expense(conn, "alice", 1250, "groceries", "2026-11-02", merchant="TYPO")

    assert delete_expense(conn, "alice", typo) is True

    assert [e["id"] for e in list_expenses(conn, "alice")] == [keep]


def test_cannot_delete_someone_elses_expense(conn):
    theirs = add_expense(conn, "alice", 10, "other", "2026-11-01")

    assert delete_expense(conn, "bob", theirs) is False
    assert len(list_expenses(conn, "alice")) == 1


def test_api_deletes_your_own_expense(conn):
    alice = browser_for(conn, "alice")
    created = alice.post("/api/expenses", json={"amount": 1250, "category": "groceries", "date": "2026-11-02"}).json()

    response = alice.delete(f"/api/expenses/{created['id']}")

    assert response.status_code == 204
    assert alice.get("/api/expenses").json() == []


def test_api_changing_the_id_cannot_delete_another_users_expense(conn):
    alice_expense = add_expense(conn, "alice", 34.6, "groceries", "2026-11-23", merchant="Esselunga")
    bob = browser_for(conn, "bob")

    response = bob.delete(f"/api/expenses/{alice_expense}")

    assert response.status_code == 404  # same answer as "does not exist": reveals nothing
    assert [e["merchant"] for e in list_expenses(conn, "alice")] == ["Esselunga"]


def test_api_unknown_id_is_404(conn):
    assert browser_for(conn, "alice").delete("/api/expenses/999").status_code == 404


def test_api_delete_needs_a_session(conn):
    expense = add_expense(conn, "alice", 10, "other", "2026-11-01")

    assert TestClient(app).delete(f"/api/expenses/{expense}").status_code == 401
    assert len(list_expenses(conn, "alice")) == 1


def test_deleting_updates_the_month_status(conn):
    alice = browser_for(conn, "alice")
    created = alice.post("/api/expenses", json={"amount": 1250, "category": "groceries", "date": "2026-11-02"}).json()
    alice.post("/api/expenses", json={"amount": 12.5, "category": "groceries", "date": "2026-11-02"})

    alice.delete(f"/api/expenses/{created['id']}")

    assert alice.get("/api/status", params={"month": "2026-11"}).json()["spent"] == 12.5
