"""Turn a receipt photo into a PROPOSED expense.

The vision model reads the photo and answers in a fixed JSON shape.
Python then checks and cleans every field, because small models make
predictable mistakes (European dates, "19,60", invented categories).
Nothing is saved here: the student checks the proposal and confirms it.
"""

import re
from datetime import date, timedelta
from typing import Optional

from backend.transactions import CATEGORIES

PROMPT = (
    "Read this receipt. Return the shop name, the purchase date as YYYY-MM-DD, "
    "the final total paid in euros, and the best spending category. "
    "If something is unreadable, use an empty string or 0."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "merchant": {"type": "string"},
        "date": {"type": "string"},
        "total": {"type": "number"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
    },
    "required": ["merchant", "date", "total", "category"],
}

_DATE = re.compile(r"(\d{1,4})[-/.](\d{1,2})[-/.](\d{2,4})")


def _parse_date(raw, today: date) -> Optional[date]:
    """Accept 2026-11-23, 23-11-2026, 23/11/2026, 23.11.26 (day first, as on European receipts)."""
    match = _DATE.search(str(raw or ""))
    if not match:
        return None
    a, b, c = match.groups()
    try:
        if len(a) == 4:
            day = date(int(a), int(b), int(c))
        else:
            year = int(c) + 2000 if len(c) == 2 else int(c)
            day = date(year, int(b), int(a))
    except ValueError:
        return None
    # A receipt from the future, or more than a year old, is a misreading.
    if day > today or day < today - timedelta(days=366):
        return None
    return day


def _parse_amount(raw) -> Optional[float]:
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = re.sub(r"[^0-9,.\-]", "", str(raw or ""))
        if "," in text and "." in text:  # 1.234,56
            text = text.replace(".", "")
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return None
    return round(value, 2) if value > 0 else None


def read_receipt(vision_client, image_base64: str, today: Optional[date] = None) -> dict:
    """Ask the vision model to read the receipt, then validate its answer.

    Returns {"merchant", "amount" (None if unreadable), "date", "category", "warnings": [str]}.
    """
    today = today or date.today()
    answer = vision_client.read_image(PROMPT, image_base64, SCHEMA)
    warnings = []

    amount = _parse_amount(answer.get("total"))
    if amount is None:
        warnings.append("Could not read the amount: please type it.")

    day = _parse_date(answer.get("date"), today)
    if day is None:
        day = today
        warnings.append("Could not read a valid date: set to today, please check.")

    category = answer.get("category")
    if category not in CATEGORIES:
        category = "other"
        warnings.append("Could not guess the category: please pick one.")

    merchant = str(answer.get("merchant") or "").strip()[:60]

    return {
        "merchant": merchant,
        "amount": amount,
        "date": day.isoformat(),
        "category": category,
        "warnings": warnings,
    }
