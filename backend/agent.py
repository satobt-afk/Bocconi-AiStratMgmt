"""The AI budget coach: a tool-calling agent loop.

Chatbot vs agent: a chatbot answers from what the model "remembers".
This agent lets the model CHOOSE tools (Python functions below), runs
them on the student's real data, gives the results back, and only then
lets the model write the answer. All numbers come from Python.

    question -> model -> tool call? -> run tool -> result -> model -> ... -> answer
"""

import json
import sqlite3
from datetime import date
from typing import Callable, Dict, List, Optional

from backend import budgeting, transactions

MAX_HISTORY = 10  # previous user/assistant messages kept as context

SYSTEM_PROMPT = """You are a friendly budget coach for exchange students living on a fixed monthly budget.
Today is {today}. All amounts are in euros.

Rules:
- Never invent numbers. Always call a tool to get amounts, then use exactly the numbers it returns.
- For "can I afford / can I buy / should I spend" questions, call can_afford with the most fitting category
  (trips and weekends away = travel, eating out = restaurant, supermarket = groceries, going out = leisure).
- In tool results, "spent" is money already spent and "remaining" is money left. A negative remaining means over budget.
- can_afford returns a "summary" sentence: base your answer on it and keep its meaning
  ("Possible but tight" is not a no).
- Talk to the student as "you". Quote the key numbers from the tool (for example what is left after the purchase).
- Answer in the same language as the student, in at most 4 short sentences, with one concrete saving tip when useful.
- You give budgeting guidance only: no investment advice, and you cannot move money."""

TOOLS = [
    {
        "name": "get_budget_status",
        "description": "This month's budget: total budget, spent, remaining, days left, and per category budget/spent/remaining/over_budget.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "forecast_month_end",
        "description": "Projection of total spending at the end of this month if the current day-to-day pace continues.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "can_afford",
        "description": "Check whether a planned purchase fits this month's budget. Returns verdict yes / tight / no with the numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Price in euros"},
                "category": {"type": "string", "enum": list(transactions.CATEGORIES)},
            },
            "required": ["amount", "category"],
        },
    },
    {
        "name": "get_recent_expenses",
        "description": "The 10 most recent expenses of this month (date, amount, category, merchant).",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _tool_functions(conn: sqlite3.Connection, today: date) -> Dict[str, Callable[..., dict]]:
    month = today.strftime("%Y-%m")
    return {
        "get_budget_status": lambda: budgeting.get_budget_status(conn, month, today=today),
        "forecast_month_end": lambda: budgeting.forecast_month_end(conn, today=today),
        "can_afford": lambda amount, category: budgeting.can_afford(conn, float(amount), category, today=today),
        "get_recent_expenses": lambda: {"expenses": transactions.list_expenses(conn, month=month)[-10:]},
    }


def _run_tool(functions: Dict[str, Callable[..., dict]], name: str, arguments: dict) -> dict:
    """Run one tool; any problem becomes an error message the model can read and fix."""
    if name not in functions:
        return {"error": f"Unknown tool {name!r}. Available tools: {sorted(functions)}"}
    try:
        return functions[name](**arguments)
    except (TypeError, ValueError) as error:
        return {"error": f"Invalid arguments for {name}: {error}"}


def run_agent(
    conn: sqlite3.Connection,
    client,
    history: List[dict],
    user_message: str,
    today: Optional[date] = None,
    max_steps: int = 4,
) -> dict:
    """Answer one student message. Returns {"reply": str, "tools_used": [{"name", "arguments"}]}."""
    today = today or date.today()
    functions = _tool_functions(conn, today)

    past = [
        {"role": m["role"], "content": str(m.get("content", ""))}
        for m in history
        if m.get("role") in ("user", "assistant")
    ][-MAX_HISTORY:]
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT.format(today=today.isoformat())}]
        + past
        + [{"role": "user", "content": user_message}]
    )
    tools_used = []

    for _ in range(max_steps):
        reply = client.chat(messages, TOOLS)
        if not reply.tool_calls:
            return {"reply": reply.content, "tools_used": tools_used}

        messages.append({"role": "assistant", "content": reply.content, "tool_calls": reply.tool_calls})
        for call in reply.tool_calls:
            result = _run_tool(functions, call.name, call.arguments)
            tools_used.append({"name": call.name, "arguments": call.arguments})
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": json.dumps(result),
            })

    return {
        "reply": "Sorry, I couldn't finish answering that. Could you ask in a simpler way?",
        "tools_used": tools_used,
    }
