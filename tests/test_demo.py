"""Tests for the demo data set.

The demo date is not fixed, so the story is generated relative to "today".
Whatever the day, it must show the key moments of the demo script:
a restaurant tip, a "tight" weekend trip, and one month over budget.
"""

from datetime import date

import pytest

from backend.advice import saving_tips
from backend.budgeting import can_afford, monthly_totals
from backend.demo import seed_demo
from backend.transactions import connect, default_db_path, list_expenses


@pytest.fixture(params=[date(2026, 11, 5), date(2026, 11, 15), date(2026, 11, 25), date(2026, 11, 30),
                        date(2027, 1, 12), date(2027, 2, 28)])
def demo(request):
    conn = connect(":memory:")
    seed_demo(conn, today=request.param)
    return conn, request.param


def test_every_demo_expense_is_labelled_synthetic(demo):
    conn, _ = demo

    expenses = list_expenses(conn)
    assert expenses
    assert {e["source"] for e in expenses} == {"synthetic"}


def test_no_expense_is_in_the_future(demo):
    conn, today = demo

    assert max(e["date"] for e in list_expenses(conn)) <= today.isoformat()


def test_restaurant_tip_shows_up(demo):
    conn, today = demo

    assert saving_tips(conn, today=today)[0]["category"] == "restaurant"


def test_weekend_trip_is_possible_but_tight(demo):
    conn, today = demo

    assert can_afford(conn, 150, "travel", today=today)["verdict"] == "tight"


def test_previous_month_is_over_budget_in_the_year_view(demo):
    conn, today = demo
    previous = date(today.year, today.month, 1).toordinal() - 1
    prev = date.fromordinal(previous)

    month = monthly_totals(conn, prev.year)[prev.month - 1]
    assert month["spent"] > month["budget"]


def test_seeding_twice_does_not_duplicate(demo):
    conn, today = demo
    count = len(list_expenses(conn))

    seed_demo(conn, today=today)

    assert len(list_expenses(conn)) == count


def test_database_path_can_be_chosen_with_an_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "demo.db"))

    assert default_db_path() == tmp_path / "demo.db"


def test_default_database_is_the_real_one(monkeypatch):
    monkeypatch.delenv("BUDGET_DB", raising=False)

    assert default_db_path().name == "budget.db"
