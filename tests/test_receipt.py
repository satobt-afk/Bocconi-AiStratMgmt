"""Tests for turning a receipt photo into a PROPOSED expense.

The vision model is replaced by a fake that returns what a real model
might say, including the mistakes we saw with qwen3-vl (European dates,
comma decimals, unknown categories). Nothing is ever saved here: the
student confirms in the app.
"""

from datetime import date

import pytest

from backend.model_client import ModelUnavailable
from backend.receipt import read_receipt

TODAY = date(2026, 11, 25)


class FakeVision:
    def __init__(self, answer=None, error=None):
        self.answer, self.error = answer, error
        self.received = None

    def read_image(self, prompt, image_base64, schema):
        self.received = (prompt, image_base64, schema)
        if self.error:
            raise self.error
        return self.answer


def scan(answer):
    return read_receipt(FakeVision(answer), "aW1hZ2U=", today=TODAY)


def test_clean_answer_becomes_a_proposal():
    proposal = scan({"merchant": " ESSELUNGA S.p.A. ", "date": "23-11-2026", "total": 19.6, "category": "groceries"})

    assert proposal == {
        "merchant": "ESSELUNGA S.p.A.",
        "amount": 19.6,
        "date": "2026-11-23",
        "category": "groceries",
        "warnings": [],
    }


@pytest.mark.parametrize("raw", ["23-11-2026", "23/11/2026", "23.11.2026", "23/11/26", "2026-11-23", "23-11-2026 18:42"])
def test_european_and_iso_dates_are_understood(raw):
    assert scan({"merchant": "X", "date": raw, "total": 5, "category": "other"})["date"] == "2026-11-23"


@pytest.mark.parametrize("raw", ["", "yesterday", "2026-12-24", "2020-01-01"])
def test_unreadable_future_or_very_old_date_falls_back_to_today(raw):
    proposal = scan({"merchant": "X", "date": raw, "total": 5, "category": "other"})

    assert proposal["date"] == "2026-11-25"
    assert any("date" in w.lower() for w in proposal["warnings"])


@pytest.mark.parametrize("raw, expected", [("19,60", 19.6), ("€ 19.60", 19.6), (7, 7.0)])
def test_amount_formats_are_understood(raw, expected):
    assert scan({"merchant": "X", "date": "2026-11-23", "total": raw, "category": "other"})["amount"] == expected


@pytest.mark.parametrize("raw", [0, -3, "", "abc"])
def test_missing_amount_is_left_empty_with_a_warning(raw):
    proposal = scan({"merchant": "X", "date": "2026-11-23", "total": raw, "category": "other"})

    assert proposal["amount"] is None
    assert any("amount" in w.lower() for w in proposal["warnings"])


def test_unknown_category_becomes_other_with_a_warning():
    proposal = scan({"merchant": "X", "date": "2026-11-23", "total": 5, "category": "food"})

    assert proposal["category"] == "other"
    assert any("category" in w.lower() for w in proposal["warnings"])


def test_garbage_answer_does_not_crash():
    proposal = scan({"unexpected": True})

    assert proposal["amount"] is None
    assert proposal["merchant"] == ""
    assert proposal["date"] == "2026-11-25"


def test_model_receives_the_image_and_a_json_schema():
    vision = FakeVision({"merchant": "X", "date": "2026-11-23", "total": 5, "category": "other"})

    read_receipt(vision, "aW1hZ2U=", today=TODAY)

    prompt, image, schema = vision.received
    assert image == "aW1hZ2U="
    assert set(schema["required"]) == {"merchant", "date", "total", "category"}
    assert "groceries" in schema["properties"]["category"]["enum"]


def test_model_offline_is_reported():
    with pytest.raises(ModelUnavailable):
        read_receipt(FakeVision(error=ModelUnavailable("down")), "aW1hZ2U=", today=TODAY)
