"""Guard rails before going public: rate limits on the AI, temporary demo sandboxes.

The AI runs on one Mac: a few requests per minute per user keep it usable for
everyone. Demo sandboxes are deleted after 24 h; real accounts never are.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.access import create_access_link
from backend.db import create_user, delete_expired_guests
from backend.limits import RateLimiter
from backend.main import app, get_conn, get_model
from backend.model_client import ModelReply
from backend.transactions import add_expense, connect


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limiter_allows_up_to_the_limit_then_refuses():
    clock = Clock()
    limiter = RateLimiter(clock=clock)

    results = [limiter.allow("alice:chat", limit=3, window=60) for _ in range(4)]

    assert results == [True, True, True, False]


def test_limiter_allows_again_once_the_window_has_passed():
    clock = Clock()
    limiter = RateLimiter(clock=clock)
    for _ in range(3):
        limiter.allow("alice:chat", limit=3, window=60)

    clock.now += 61

    assert limiter.allow("alice:chat", limit=3, window=60) is True


def test_limits_are_per_user():
    limiter = RateLimiter(clock=Clock())
    for _ in range(3):
        limiter.allow("alice:chat", limit=3, window=60)

    assert limiter.allow("bob:chat", limit=3, window=60) is True


# ---------- Through the API ----------

class OkModel:
    def chat(self, messages, tools):
        return ModelReply("ok")

    def read_image(self, prompt, image, schema):
        return {"merchant": "X", "date": "", "total": 5, "category": "other"}


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "on")
    main.limiter.reset()
    conn = connect(":memory:")
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_model] = lambda: OkModel()
    yield conn
    app.dependency_overrides.clear()
    main.limiter.reset()


def guest():
    browser = TestClient(app)
    browser.get("/demo")
    return browser


def member(conn, user_id="me"):
    create_user(conn, user_id=user_id)
    browser = TestClient(app)
    browser.get(f"/join/{create_access_link(conn, user_id)}")
    return browser


def test_guest_coach_is_limited_per_minute(conn):
    visitor = guest()
    limit = main.LIMITS["chat"]["guest"][0]

    codes = [visitor.post("/api/chat", json={"message": "hi"}).status_code for _ in range(limit + 1)]

    assert codes[:limit] == [200] * limit
    assert codes[-1] == 429
    assert "minute" in visitor.post("/api/chat", json={"message": "hi"}).json()["detail"]


def test_one_busy_guest_does_not_block_another(conn):
    first, second = guest(), guest()
    for _ in range(main.LIMITS["chat"]["guest"][0] + 1):
        first.post("/api/chat", json={"message": "hi"})

    assert second.post("/api/chat", json={"message": "hi"}).status_code == 200


def test_members_get_a_higher_coach_limit_than_guests(conn):
    me = member(conn)
    guest_limit = main.LIMITS["chat"]["guest"][0]

    codes = [me.post("/api/chat", json={"message": "hi"}).status_code for _ in range(guest_limit + 1)]

    assert codes == [200] * (guest_limit + 1)


def test_receipt_scans_are_limited_too(conn):
    visitor = guest()
    limit = main.LIMITS["scan"]["guest"][0]

    codes = [visitor.post("/api/receipts/scan", json={"image": "aW1hZ2U="}).status_code for _ in range(limit + 1)]

    assert codes[-1] == 429


def test_new_demo_sandboxes_are_capped(conn, monkeypatch):
    monkeypatch.setitem(main.DEMO_CAPS, "per_hour", 2)

    codes = [TestClient(app).get("/demo", follow_redirects=False).status_code for _ in range(3)]

    assert codes == [303, 303, 429]


# ---------- Deleting old demo sandboxes ----------

def test_guests_older_than_24h_are_deleted_with_all_their_data(conn):
    old = create_user(conn, label="guest")
    add_expense(conn, old, 10, "other", "2026-11-01")
    conn.execute("INSERT INTO budgets (user_id, category, limit_cents) VALUES (?, 'rent', 100)", (old,))
    conn.execute("INSERT INTO sessions VALUES ('h', ?, 'x', 'x')", (old,))
    conn.commit()
    later = datetime.now(timezone.utc) + timedelta(hours=25)

    deleted = delete_expired_guests(conn, now=later)

    assert deleted == 1
    for table in ("users", "expenses", "budgets", "sessions"):
        column = "id" if table == "users" else "user_id"
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (old,)).fetchone()[0] == 0


def test_real_accounts_are_never_deleted_however_old(conn):
    owner = create_user(conn, label="owner")
    grandpa = create_user(conn, label="Grandpa")
    add_expense(conn, owner, 10, "other", "2026-11-01")
    much_later = datetime.now(timezone.utc) + timedelta(days=3650)

    delete_expired_guests(conn, now=much_later)

    remaining = {r[0] for r in conn.execute("SELECT id FROM users")}
    assert {owner, grandpa} <= remaining
    assert conn.execute("SELECT COUNT(*) FROM expenses WHERE user_id = ?", (owner,)).fetchone()[0] == 1


def test_recent_guests_are_kept(conn):
    fresh = create_user(conn, label="guest")

    assert delete_expired_guests(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (fresh,)).fetchone()[0] == 1


def test_a_deleted_guests_cookie_no_longer_works(conn):
    visitor = guest()
    assert visitor.get("/api/expenses").status_code == 200

    delete_expired_guests(conn, now=datetime.now(timezone.utc) + timedelta(hours=25))

    assert visitor.get("/api/expenses").status_code == 401
