"""The evaluation runner, with a fake model (no real model call in pytest)."""

import json

from backend.model_client import ModelReply, ToolCall
from evaluation.run_eval import FIXED_DATE, QUESTIONS, ask_agent, ask_baseline, build_db, expected_verdict, score


class FakeModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.tools_seen = []

    def chat(self, messages, tools):
        self.tools_seen.append(tools)
        return self.replies.pop(0)


def test_the_models_own_category_is_scored_not_the_guard_rails_fix():
    conn, user = build_db()
    model = FakeModel(ModelReply("", [ToolCall("c", "can_afford", {"amount": 150, "category": "week-end"})]),
                      ModelReply("It's possible but tight."))
    question = {"id": "x", "language": "en", "scene": "category_mapping",
                "question": "Weekend for 150 €?", "expect": {"category": "travel"}}

    answer = ask_agent(conn, user, model, question)
    checks = score(question, answer, None)

    assert answer["raw_calls"][0]["arguments"]["category"] == "week-end"
    assert answer["tools_used"][0]["arguments"]["category"] == "travel"
    assert checks["category_model"]["ok"] is False
    assert checks["category_after_guardrail"]["ok"] is True


def test_tools_run_on_the_fixed_date():
    conn, user = build_db()
    model = FakeModel(ModelReply("", [ToolCall("c", "get_budget_status", {})]), ModelReply("ok"))

    answer = ask_agent(conn, user, model, {"question": "Status?"})

    assert answer["tool_results"][0]["month"] == FIXED_DATE.strftime("%Y-%m")


def test_baseline_gets_no_tools_and_the_data_as_text():
    conn, user = build_db()
    model = FakeModel(ModelReply("You have 193 € left."))

    answer = ask_baseline(conn, user, model, {"question": "How much is left?"})

    assert model.tools_seen == [[]]
    assert "budget_status" in answer["tool_results"][0]


def test_the_question_set_covers_every_scene_language_and_verdict():
    questions = json.loads(QUESTIONS.read_text())
    conn, user = build_db()

    verdicts = {expected_verdict(conn, user, q) for q in questions} - {None}

    assert len(questions) == 30
    assert {q["language"] for q in questions} == {"en", "fr", "it"}
    assert {q["scene"] for q in questions} == {"tool_choice", "category_mapping", "verdict_kept",
                                                 "numbers_faithful", "no_data", "out_of_scope"}
    assert verdicts == {"yes", "tight", "no"}
