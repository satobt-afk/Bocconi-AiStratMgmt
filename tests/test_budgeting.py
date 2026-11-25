"""Tests for monthly budget status and yearly history."""

from datetime import date

import pytest

from backend.budgeting import get_budget_status, monthly_totals, set_budget
from backend.transactions import add_expense, connect


@pytest.fixture
def conn():
    conn = connect(":memory:")
    set_budget(conn, "rent", 400)
    set_budget(conn, "restaurant", 60)
    set_budget(conn, "groceries", 150)
    return conn


def test_status_sums_spending_against_budgets(conn):
    add_expense(conn, 400, "rent", "2026-11-01")
    add_expense(conn, 75, "restaurant", "2026-11-10")
    add_expense(conn, 30, "groceries", "2026-11-12")

    status = get_budget_status(conn, "2026-11", today=date(2026, 11, 25))

    assert status["total_budget"] == 610
    assert status["spent"] == 505
    assert status["remaining"] == 105
    assert status["days_left"] == 6  # 25 to 30 November, today included
    restaurant = status["categories"]["restaurant"]
    assert restaurant == {"budget": 60, "spent": 75, "remaining": -15, "over_budget": True}


def test_new_month_starts_from_zero_but_history_is_kept(conn):
    add_expense(conn, 75, "restaurant", "2026-10-31")

    november = get_budget_status(conn, "2026-11", today=date(2026, 11, 1))
    october = get_budget_status(conn, "2026-10", today=date(2026, 11, 1))

    assert november["spent"] == 0
    assert october["spent"] == 75
    assert october["days_left"] == 0  # month already over


def test_category_without_budget_still_counts_spending(conn):
    add_expense(conn, 12, "leisure", "2026-11-05")

    status = get_budget_status(conn, "2026-11", today=date(2026, 11, 5))

    assert status["spent"] == 12
    assert status["categories"]["leisure"] == {
        "budget": 0, "spent": 12, "remaining": -12, "over_budget": True,
    }


def test_cents_do_not_drift(conn):
    # In float maths 0.1 + 0.2 == 0.30000000000000004: money must stay exact.
    add_expense(conn, 0.10, "groceries", "2026-11-02")
    add_expense(conn, 0.20, "groceries", "2026-11-03")

    status = get_budget_status(conn, "2026-11", today=date(2026, 11, 3))

    assert status["spent"] == 0.30


def test_monthly_totals_cover_the_whole_year(conn):
    add_expense(conn, 760, "rent", "2026-09-15")
    add_expense(conn, 845, "rent", "2026-10-15")
    add_expense(conn, 99, "rent", "2025-10-15")  # other year: ignored

    totals = monthly_totals(conn, 2026)

    assert len(totals) == 12
    assert totals[8] == {"month": "2026-09", "spent": 760, "budget": 610}
    assert totals[9]["spent"] == 845
    assert totals[0]["spent"] == 0


def test_budget_can_be_changed(conn):
    set_budget(conn, "rent", 450)

    assert get_budget_status(conn, "2026-11")["categories"]["rent"]["budget"] == 450


def test_budget_must_be_valid(conn):
    with pytest.raises(ValueError):
        set_budget(conn, "casino", 50)
    with pytest.raises(ValueError):
        set_budget(conn, "rent", -1)
