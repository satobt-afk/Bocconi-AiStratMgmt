"""Proactive saving tips: spot a category running faster than usual and suggest a concrete fix.

"Usual" = what the student spent in that category by the same day of the month,
averaged over their previous active months (up to 3). With no history yet, the
budget pace is used instead (budget x day / days in month). Rent is a fixed cost
and never gets a tip. Every number is computed here; the app and the AI coach
only display or rephrase it.
"""

import calendar
import math
import sqlite3
from datetime import date
from typing import Dict, List, Optional

from backend.budgeting import FIXED_CATEGORIES, _budgets_cents, _fmt
from backend.transactions import CATEGORIES

HISTORY_MONTHS = 3
MIN_GAP_CENTS = 1000  # ignore differences under 10 €
MIN_RATIO = 1.25  # at least 25 % above usual
MAX_TIPS = 3

LABELS = {"groceries": "Groceries", "restaurant": "Restaurant", "transport": "Transport",
          "leisure": "Leisure", "travel": "Travel", "other": "Other"}
# Things to skip when a category runs ahead: (singular, plural)
SKIPPABLE = {"groceries": ("extra shop", "extra shops"), "restaurant": ("meal out", "meals out"),
             "transport": ("ride", "rides"), "leisure": ("outing", "outings"),
             "travel": ("trip", "trips"), "other": ("purchase", "purchases")}
# What to do once a category is already over budget, until the month resets
OVER_BUDGET_ACTIONS = {
    "restaurant": "Cook at home until {reset}: each meal out you skip saves about {avg}.",
    "groceries": "Plan your meals and pick store brands until {reset}.",
    "leisure": "Choose free activities until {reset} (parks, free museum days, student events).",
    "travel": "Postpone new trips until {reset}.",
    "transport": "Walk or cycle short distances until {reset}.",
    "other": "Hold non-essential purchases until {reset}.",
}


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _shift(year: int, month: int, delta: int):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _spent_by_day(conn: sqlite3.Connection, year: int, month: int, day: int) -> Dict[str, int]:
    """Cents spent per category from the 1st to `day` (clamped to the month length)."""
    last = min(day, calendar.monthrange(year, month)[1])
    rows = conn.execute(
        "SELECT category, SUM(amount_cents) AS total FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category",
        (date(year, month, 1).isoformat(), date(year, month, last).isoformat()),
    )
    return {r["category"]: r["total"] for r in rows}


def _active(conn: sqlite3.Connection, year: int, month: int) -> bool:
    prefix = f"{year:04d}-{month:02d}"
    return conn.execute("SELECT 1 FROM expenses WHERE substr(date, 1, 7) = ? LIMIT 1", (prefix,)).fetchone() is not None


def _average_ticket(conn: sqlite3.Connection, category: str, month_prefix: str) -> int:
    row = conn.execute(
        "SELECT AVG(amount_cents) AS avg FROM expenses WHERE category = ? AND substr(date, 1, 7) = ?",
        (category, month_prefix),
    ).fetchone()
    return round(row["avg"] or 0)


def saving_tips(conn: sqlite3.Connection, today: Optional[date] = None) -> List[dict]:
    """Up to 3 tips for the current month, biggest overspending first."""
    today = today or date.today()
    year, month, day = today.year, today.month, today.day
    days_in_month = calendar.monthrange(year, month)[1]
    reset_y, reset_m = _shift(year, month, 1)
    reset = f"{calendar.month_abbr[reset_m]} 1"
    prefix = f"{year:04d}-{month:02d}"

    budgets = _budgets_cents(conn)
    now = _spent_by_day(conn, year, month, day)
    history_months = [
        (y, m) for y, m in (_shift(year, month, -k) for k in range(1, HISTORY_MONTHS + 1)) if _active(conn, y, m)
    ]
    history = [_spent_by_day(conn, y, m, day) for y, m in history_months]
    # Categories the student actually used in those months: for the others, "usual = 0 €"
    # would be meaningless, so they are compared with their budget pace instead.
    used_before = set()
    for y, m in history_months:
        used_before |= set(_spent_by_day(conn, y, m, 31))

    tips = []
    for category in CATEGORIES:
        if category in FIXED_CATEGORIES:
            continue
        spent = now.get(category, 0)
        if category in used_before:
            usual = round(sum(h.get(category, 0) for h in history) / len(history))
            based_on = "history"
        elif category in budgets:
            usual = round(budgets[category] * day / days_in_month)
            based_on = "budget"
        else:
            continue

        ahead = spent - usual
        if ahead < MIN_GAP_CENTS or spent <= usual * MIN_RATIO:
            continue

        label = LABELS[category]
        avg = _average_ticket(conn, category, prefix)
        usual_text = (
            f"Usually {_fmt(usual)} by the {_ordinal(day)}." if based_on == "history"
            else f"Your budget pace is {_fmt(usual)} by the {_ordinal(day)}."
        )
        budget = budgets.get(category)
        if budget is not None and spent > budget:
            kind = "over_budget"
            message = f"{label}: {_fmt(spent)} spent, budget {_fmt(budget)} ({_fmt(spent - budget)} over). {usual_text}"
            tip = OVER_BUDGET_ACTIONS[category].format(reset=reset, avg=_fmt(avg))
        else:
            kind = "ahead_of_usual"
            message = f"{label}: {_fmt(spent)} so far. {usual_text}"
            pace = "usual pace" if based_on == "history" else "budget pace"
            n = math.ceil(ahead / avg) if avg else 0
            if 1 <= n <= 4:
                noun = SKIPPABLE[category][0 if n == 1 else 1]
                tip = f"Skip {n} {noun} (about {_fmt(avg)} each) to get back to your {pace}."
            else:
                tip = f"Slow down on {label.lower()} until {reset}: you are {_fmt(ahead)} ahead of your {pace}."

        tips.append({
            "category": category,
            "kind": kind,
            "spent": spent / 100,
            "usual": usual / 100,
            "usual_based_on": based_on,
            "ahead_by": ahead / 100,
            "message": message,
            "tip": tip,
        })

    tips.sort(key=lambda t: t["ahead_by"], reverse=True)
    return tips[:MAX_TIPS]
