"""Tests for the month-end forecast and the "can I afford it?" check.

These are the numbers the AI coach relies on, so they are computed in
Python and tested here, never left to the language model.
"""

from datetime import date

import pytest

from backend.budgeting import can_afford, forecast_month_end, set_budget
from backend.transactions import add_expense, connect


@pytest.fixture
def conn():
    conn = connect(":memory:")
    set_budget(conn, "rent", 400)
    set_budget(conn, "groceries", 150)
    set_budget(conn, "restaurant", 60)
    set_budget(conn, "travel", 100)
    add_expense(conn, 400, "rent", "2026-11-01")
    add_expense(conn, 30, "groceries", "2026-11-05")
    add_expense(conn, 70, "restaurant", "2026-11-10")
    return conn  # total budget 710; 100 of day-to-day spending in 10 days


def test_forecast_extrapolates_day_to_day_spending_but_not_rent(conn):
    forecast = forecast_month_end(conn, today=date(2026, 11, 10))

    # 100 € of non-rent spending over 10 days = 10 €/day, 20 days still to come
    assert forecast["daily_average"] == 10
    assert forecast["expected_additional_spending"] == 200
    assert forecast["projected_total"] == 700
    assert forecast["projected_remaining"] == 10


def test_forecast_on_last_day_adds_nothing(conn):
    forecast = forecast_month_end(conn, today=date(2026, 11, 30))

    assert forecast["expected_additional_spending"] == 0
    assert forecast["projected_total"] == 500


def test_affordable_purchase(conn):
    result = can_afford(conn, 50, "travel", today=date(2026, 11, 28))

    assert result["verdict"] == "yes"
    assert result["remaining_after_purchase"] == 160
    assert result["category_remaining_after_purchase"] == 50
    assert result["summary"].startswith("Yes, it fits")


def test_purchase_that_breaks_the_forecast_is_tight(conn):
    # 210 € left now, but about 200 € more day-to-day spending is expected.
    result = can_afford(conn, 100, "travel", today=date(2026, 11, 10))

    assert result["verdict"] == "tight"
    assert result["remaining_after_purchase"] == 110
    assert result["projected_remaining_after_purchase"] == -90
    assert result["summary"].startswith("Possible but tight")
    assert "90" in result["summary"]


def test_purchase_over_category_budget_is_tight(conn):
    result = can_afford(conn, 20, "restaurant", today=date(2026, 11, 29))

    assert result["verdict"] == "tight"
    assert result["category_remaining_after_purchase"] == -30
    assert "restaurant budget by 30" in result["summary"]


def test_purchase_larger_than_what_is_left_is_no(conn):
    result = can_afford(conn, 250, "travel", today=date(2026, 11, 29))

    assert result["verdict"] == "no"
    assert result["remaining_after_purchase"] == -40
    assert result["summary"] == "No: it costs 250 € but only 210 € is left this month."


def test_can_afford_rejects_bad_input(conn):
    with pytest.raises(ValueError):
        can_afford(conn, 0, "travel")
    with pytest.raises(ValueError):
        can_afford(conn, 10, "casino")
