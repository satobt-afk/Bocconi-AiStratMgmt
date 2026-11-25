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


def _fmt(cents: int) -> str:
    """3460 -> "34.60 €", 25000 -> "250 €"."""
    return f"{cents // 100} €" if cents % 100 == 0 else f"{cents / 100:.2f} €"


# Paid once a month: not used to estimate the daily spending pace.
FIXED_CATEGORIES = ("rent",)


def forecast_month_end(conn: sqlite3.Connection, today: Optional[date] = None) -> dict:
    """Project this month's total spending if the day-to-day pace so far continues.

    Day-to-day spending (everything except fixed costs like rent) is averaged
    over the days elapsed, today included, then extended to the days still to come.
    """
    today = today or date.today()
    month = today.strftime("%Y-%m")
    budgets = _budgets_cents(conn)
    spent = _spent_cents_by_category(conn, month)

    total_spent = sum(spent.values())
    variable_spent = sum(c for cat, c in spent.items() if cat not in FIXED_CATEGORIES)
    daily_cents = variable_spent / today.day
    days_to_come = _days_left(month, today) - 1
    expected_cents = round(daily_cents * days_to_come)
    projected_cents = total_spent + expected_cents
    total_budget = sum(budgets.values())

    return {
        "month": month,
        "spent_so_far": to_euros(total_spent),
        "daily_average": to_euros(round(daily_cents)),
        "days_to_come": days_to_come,
        "expected_additional_spending": to_euros(expected_cents),
        "projected_total": to_euros(projected_cents),
        "total_budget": to_euros(total_budget),
        "projected_remaining": to_euros(total_budget - projected_cents),
    }


def can_afford(conn: sqlite3.Connection, amount: Amount, category: str, today: Optional[date] = None) -> dict:
    """Decide whether a planned purchase fits this month's budget.

    verdict: "no"    -> more than what is left this month
             "tight" -> fits now, but breaks the category budget or the month-end forecast
             "yes"   -> fits now and at month end
    """
    check_category(category)
    cents = to_cents(amount)
    if cents <= 0:
        raise ValueError("Amount must be greater than 0")
    today = today or date.today()
    month = today.strftime("%Y-%m")

    budgets = _budgets_cents(conn)
    spent = _spent_cents_by_category(conn, month)
    forecast = forecast_month_end(conn, today)
    expected_cents = to_cents(forecast["expected_additional_spending"])

    remaining_after = sum(budgets.values()) - sum(spent.values()) - cents
    category_after = budgets.get(category, 0) - spent.get(category, 0) - cents
    projected_after = remaining_after - expected_cents

    if remaining_after < 0:
        verdict = "no"
        summary = f"No: it costs {_fmt(cents)} but only {_fmt(remaining_after + cents)} is left this month."
    elif category_after < 0 or projected_after < 0:
        verdict = "tight"
        problems = []
        if category_after < 0:
            problems.append(f"it puts you over your {category} budget by {_fmt(-category_after)}")
        if projected_after < 0:
            problems.append(f"at your current pace you would end the month {_fmt(-projected_after)} over budget")
        summary = (
            f"Possible but tight: you would still have {_fmt(remaining_after)} left now, but "
            + " and ".join(problems) + "."
        )
    else:
        verdict = "yes"
        summary = (
            f"Yes, it fits: you would still have {_fmt(remaining_after)} left this month, "
            f"about {_fmt(projected_after)} after your usual spending until month end."
        )

    return {
        "amount": to_euros(cents),
        "category": category,
        "verdict": verdict,
        "summary": summary,  # ready-made sentence: small models rephrase better than they reason
        "remaining_after_purchase": to_euros(remaining_after),
        "category_remaining_after_purchase": to_euros(category_after),
        "expected_other_spending_until_month_end": to_euros(expected_cents),
        "projected_remaining_after_purchase": to_euros(projected_after),
    }


def daily_spending(conn: sqlite3.Connection, month: str, today: Optional[date] = None) -> dict:
    """Day-by-day spending of `month`, its running total, and the ideal pace to compare with.

    Ideal pace: fixed costs (rent) are due from day 1, the rest of the budget is
    spread evenly over the month. Running totals stop at today (the future is unknown).
    """
    check_month(month)
    today = today or date.today()
    year, mon = int(month[:4]), int(month[5:7])
    days_in_month = calendar.monthrange(year, mon)[1]

    budgets = _budgets_cents(conn)
    fixed = sum(c for cat, c in budgets.items() if cat in FIXED_CATEGORIES)
    variable = sum(c for cat, c in budgets.items() if cat not in FIXED_CATEGORIES)
    rows = conn.execute(
        "SELECT date, SUM(amount_cents) AS total FROM expenses WHERE substr(date, 1, 7) = ? GROUP BY date",
        (month,),
    )
    per_day = {r["date"]: r["total"] for r in rows}

    days, running = [], 0
    for d in range(1, days_in_month + 1):
        day = date(year, mon, d)
        spent = per_day.get(day.isoformat(), 0)
        running += spent
        days.append({
            "date": day.isoformat(),
            "spent": to_euros(spent),
            "cumulative": to_euros(running) if day <= today else None,
            "ideal": to_euros(fixed + round(variable * d / days_in_month)),
        })
    return {"month": month, "total_budget": to_euros(fixed + variable), "days": days}


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
