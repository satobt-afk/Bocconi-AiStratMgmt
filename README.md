# 🐷 Personal Financial Agent — a budget coach for exchange students

> **For exchange students living on a fixed budget, we offer real-time spending control and personalized saving advice, using receipt scanning, auto-categorization, monthly/annual dashboards and an AI budget coach.**

Course project — *AI in Strategic Management* (30754), Bocconi University.

## The problem
Exchange students arrive in a new city for one or two semesters with a fixed amount of money (savings, a scholarship, family support). Prices are unfamiliar, there are many one-off temptations (weekend trips, dinners with new friends), and nobody tells them *during* the month that they are drifting. They usually discover the problem at the end of the month, when it is too late.

## Hypothesis
We believe exchange students make better spending decisions when they can see, at any moment, where they stand against their monthly budget, and can ask *"can I afford this?"* before buying, with an answer based on their own numbers.

## What the app does

| Feature | Status |
|---|---|
| ➕ Add an expense manually (amount, category, date, place) | ✅ built |
| 🎯 Monthly budget per category (rent, groceries, restaurant, transport, leisure, travel, other) | ✅ built |
| 🏠 Monthly status: what is left, days left, over-budget alerts; months reset on the 1st, history kept | ✅ built |
| 🤖 AI budget coach: answers questions like *"Can I afford a 150 € weekend?"* using tools on the student's real data | ✅ built |
| 📸 Receipt scanning: a photo is read by a vision model (`qwen3-vl:2b-instruct`), checked by Python, then confirmed by the student | ✅ built |
| 📊 Dashboards: spending by category (donut), day-by-day spending vs ideal pace, month-by-month comparison over the year | ✅ built |
| 💡 Proactive advice: a category running faster than usual (compared with the student's previous months at the same date, or with the budget pace) gets a tip with a concrete action; one tap asks the coach | ✅ built |

## How the AI is used (and kept honest)
The coach is an **agent**, not a chatbot. The language model chooses which tool to call (`can_afford`, `get_budget_status`, `forecast_month_end`, `get_saving_tips`, `get_recent_expenses`). Python runs that tool on the real data, and the model then phrases the answer.

- **The model never computes money.** All numbers come from tested Python functions.
- **Errors stay visible.** The app shows which tool was used ("checked 150 € in Travel"), and Python's own verdict word for word ("📌 From your data").
- **The model is replaceable.** Today it is a small local model (`qwen2.5:3b` via [Ollama](https://ollama.com)). `backend/model_client.py` is the only file that talks to a model, so we can switch to the Claude API without touching the rest.

Design decisions and known limitations are in [NOTES.md](NOTES.md).

## Architecture
```
Phone / browser ── HTML + CSS + JS (frontend/)
        │  JSON over HTTP
        ▼
FastAPI (backend/main.py)
   ├── transactions.py / budgeting.py ── SQLite (data/budget.db, never committed)
   └── agent.py ── model_client.py ── Ollama (local Qwen model)
```

## How to run it
See [CLAUDE.md §2](CLAUDE.md#2-how-to-run-it) for the exact commands. You also need:

1. [Ollama](https://ollama.com/download) running, with the models downloaded: `ollama pull qwen2.5:3b` (coach) and `ollama pull qwen3-vl:2b-instruct` (receipts)
2. Then open the app at `http://127.0.0.1:8000` → 🎯 set budgets → ➕ add expenses → 🤖 ask the coach.

To open it on a phone on the same Wi-Fi, start the server with `--host 0.0.0.0` and open `http://<your-computer-ip>:8000`. This makes the app reachable by anyone on that network, so only do it on a network you trust.

## Evaluation approach
We plan to ask exchange students to use the app for one month, then compare with how they managed the previous months: did they overspend less, and did they feel more in control? This is a first evaluation idea, not proof that the app causes any improvement.
