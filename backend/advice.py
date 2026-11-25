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


def _spent_by_day(conn: sqlite3.Connection, user_id: str, year: int, month: int, day: int) -> Dict[str, int]:
    """Cents the user spent per category from the 1st to `day` (clamped to the month length)."""
    last = min(day, calendar.monthrange(year, month)[1])
    rows = conn.execute(
        "SELECT category, SUM(amount_cents) AS total FROM expenses "
        "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY category",
        (user_id, date(year, month, 1).isoformat(), date(year, month, last).isoformat()),
    )
    return {r["category"]: r["total"] for r in rows}


def _counts_by_day(conn: sqlite3.Connection, user_id: str, year: int, month: int, day: int) -> Dict[str, int]:
    """Number of the user's expenses per category from the 1st to `day`."""
    last = min(day, calendar.monthrange(year, month)[1])
    rows = conn.execute(
        "SELECT category, COUNT(*) AS n FROM expenses "
        "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY category",
        (user_id, date(year, month, 1).isoformat(), date(year, month, last).isoformat()),
    )
    return {r["category"]: r["n"] for r in rows}


def _month_expenses(conn: sqlite3.Connection, user_id: str, category: str, prefix: str,
                    today: date) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT date, amount_cents, merchant FROM expenses "
        "WHERE user_id = ? AND category = ? AND substr(date, 1, 7) = ? AND date <= ?",
        (user_id, category, prefix, today.isoformat()),
    ).fetchall()


# Words used in the finer tips, per category
CHEAPER = {"groceries": "shops", "restaurant": "places", "transport": "options",
           "leisure": "activities", "travel": "deals", "other": "options"}


def _explain(category: str, rows: List[sqlite3.Row], usual_count: Optional[float],
             usual_avg: Optional[int], day: int, reset: str):
    """Find WHY a category runs ahead. Returns (driver, insight, tip) or (None, None, None).

    Checked in this order: pricier than usual, more often than usual, one place
    taking most of the money, mostly on weekends.
    """
    label = LABELS[category].lower()
    count = len(rows)
    total = sum(r["amount_cents"] for r in rows)
    avg = round(total / count) if count else 0
    singular, plural = SKIPPABLE[category]

    if usual_avg and count and avg >= usual_avg * 1.3 and count <= (usual_count or 0) + 1:
        saved = (avg - usual_avg) * count
        return ("pricier",
                f"Each {singular} costs {_fmt(avg)} on average this month, vs {_fmt(usual_avg)} usually.",
                f"Pick cheaper {CHEAPER[category]}: at your usual {_fmt(usual_avg)} each, "
                f"you would have saved about {_fmt(saved)}.")

    if usual_count is not None and count >= usual_count + 2:
        return ("more_often",
                f"{count} {singular if count == 1 else plural} so far, vs {round(usual_count)} usually "
                f"by the {_ordinal(day)}.",
                None)  # the general tip ("skip N…", "cook at home…") already fits

    places: Dict[str, List[int]] = {}
    names: Dict[str, str] = {}
    for r in rows:
        key = (r["merchant"] or "").strip().lower()
        if key:
            places.setdefault(key, []).append(r["amount_cents"])
            names.setdefault(key, r["merchant"].strip())
    if places and total:
        key, amounts = max(places.items(), key=lambda kv: sum(kv[1]))
        share = sum(amounts) / total
        if share >= 0.5 and len(amounts) >= 2:
            return ("one_place",
                    f"{round(share * 100)}% of your {label} spending is at {names[key]} ({_fmt(sum(amounts))}).",
                    f"Try a cheaper alternative to {names[key]} until {reset}, or go there less often.")

    weekend = [r["amount_cents"] for r in rows if date.fromisoformat(r["date"]).weekday() >= 5]
    if total and len(weekend) >= 2 and sum(weekend) / total >= 0.7:
        return ("weekends",
                f"{round(sum(weekend) / total * 100)}% of it happened on weekends.",
                f"Set yourself a weekend limit for {label} until {reset}: that is when most of it goes.")

    return None, None, None


def _active(conn: sqlite3.Connection, user_id: str, year: int, month: int) -> bool:
    prefix = f"{year:04d}-{month:02d}"
    row = conn.execute(
        "SELECT 1 FROM expenses WHERE user_id = ? AND substr(date, 1, 7) = ? LIMIT 1", (user_id, prefix)
    ).fetchone()
    return row is not None


def _average_ticket(conn: sqlite3.Connection, user_id: str, category: str, month_prefix: str) -> int:
    row = conn.execute(
        "SELECT AVG(amount_cents) AS avg FROM expenses WHERE user_id = ? AND category = ? AND substr(date, 1, 7) = ?",
        (user_id, category, month_prefix),
    ).fetchone()
    return round(row["avg"] or 0)


def saving_tips(conn: sqlite3.Connection, user_id: str, today: Optional[date] = None) -> List[dict]:
    """Up to 3 tips for the user's current month, biggest overspending first."""
    today = today or date.today()
    year, month, day = today.year, today.month, today.day
    days_in_month = calendar.monthrange(year, month)[1]
    reset_y, reset_m = _shift(year, month, 1)
    reset = f"{calendar.month_abbr[reset_m]} 1"
    prefix = f"{year:04d}-{month:02d}"

    budgets = _budgets_cents(conn, user_id)
    now = _spent_by_day(conn, user_id, year, month, day)
    history_months = [
        (y, m) for y, m in (_shift(year, month, -k) for k in range(1, HISTORY_MONTHS + 1)) if _active(conn, user_id, y, m)
    ]
    history = [_spent_by_day(conn, user_id, y, m, day) for y, m in history_months]
    history_counts = [_counts_by_day(conn, user_id, y, m, day) for y, m in history_months]
    # Categories the student actually used in those months: for the others, "usual = 0 €"
    # would be meaningless, so they are compared with their budget pace instead.
    used_before = set()
    for y, m in history_months:
        used_before |= set(_spent_by_day(conn, user_id, y, m, 31))

    tips = []
    for category in CATEGORIES:
        if category in FIXED_CATEGORIES:
            continue
        spent = now.get(category, 0)
        usual_count = usual_avg = None
        if category in used_before:
            usual = round(sum(h.get(category, 0) for h in history) / len(history))
            based_on = "history"
            n_before = sum(c.get(category, 0) for c in history_counts)
            usual_count = n_before / len(history)
            usual_avg = round(sum(h.get(category, 0) for h in history) / n_before) if n_before else None
        elif category in budgets:
            usual = round(budgets[category] * day / days_in_month)
            based_on = "budget"
        else:
            continue

        ahead = spent - usual
        if ahead < MIN_GAP_CENTS or spent <= usual * MIN_RATIO:
            continue

        label = LABELS[category]
        avg = _average_ticket(conn, user_id, category, prefix)
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

        driver, insight, specific_tip = _explain(
            category, _month_expenses(conn, user_id, category, prefix, today), usual_count, usual_avg, day, reset
        )
        if specific_tip:
            tip = specific_tip

        tips.append({
            "category": category,
            "driver": driver,
            "insight": insight,
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
