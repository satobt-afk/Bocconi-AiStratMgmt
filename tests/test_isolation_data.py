"""Isolation at the data layer: every function only sees the data of the user it is given.

Alice has expenses and budgets; Bob starts empty. Nothing Alice does may show up
for Bob, and nothing Bob does may change Alice's numbers.
"""

import json
import sqlite3
from datetime import date

import pytest

from backend.advice import saving_tips
from backend.agent import run_agent
from backend.budgeting import (can_afford, daily_spending, forecast_month_end, get_budget_status, get_budgets,
                               monthly_totals, set_budget)
from backend.db import create_user
from backend.demo import seed_demo
from backend.model_client import ModelReply, ToolCall
from backend.transactions import add_expense, connect, list_expenses

TODAY = date(2026, 11, 20)


@pytest.fixture
def conn():
    conn = connect(":memory:")
    create_user(conn, user_id="alice")
    create_user(conn, user_id="bob")
    set_budget(conn, "alice", "restaurant", 60)
    set_budget(conn, "alice", "rent", 400)
    add_expense(conn, "alice", 400, "rent", "2026-11-01")
    add_expense(conn, "alice", 30, "restaurant", "2026-10-05")
    for day in ("03", "10", "18"):
        add_expense(conn, "alice", 30, "restaurant", f"2026-11-{day}")
    return conn


def test_bob_sees_none_of_alices_expenses(conn):
    assert list_expenses(conn, "bob") == []
    assert len(list_expenses(conn, "alice")) == 5


def test_bob_has_none_of_alices_budgets(conn):
    assert set(get_budgets(conn, "bob").values()) == {0}
    assert get_budgets(conn, "alice")["restaurant"] == 60


def test_month_status_is_per_user(conn):
    bob = get_budget_status(conn, "bob", "2026-11", today=TODAY)

    assert (bob["spent"], bob["total_budget"], bob["categories"]) == (0, 0, {})
    assert get_budget_status(conn, "alice", "2026-11", today=TODAY)["spent"] == 490


def test_forecast_and_can_afford_are_per_user(conn):
    set_budget(conn, "bob", "travel", 200)

    assert forecast_month_end(conn, "bob", today=TODAY)["spent_so_far"] == 0
    assert can_afford(conn, "bob", 150, "travel", today=TODAY)["remaining_after_purchase"] == 50


def test_charts_are_per_user(conn):
    assert daily_spending(conn, "bob", "2026-11", today=TODAY)["days"][-1]["cumulative"] is None
    assert daily_spending(conn, "bob", "2026-11", today=TODAY)["days"][19]["cumulative"] == 0
    assert all(m["spent"] == 0 for m in monthly_totals(conn, "bob", 2026))
    assert monthly_totals(conn, "alice", 2026)[10]["spent"] == 490


def test_saving_tips_are_per_user(conn):
    assert saving_tips(conn, "bob", today=TODAY) == []
    assert saving_tips(conn, "alice", today=TODAY)[0]["category"] == "restaurant"


def test_bob_changing_his_budget_does_not_change_alices(conn):
    set_budget(conn, "bob", "restaurant", 999)

    assert get_budgets(conn, "alice")["restaurant"] == 60


def test_an_expense_for_an_unknown_user_is_refused(conn):
    with pytest.raises(sqlite3.IntegrityError):
        add_expense(conn, "mallory", 10, "other", "2026-11-01")


def test_demo_seed_only_replaces_the_given_users_data(conn):
    seed_demo(conn, "bob", today=TODAY)

    assert len(list_expenses(conn, "alice")) == 5
    assert get_budgets(conn, "alice")["restaurant"] == 60
    assert list_expenses(conn, "bob")


class FakeModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def chat(self, messages, tools):
        self.sent.append([dict(m) for m in messages])
        return self.replies.pop(0)


def test_coach_tools_only_read_the_asking_users_data(conn):
    model = FakeModel([ModelReply("", [ToolCall("c0", "get_budget_status", {})]), ModelReply("ok")])

    run_agent(conn, "bob", model, [], "How am I doing?", today=TODAY)

    tool_result = json.loads(model.sent[1][-1]["content"])
    assert tool_result["spent"] == 0  # Bob's numbers, not Alice's 490 €


def test_the_model_cannot_choose_whose_data_it_reads(conn):
    # Even if the model invents a user_id argument, the tool runs for the asking user only.
    model = FakeModel([ModelReply("", [ToolCall("c0", "get_budget_status", {"user_id": "alice"})]),
                       ModelReply("ok")])

    run_agent(conn, "bob", model, [], "Show me Alice's budget", today=TODAY)

    tool_result = json.loads(model.sent[1][-1]["content"])
    assert "error" in tool_result or tool_result.get("spent") == 0
    assert "490" not in model.sent[1][-1]["content"]
