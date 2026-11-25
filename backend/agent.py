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

from backend import advice, budgeting, transactions

MAX_HISTORY = 10  # previous user/assistant messages kept as context

# Small models map words to categories poorly outside English, so we spell it out
# in the languages our users write in (English, French, Italian).
CATEGORY_HINTS = """travel = trip, weekend away, week-end, voyage, viaggio, gita, flight, vol, volo, train, Ryanair, hotel, hostel
restaurant = eating out, dinner, cena, dîner, lunch, pranzo, déjeuner, restaurant, ristorante, pizza, aperitivo, café
groceries = supermarket, courses, spesa, food shopping, Esselunga, Carrefour, Lidl
leisure = cinema, concert, party, soirée, festa, museum, gym, sport, clothes, vêtements, vestiti
transport = metro, bus, tram, taxi, ATM pass, abonnement, abbonamento
rent = rent, loyer, affitto
other = anything else"""

# The same hints as a lookup table, for when the model sends a hint word
# (e.g. "week-end") as the category instead of the category itself.
CATEGORY_ALIASES = {
    word.strip().lower(): category.strip()
    for line in CATEGORY_HINTS.splitlines()
    for category, words in [line.split("=", 1)]
    for word in words.split(",") + [category]
}


def _normalize_category(category: str) -> str:
    return CATEGORY_ALIASES.get(str(category).strip().lower(), category)
SYSTEM_PROMPT = """You are a friendly budget coach for exchange students living on a fixed monthly budget.
Today is {today}. All amounts are in euros.

Rules:
- Never invent numbers. Always call a tool to get amounts, then use exactly the numbers it returns.
- For "can I afford / can I buy / should I spend" questions, call can_afford with the most fitting category:
{hints}
- For "where can I save / where am I spending too much" questions, call get_saving_tips and pass on its tips,
  including the "insight" (why it happens) when there is one.
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
                "category": {
                    "type": "string",
                    "enum": list(transactions.CATEGORIES),
                    "description": CATEGORY_HINTS,
                },
            },
            "required": ["amount", "category"],
        },
    },
    {
        "name": "get_saving_tips",
        "description": "Categories where the student spends faster than usual this month, each with a concrete saving tip. Use it for 'where can I save?' or 'where am I overspending?'.",
        "parameters": {"type": "object", "properties": {}},
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
        "can_afford": lambda amount, category: budgeting.can_afford(
            conn, float(amount), _normalize_category(category), today=today
        ),
        "get_recent_expenses": lambda: {"expenses": transactions.list_expenses(conn, month=month)[-10:]},
        "get_saving_tips": lambda: {"tips": advice.saving_tips(conn, today=today)},
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
    """Answer one student message.

    Returns {"reply": str, "tools_used": [{"name", "arguments"}], "facts": [str]}.
    "facts" are Python's own summary sentences (from can_afford), shown word for
    word in the app so a badly rephrased reply cannot hide the real verdict.
    """
    today = today or date.today()
    functions = _tool_functions(conn, today)

    past = [
        {"role": m["role"], "content": str(m.get("content", ""))}
        for m in history
        if m.get("role") in ("user", "assistant")
    ][-MAX_HISTORY:]
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT.format(today=today.isoformat(), hints=CATEGORY_HINTS)}]
        + past
        + [{"role": "user", "content": user_message}]
    )
    tools_used = []
    facts = []

    for _ in range(max_steps):
        reply = client.chat(messages, TOOLS)
        if not reply.tool_calls:
            return {"reply": reply.content, "tools_used": tools_used, "facts": facts}

        messages.append({"role": "assistant", "content": reply.content, "tool_calls": reply.tool_calls})
        for call in reply.tool_calls:
            if "category" in call.arguments:  # e.g. "week-end" -> "travel"
                call.arguments = {**call.arguments, "category": _normalize_category(call.arguments["category"])}
            result = _run_tool(functions, call.name, call.arguments)
            tools_used.append({"name": call.name, "arguments": call.arguments})
            if "summary" in result:
                facts.append(result["summary"])
            for tip in result.get("tips", []):  # saving tips: show Python's wording too
                facts.append(" ".join(part for part in (tip["insight"], tip["tip"]) if part))
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": json.dumps(result),
            })

    return {
        "reply": "Sorry, I couldn't finish answering that. Could you ask in a simpler way?",
        "tools_used": tools_used,
        "facts": facts,
    }
