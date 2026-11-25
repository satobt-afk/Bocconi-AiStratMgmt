"""Tests for the data behind the charts (computed in Python, drawn by the browser)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.budgeting import daily_spending, set_budget
from backend.main import app, get_conn
from backend.transactions import add_expense, connect


@pytest.fixture
def conn():
    conn = connect(":memory:")
    set_budget(conn, "rent", 400)      # fixed cost: due from day 1
    set_budget(conn, "groceries", 300)  # day-to-day: 10 € a day in a 30-day month
    add_expense(conn, 400, "rent", "2026-11-01")
    add_expense(conn, 20, "groceries", "2026-11-02")
    add_expense(conn, 15, "groceries", "2026-11-02")
    add_expense(conn, 30, "groceries", "2026-11-05")
    return conn


def test_one_point_per_day_of_the_month(conn):
    days = daily_spending(conn, "2026-11", today=date(2026, 11, 30))["days"]

    assert len(days) == 30
    assert days[0]["date"] == "2026-11-01"
    assert days[-1]["date"] == "2026-11-30"


def test_spending_per_day_and_running_total(conn):
    days = daily_spending(conn, "2026-11", today=date(2026, 11, 30))["days"]

    assert days[1]["spent"] == 35  # two expenses on the 2nd
    assert days[1]["cumulative"] == 435
    assert days[4]["cumulative"] == 465
    assert days[29]["cumulative"] == 465


def test_ideal_pace_counts_rent_from_day_one_then_spreads_the_rest(conn):
    days = daily_spending(conn, "2026-11", today=date(2026, 11, 30))["days"]

    assert days[0]["ideal"] == 410   # 400 rent + 10 € of day-to-day budget
    assert days[14]["ideal"] == 550  # 400 + 15 days × 10 €
    assert days[29]["ideal"] == 700  # whole budget on the last day


def test_future_days_have_no_running_total_yet(conn):
    days = daily_spending(conn, "2026-11", today=date(2026, 11, 10))["days"]

    assert days[9]["cumulative"] == 465   # today
    assert days[10]["cumulative"] is None  # tomorrow: unknown
    assert days[10]["ideal"] == 510        # the target line still goes to month end


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_daily_endpoint(client):
    response = client.get("/api/daily", params={"month": "2026-11"})

    assert response.status_code == 200
    assert response.json()["total_budget"] == 700
    assert len(response.json()["days"]) == 30


def test_year_endpoint_returns_twelve_months(client):
    response = client.get("/api/year", params={"year": 2026})

    months = response.json()["months"]
    assert len(months) == 12
    assert months[10] == {"month": "2026-11", "spent": 465, "budget": 700}


@pytest.mark.parametrize("path, params", [("/api/daily", {"month": "Nov"}), ("/api/year", {"year": 1999})])
def test_chart_endpoints_reject_bad_periods(client, path, params):
    assert client.get(path, params=params).status_code == 422
