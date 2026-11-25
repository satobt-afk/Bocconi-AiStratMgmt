"""Tests for proactive saving tips.

A tip appears when a category runs clearly faster than usual: compared with
the student's previous months at the same day of the month, or with the
budget pace when there is no history yet. Every number is computed here.
"""

from datetime import date

import pytest

from backend.advice import saving_tips
from backend.budgeting import set_budget
from backend.transactions import add_expense, connect

TODAY = date(2026, 11, 20)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    for category, amount in {"rent": 400, "groceries": 150, "restaurant": 60, "leisure": 80}.items():
        set_budget(conn, category, amount)
    # History: restaurant spending by the 20th was 20 € in Sep and 40 € in Oct (usual = 30 €)
    add_expense(conn, 20, "restaurant", "2026-09-10")
    add_expense(conn, 100, "groceries", "2026-09-12")
    add_expense(conn, 40, "restaurant", "2026-10-05")
    add_expense(conn, 50, "restaurant", "2026-10-28")  # after the 20th: not part of "usual by the 20th"
    add_expense(conn, 110, "groceries", "2026-10-12")
    # This month
    add_expense(conn, 400, "rent", "2026-11-01")
    add_expense(conn, 95, "groceries", "2026-11-12")  # usual 105: fine
    for day in ("03", "10", "18"):
        add_expense(conn, 25, "restaurant", f"2026-11-{day}")  # 75 €: way above usual 30 €
    return conn


def test_category_running_faster_than_usual_gets_a_tip(conn):
    tips = saving_tips(conn, today=TODAY)

    assert [t["category"] for t in tips] == ["restaurant"]
    tip = tips[0]
    assert tip["spent"] == 75
    assert tip["usual"] == 30
    assert tip["usual_based_on"] == "history"
    assert tip["ahead_by"] == 45


def test_over_budget_tip_says_so_and_proposes_a_concrete_action(conn):
    tip = saving_tips(conn, today=TODAY)[0]

    assert tip["kind"] == "over_budget"
    assert "15 € over" in tip["message"]
    assert "Dec 1" in tip["tip"]


def test_rent_and_normal_categories_get_no_tip(conn):
    categories = {t["category"] for t in saving_tips(conn, today=TODAY)}

    assert "rent" not in categories
    assert "groceries" not in categories


def test_ahead_but_still_within_budget_suggests_skipping_a_few_purchases():
    conn = connect(":memory:")
    set_budget(conn, "leisure", 300)
    add_expense(conn, 10, "leisure", "2026-10-08")  # usual by the 20th: 10 €
    add_expense(conn, 30, "leisure", "2026-11-04")
    add_expense(conn, 30, "leisure", "2026-11-15")  # 60 € now, 50 € ahead, avg 30 € each

    tip = saving_tips(conn, today=TODAY)[0]

    assert tip["kind"] == "ahead_of_usual"
    assert tip["tip"].startswith("Skip 2 outings (about 30 € each)")


def test_without_history_the_budget_pace_is_used():
    conn = connect(":memory:")
    set_budget(conn, "restaurant", 60)  # pace by Nov 10: 60 × 10/30 = 20 €
    add_expense(conn, 40, "restaurant", "2026-11-08")

    tip = saving_tips(conn, today=date(2026, 11, 10))[0]

    assert tip["usual"] == 20
    assert tip["usual_based_on"] == "budget"


def test_small_differences_are_not_worth_a_tip():
    conn = connect(":memory:")
    set_budget(conn, "other", 60)  # pace by Nov 10: 20 €
    add_expense(conn, 28, "other", "2026-11-08")  # only 8 € ahead

    assert saving_tips(conn, today=date(2026, 11, 10)) == []


def test_at_most_three_tips_biggest_first():
    conn = connect(":memory:")
    for i, category in enumerate(["groceries", "restaurant", "leisure", "travel", "other"]):
        set_budget(conn, category, 30)
        add_expense(conn, 50 + 10 * i, category, "2026-11-05")

    tips = saving_tips(conn, today=date(2026, 11, 10))

    assert [t["category"] for t in tips] == ["other", "travel", "leisure"]


def test_category_never_used_before_is_compared_with_its_budget_not_with_zero():
    # Found with the demo data: "Transport: 35 € so far. Usually 0 €" -> "skip 1 ride" made no sense.
    conn = connect(":memory:")
    set_budget(conn, "transport", 40)  # budget pace by the 25th: 33.33 €
    add_expense(conn, 100, "groceries", "2026-10-10")  # October is an active month, without transport
    add_expense(conn, 35, "transport", "2026-11-03")

    assert saving_tips(conn, today=date(2026, 11, 25)) == []  # 35 € vs 33.33 €: on track
