"""Sessions and isolation through the real API (no dependency overrides for the user).

Each TestClient is a separate "browser" with its own cookie jar. A browser is
somebody only if it holds a valid session cookie issued by the server.
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from backend.db import create_user
from backend.main import app, get_conn, get_model
from backend.model_client import ModelReply, ToolCall
from backend.sessions import COOKIE_NAME, cookie_settings, new_session, user_for_token
from backend.transactions import connect

DATA_ENDPOINTS = [
    ("get", "/api/status"), ("get", "/api/expenses"), ("get", "/api/budgets"), ("get", "/api/daily"),
    ("get", "/api/year"), ("get", "/api/tips"),
]


@pytest.fixture
def conn():
    conn = connect(":memory:")
    app.dependency_overrides[get_conn] = lambda: conn
    yield conn
    app.dependency_overrides.clear()


def browser_for(conn, user_id):
    """A browser holding a valid session for user_id (as if it had used its invitation link)."""
    create_user(conn, user_id=user_id)
    browser = TestClient(app)
    browser.cookies.set(COOKIE_NAME, new_session(conn, user_id))
    return browser


@pytest.mark.parametrize("method, path", DATA_ENDPOINTS + [("post", "/api/expenses"), ("put", "/api/budgets/rent"),
                                                          ("post", "/api/chat"), ("post", "/api/receipts/scan")])
def test_without_a_session_every_data_endpoint_is_refused(conn, method, path):
    response = getattr(TestClient(app), method)(path, **({"json": {}} if method != "get" else {}))

    assert response.status_code == 401


def test_a_made_up_cookie_is_refused(conn):
    browser = TestClient(app)
    browser.cookies.set(COOKIE_NAME, "i-made-this-up")

    assert browser.get("/api/expenses").status_code == 401


def test_the_health_check_and_the_page_stay_public(conn):
    assert TestClient(app).get("/health").status_code == 200
    assert TestClient(app).get("/").status_code == 200


def test_two_users_only_ever_see_their_own_data(conn):
    alice, bob = browser_for(conn, "alice"), browser_for(conn, "bob")
    alice.put("/api/budgets/restaurant", json={"amount": 60})
    alice.post("/api/expenses", json={"amount": 75, "category": "restaurant", "date": "2026-11-10", "merchant": "Luini"})
    bob.post("/api/expenses", json={"amount": 12, "category": "transport", "date": "2026-11-10", "merchant": "Bus"})

    assert [e["merchant"] for e in alice.get("/api/expenses").json()] == ["Luini"]
    assert [e["merchant"] for e in bob.get("/api/expenses").json()] == ["Bus"]
    assert bob.get("/api/budgets").json()["restaurant"] == 0
    assert bob.get("/api/status", params={"month": "2026-11"}).json()["spent"] == 12
    assert alice.get("/api/status", params={"month": "2026-11"}).json()["spent"] == 75
    assert bob.get("/api/daily", params={"month": "2026-11"}).json()["total_budget"] == 0
    assert bob.get("/api/year", params={"year": 2026}).json()["months"][10]["spent"] == 12
    assert bob.get("/api/tips").json() == {"tips": []}


def test_a_user_id_sent_by_the_browser_is_ignored(conn):
    alice, bob = browser_for(conn, "alice"), browser_for(conn, "bob")
    alice.post("/api/expenses", json={"amount": 75, "category": "restaurant", "date": "2026-11-10"})

    # Bob tries to read and write Alice's data by naming her
    assert bob.get("/api/expenses", params={"user_id": "alice"}).json() == []
    bob.post("/api/expenses", json={"amount": 1, "category": "other", "date": "2026-11-10", "user_id": "alice"})

    assert len(alice.get("/api/expenses").json()) == 1
    assert len(bob.get("/api/expenses").json()) == 1


class FakeModel:
    def __init__(self):
        self.sent = []

    def chat(self, messages, tools):
        self.sent.append([dict(m) for m in messages])
        if len(self.sent) == 1:
            return ModelReply("", [ToolCall("c0", "get_budget_status", {})])
        return ModelReply("ok")


def test_the_coach_only_reads_the_signed_in_users_data(conn):
    alice, bob = browser_for(conn, "alice"), browser_for(conn, "bob")
    alice.post("/api/expenses", json={"amount": 490, "category": "rent", "date": "2026-11-01"})
    model = FakeModel()
    app.dependency_overrides[get_model] = lambda: model

    assert bob.post("/api/chat", json={"message": "How am I doing?"}).status_code == 200

    assert "490" not in model.sent[1][-1]["content"]


def test_the_raw_token_is_never_stored(conn):
    create_user(conn, user_id="alice")

    token = new_session(conn, "alice")

    stored = [r[0] for r in conn.execute("SELECT token_hash FROM sessions")]
    assert token not in stored
    assert stored == [hashlib.sha256(token.encode()).hexdigest()]
    assert user_for_token(conn, token) == "alice"


def test_tokens_are_long_and_unique(conn):
    create_user(conn, user_id="alice")

    tokens = {new_session(conn, "alice") for _ in range(50)}

    assert len(tokens) == 50
    assert all(len(t) >= 43 for t in tokens)  # 32 random bytes, base64url


def test_cookie_is_httponly_lax_and_secure_only_in_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    local = cookie_settings()
    monkeypatch.setenv("APP_ENV", "production")
    production = cookie_settings()

    assert local["httponly"] is True and local["samesite"] == "lax" and local["secure"] is False
    assert production["secure"] is True
    assert production["max_age"] >= 30 * 24 * 3600
