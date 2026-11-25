"""Ways into the private app: personal access links and the demo mode.

Nobody gets in by just opening the page. A personal access link (one use,
15 minutes) gives a browser a session for one account. The demo link, only
when DEMO_MODE=on, gives each visitor their own pre-filled sandbox.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.access import create_access_link, owner_user, redeem_access_link
from backend.db import create_user
from backend.main import app, get_conn
from backend.sessions import COOKIE_NAME
from backend.transactions import add_expense, connect


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    conn = connect(":memory:")
    app.dependency_overrides[get_conn] = lambda: conn
    yield conn
    app.dependency_overrides.clear()


def open_link(token):
    """What a person does: open the link (GET shows a page), then tap "Sign in" (POST)."""
    browser = TestClient(app)
    browser.get(f"/join/{token}")
    response = browser.post(f"/join/{token}", follow_redirects=False)
    return browser, response


def test_access_link_signs_the_browser_in_to_that_account(conn):
    create_user(conn, user_id="me")
    add_expense(conn, "me", 34.6, "groceries", "2026-11-23", merchant="Esselunga")

    browser, response = open_link(create_access_link(conn, "me"))

    assert response.status_code == 303 and response.headers["location"] == "/"
    cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert [e["merchant"] for e in browser.get("/api/expenses").json()] == ["Esselunga"]


def test_access_link_works_only_once(conn):
    create_user(conn, user_id="me")
    token = create_access_link(conn, "me")
    open_link(token)

    browser, response = open_link(token)

    assert response.status_code == 400
    assert browser.get("/api/expenses").status_code == 401


def test_expired_access_link_is_refused(conn):
    create_user(conn, user_id="me")
    token = create_access_link(conn, "me")
    later = datetime.now(timezone.utc) + timedelta(minutes=16)

    assert redeem_access_link(conn, token, now=later) is None


def test_made_up_access_link_is_refused(conn):
    browser, response = open_link("i-made-this-up")

    assert response.status_code == 400
    assert browser.get("/api/expenses").status_code == 401


def test_access_link_is_stored_hashed(conn):
    create_user(conn, user_id="me")

    token = create_access_link(conn, "me")

    assert token not in [r[0] for r in conn.execute("SELECT token_hash FROM access_links")]


def test_owner_user_is_the_migrated_owner_or_a_new_one(conn):
    first = owner_user(conn)

    assert owner_user(conn) == first
    assert conn.execute("SELECT label FROM users WHERE id = ?", (first,)).fetchone()[0] == "owner"


def test_demo_is_closed_by_default(conn):
    response = TestClient(app).get("/demo", follow_redirects=False)

    assert response.status_code == 404


def test_each_demo_visitor_gets_a_private_prefilled_sandbox(conn, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "on")
    create_user(conn, user_id="me")
    add_expense(conn, "me", 999, "rent", "2026-11-01", merchant="MY REAL RENT")
    guest1, guest2 = TestClient(app), TestClient(app)

    assert guest1.get("/demo", follow_redirects=False).status_code == 303
    guest2.get("/demo")
    guest1.post("/api/expenses", json={"amount": 5, "category": "other", "date": "2026-11-02", "merchant": "GUEST 1"})

    expenses1 = [e["merchant"] for e in guest1.get("/api/expenses").json()]
    expenses2 = [e["merchant"] for e in guest2.get("/api/expenses").json()]
    assert len(expenses1) > 10  # pre-filled with the demo story
    assert "GUEST 1" in expenses1 and "GUEST 1" not in expenses2
    assert "MY REAL RENT" not in expenses1 + expenses2
    assert {e["source"] for e in guest2.get("/api/expenses").json()} == {"synthetic"}


def test_me_tells_the_page_who_is_there(conn, monkeypatch):
    anonymous = TestClient(app).get("/api/me").json()
    assert anonymous == {"signed_in": False, "kind": None, "demo_available": False}

    monkeypatch.setenv("DEMO_MODE", "on")
    guest = TestClient(app)
    guest.get("/demo")
    assert guest.get("/api/me").json() == {"signed_in": True, "kind": "guest", "demo_available": True}

    create_user(conn, user_id="me")
    member, _ = open_link(create_access_link(conn, "me"))
    assert member.get("/api/me").json()["kind"] == "member"


def test_demo_link_never_replaces_a_real_accounts_session(conn, monkeypatch):
    # Security review: another website could send a signed-in owner to /demo and
    # swap their session for a sandbox (forced logout). /demo must keep it.
    monkeypatch.setenv("DEMO_MODE", "on")
    create_user(conn, user_id="me")
    add_expense(conn, "me", 34.6, "groceries", "2026-11-23", merchant="Esselunga")
    me, _ = open_link(create_access_link(conn, "me"))

    response = me.get("/demo", follow_redirects=False)

    assert response.status_code == 303 and "set-cookie" not in response.headers
    assert me.get("/api/me").json()["kind"] == "member"
    assert [e["merchant"] for e in me.get("/api/expenses").json()] == ["Esselunga"]


def test_opening_the_demo_again_keeps_the_same_sandbox(conn, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "on")
    visitor = TestClient(app)
    visitor.get("/demo")
    visitor.post("/api/expenses", json={"amount": 5, "category": "other", "date": "2026-11-02", "merchant": "MINE"})

    visitor.get("/demo")

    assert "MINE" in [e["merchant"] for e in visitor.get("/api/expenses").json()]



def test_opening_the_link_does_not_use_it_up(conn):
    # Found for real: Messages/Notes fetch a link to build a preview, which used up
    # the one-time link before the iPhone opened it. Only the button press counts.
    create_user(conn, user_id="me")
    token = create_access_link(conn, "me")
    preview_bot = TestClient(app)

    first, second = preview_bot.get(f"/join/{token}"), preview_bot.get(f"/join/{token}")

    assert first.status_code == second.status_code == 200
    assert "Sign in" in first.text and 'method="post"' in first.text
    assert "set-cookie" not in first.headers
    assert preview_bot.get("/api/expenses").status_code == 401
    browser, response = open_link(token)  # the real person still gets in
    assert response.status_code == 303
    assert browser.get("/api/expenses").status_code == 200


def test_opening_a_used_or_made_up_link_says_so_right_away(conn):
    create_user(conn, user_id="me")
    token = create_access_link(conn, "me")
    open_link(token)

    assert TestClient(app).get(f"/join/{token}").status_code == 400
    assert TestClient(app).get("/join/made-up").status_code == 400
