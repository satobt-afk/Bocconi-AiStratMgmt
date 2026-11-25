"""Monthly budgets per category and spending status.

A month runs from the 1st to its last day. Nothing is ever deleted when
a month ends: the "reset" is simply that each month's status only counts
expenses dated in that month, so past months stay available as history.
All sums are done in integer cents, then converted to euros.
"""

import calendar
import sqlite3
from datetime import date
from typing import Dict, List, Optional

from backend.transactions import CATEGORIES, Amount, check_category, check_month, to_cents, to_euros


def set_budget(conn: sqlite3.Connection, category: str, amount: Amount) -> None:
    """Set the monthly limit for a category (applies to every month)."""
    check_category(category)
    cents = to_cents(amount)
    if cents < 0:
        raise ValueError("Budget cannot be negative")
    with conn:
        conn.execute(
            "INSERT INTO budgets (category, limit_cents) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET limit_cents = excluded.limit_cents",
            (category, cents),
        )


def get_budgets(conn: sqlite3.Connection) -> Dict[str, float]:
    """Monthly limit of every category, 0 when none was set."""
    budgets = _budgets_cents(conn)
    return {category: to_euros(budgets.get(category, 0)) for category in CATEGORIES}


def _budgets_cents(conn: sqlite3.Connection) -> Dict[str, int]:
    return {r["category"]: r["limit_cents"] for r in conn.execute("SELECT category, limit_cents FROM budgets")}


def _spent_cents_by_category(conn: sqlite3.Connection, month: str) -> Dict[str, int]:
    rows = conn.execute(
        "SELECT category, SUM(amount_cents) AS total FROM expenses "
        "WHERE substr(date, 1, 7) = ? GROUP BY category",
        (month,),
    )
    return {r["category"]: r["total"] for r in rows}


def _days_left(month: str, today: date) -> int:
    """Days remaining in `month`, today included; 0 if the month is over."""
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    last = date(year, mon, calendar.monthrange(year, mon)[1])
    if today > last:
        return 0
    if today < first:
        return last.day
    return (last - today).days + 1


def get_budget_status(conn: sqlite3.Connection, month: str, today: Optional[date] = None) -> dict:
    """Budget, spending and remaining amount for `month` (YYYY-MM), in total and per category."""
    check_month(month)
    today = today or date.today()
    budgets = _budgets_cents(conn)
    spent = _spent_cents_by_category(conn, month)

    categories = {}
    for category in CATEGORIES:
        if category not in budgets and category not in spent:
            continue
        b, s = budgets.get(category, 0), spent.get(category, 0)
        categories[category] = {
            "budget": to_euros(b),
            "spent": to_euros(s),
            "remaining": to_euros(b - s),
            "over_budget": s > b,
        }

    total_budget, total_spent = sum(budgets.values()), sum(spent.values())
    return {
        "month": month,
        "total_budget": to_euros(total_budget),
        "spent": to_euros(total_spent),
        "remaining": to_euros(total_budget - total_spent),
        "days_left": _days_left(month, today),
        "categories": categories,
    }


def monthly_totals(conn: sqlite3.Connection, year: int) -> List[dict]:
    """Total spent and total budget for each of the 12 months of `year`."""
    rows = conn.execute(
        "SELECT substr(date, 1, 7) AS month, SUM(amount_cents) AS total FROM expenses "
        "WHERE substr(date, 1, 4) = ? GROUP BY month",
        (f"{year:04d}",),
    )
    spent = {r["month"]: r["total"] for r in rows}
    total_budget = sum(_budgets_cents(conn).values())
    return [
        {"month": m, "spent": to_euros(spent.get(m, 0)), "budget": to_euros(total_budget)}
        for m in (f"{year:04d}-{mon:02d}" for mon in range(1, 13))
    ]
