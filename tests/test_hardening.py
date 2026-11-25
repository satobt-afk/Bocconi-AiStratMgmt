"""Hardening before the app is reachable from the internet."""

from fastapi.testclient import TestClient

from backend.main import app


def test_automatic_api_docs_are_not_published():
    client = TestClient(app)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_security_headers_on_every_response():
    for path in ("/", "/api/me", "/join/not-a-real-link"):
        headers = TestClient(app).get(path, follow_redirects=False).headers

        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        # Access links carry a secret in the URL: never send it to another site.
        assert headers["referrer-policy"] == "no-referrer"
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp


def test_hsts_only_in_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    assert "strict-transport-security" not in TestClient(app).get("/").headers

    monkeypatch.setenv("APP_ENV", "production")
    assert "max-age=" in TestClient(app).get("/").headers["strict-transport-security"]


def test_access_link_responses_are_never_cached():
    response = TestClient(app).get("/join/not-a-real-link", follow_redirects=False)

    assert "no-store" in response.headers["cache-control"]
