"""Tests for the JSON API the frontend calls."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_conn
from backend.transactions import connect


@pytest.fixture
def client():
    conn = connect(":memory:")  # fresh, empty database for every test
    app.dependency_overrides[get_conn] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_categories_are_listed(client):
    response = client.get("/api/categories")

    assert response.status_code == 200
    assert "restaurant" in response.json()["categories"]


def test_added_expense_shows_up_in_month_status(client):
    client.put("/api/budgets/restaurant", json={"amount": 60})

    created = client.post(
        "/api/expenses",
        json={"amount": 75, "category": "restaurant", "date": "2026-11-10", "merchant": "Luini"},
    )
    status = client.get("/api/status", params={"month": "2026-11"}).json()

    assert created.status_code == 201
    assert created.json()["merchant"] == "Luini"
    assert created.json()["source"] == "manual"
    assert status["spent"] == 75
    assert status["categories"]["restaurant"]["over_budget"] is True


def test_expenses_can_be_listed_by_month(client):
    client.post("/api/expenses", json={"amount": 5, "category": "other", "date": "2026-10-31"})
    client.post("/api/expenses", json={"amount": 9, "category": "other", "date": "2026-11-01"})

    november = client.get("/api/expenses", params={"month": "2026-11"}).json()

    assert [e["amount"] for e in november] == [9]


def test_budgets_list_every_category(client):
    client.put("/api/budgets/rent", json={"amount": 400})

    budgets = client.get("/api/budgets").json()

    assert budgets["rent"] == 400
    assert budgets["travel"] == 0
    assert len(budgets) == 7


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": -3, "category": "other", "date": "2026-11-01"},
        {"amount": 3, "category": "casino", "date": "2026-11-01"},
        {"amount": 3, "category": "other", "date": "yesterday"},
        {"category": "other", "date": "2026-11-01"},  # amount missing
    ],
)
def test_invalid_expense_returns_422_with_a_message(client, payload):
    response = client.post("/api/expenses", json=payload)

    assert response.status_code == 422
    assert "detail" in response.json()


def test_invalid_month_returns_422(client):
    assert client.get("/api/status", params={"month": "November"}).status_code == 422


def test_invalid_budget_returns_422(client):
    assert client.put("/api/budgets/casino", json={"amount": 10}).status_code == 422
