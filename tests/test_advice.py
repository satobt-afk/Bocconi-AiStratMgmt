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
from tests.helpers import USER, new_db

TODAY = date(2026, 11, 20)


@pytest.fixture
def conn():
    conn = new_db()
    for category, amount in {"rent": 400, "groceries": 150, "restaurant": 60, "leisure": 80}.items():
        set_budget(conn, USER, category, amount)
    # History: restaurant spending by the 20th was 20 € in Sep and 40 € in Oct (usual = 30 €)
    add_expense(conn, USER, 20, "restaurant", "2026-09-10")
    add_expense(conn, USER, 100, "groceries", "2026-09-12")
    add_expense(conn, USER, 40, "restaurant", "2026-10-05")
    add_expense(conn, USER, 50, "restaurant", "2026-10-28")  # after the 20th: not part of "usual by the 20th"
    add_expense(conn, USER, 110, "groceries", "2026-10-12")
    # This month
    add_expense(conn, USER, 400, "rent", "2026-11-01")
    add_expense(conn, USER, 95, "groceries", "2026-11-12")  # usual 105: fine
    for day in ("03", "10", "18"):
        add_expense(conn, USER, 25, "restaurant", f"2026-11-{day}")  # 75 €: way above usual 30 €
    return conn


def test_category_running_faster_than_usual_gets_a_tip(conn):
    tips = saving_tips(conn, USER, today=TODAY)

    assert [t["category"] for t in tips] == ["restaurant"]
    tip = tips[0]
    assert tip["spent"] == 75
    assert tip["usual"] == 30
    assert tip["usual_based_on"] == "history"
    assert tip["ahead_by"] == 45


def test_over_budget_tip_says_so_and_proposes_a_concrete_action(conn):
    tip = saving_tips(conn, USER, today=TODAY)[0]

    assert tip["kind"] == "over_budget"
    assert "15 € over" in tip["message"]
    assert "Dec 1" in tip["tip"]


def test_rent_and_normal_categories_get_no_tip(conn):
    categories = {t["category"] for t in saving_tips(conn, USER, today=TODAY)}

    assert "rent" not in categories
    assert "groceries" not in categories


def test_ahead_but_still_within_budget_suggests_skipping_a_few_purchases():
    # No specific cause here (same price per outing, not much more often): the general tip applies.
    conn = new_db()
    set_budget(conn, USER, "leisure", 300)
    add_expense(conn, USER, 40, "groceries", "2026-09-10")  # September: active month, no leisure
    add_expense(conn, USER, 25, "leisure", "2026-10-08")  # usual by the 20th: (0 + 25) / 2 = 12.50 €, 25 € per outing
    add_expense(conn, USER, 30, "leisure", "2026-11-04")
    add_expense(conn, USER, 30, "leisure", "2026-11-15")  # 60 € now, 47.50 € ahead, avg 30 € each

    tip = saving_tips(conn, USER, today=TODAY)[0]

    assert tip["kind"] == "ahead_of_usual"
    assert tip["tip"].startswith("Skip 2 outings (about 30 € each)")


def test_without_history_the_budget_pace_is_used():
    conn = new_db()
    set_budget(conn, USER, "restaurant", 60)  # pace by Nov 10: 60 × 10/30 = 20 €
    add_expense(conn, USER, 40, "restaurant", "2026-11-08")

    tip = saving_tips(conn, USER, today=date(2026, 11, 10))[0]

    assert tip["usual"] == 20
    assert tip["usual_based_on"] == "budget"


def test_small_differences_are_not_worth_a_tip():
    conn = new_db()
    set_budget(conn, USER, "other", 60)  # pace by Nov 10: 20 €
    add_expense(conn, USER, 28, "other", "2026-11-08")  # only 8 € ahead

    assert saving_tips(conn, USER, today=date(2026, 11, 10)) == []


def test_at_most_three_tips_biggest_first():
    conn = new_db()
    for i, category in enumerate(["groceries", "restaurant", "leisure", "travel", "other"]):
        set_budget(conn, USER, category, 30)
        add_expense(conn, USER, 50 + 10 * i, category, "2026-11-05")

    tips = saving_tips(conn, USER, today=date(2026, 11, 10))

    assert [t["category"] for t in tips] == ["other", "travel", "leisure"]


def test_category_never_used_before_is_compared_with_its_budget_not_with_zero():
    # Found with the demo data: "Transport: 35 € so far. Usually 0 €" -> "skip 1 ride" made no sense.
    conn = new_db()
    set_budget(conn, USER, "transport", 40)  # budget pace by the 25th: 33.33 €
    add_expense(conn, USER, 100, "groceries", "2026-10-10")  # October is an active month, without transport
    add_expense(conn, USER, 35, "transport", "2026-11-03")

    assert saving_tips(conn, USER, today=date(2026, 11, 25)) == []  # 35 € vs 33.33 €: on track



# ---- Finer analysis: WHY a category runs ahead -------------------------------------------

def test_main_fixture_explains_that_it_is_more_often_than_usual(conn):
    tip = saving_tips(conn, USER, today=TODAY)[0]

    assert tip["driver"] == "more_often"
    assert tip["insight"] == "3 meals out so far, vs 1 usually by the 20th."


def test_pricier_than_usual_suggests_cheaper_options():
    conn = new_db()
    set_budget(conn, USER, "restaurant", 100)
    add_expense(conn, USER, 15, "restaurant", "2026-10-03")
    add_expense(conn, USER, 15, "restaurant", "2026-10-10")  # usually 2 meals of 15 € by the 20th
    add_expense(conn, USER, 30, "restaurant", "2026-11-04")
    add_expense(conn, USER, 30, "restaurant", "2026-11-12")  # same number of meals, twice the price

    tip = saving_tips(conn, USER, today=TODAY)[0]

    assert tip["driver"] == "pricier"
    assert tip["insight"] == "Each meal out costs 30 € on average this month, vs 15 € usually."
    assert tip["tip"] == "Pick cheaper places: at your usual 15 € each, you would have saved about 30 €."


def test_one_place_taking_most_of_the_money_is_named():
    conn = new_db()
    set_budget(conn, USER, "restaurant", 60)  # no history: budget pace by Nov 10 = 20 €
    add_expense(conn, USER, 20, "restaurant", "2026-11-03", merchant="Luini")
    add_expense(conn, USER, 25, "restaurant", "2026-11-08", merchant=" luini ")  # same place, typed differently
    add_expense(conn, USER, 5, "restaurant", "2026-11-09", merchant="Poke")

    tip = saving_tips(conn, USER, today=date(2026, 11, 10))[0]

    assert tip["driver"] == "one_place"
    assert tip["insight"] == "90% of your restaurant spending is at Luini (45 €)."
    assert "Luini" in tip["tip"]


def test_weekend_spending_is_spotted():
    conn = new_db()
    set_budget(conn, USER, "leisure", 90)  # no history: budget pace by Nov 20 = 60 €
    for day in ("07", "14", "15"):  # Saturday, Saturday, Sunday
        add_expense(conn, USER, 30, "leisure", f"2026-11-{day}")
    add_expense(conn, USER, 5, "leisure", "2026-11-10")  # Tuesday

    tip = saving_tips(conn, USER, today=TODAY)[0]

    assert tip["driver"] == "weekends"
    assert tip["insight"] == "95% of it happened on weekends."
    assert "weekend" in tip["tip"].lower()


def test_without_a_clear_cause_there_is_no_insight():
    conn = new_db()
    set_budget(conn, USER, "restaurant", 60)  # budget pace by Nov 10 = 20 €
    add_expense(conn, USER, 20, "restaurant", "2026-11-03", merchant="A")
    add_expense(conn, USER, 20, "restaurant", "2026-11-04", merchant="B")  # 2 different places, weekdays

    tip = saving_tips(conn, USER, today=date(2026, 11, 10))[0]

    assert tip["driver"] is None
    assert tip["insight"] is None
