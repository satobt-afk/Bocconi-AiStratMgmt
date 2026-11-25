# Notes

Decisions, temporary limitations, and changing project context (see CLAUDE.md §3).

## Decisions

- **2026-11-25 — SQLite for expenses and budgets.** Expenses must persist between sessions, so a database is necessary. SQLite ships with Python (`sqlite3`): no server and no new dependency. The file lives at `data/budget.db`, which `.gitignore` already excludes.
- **2026-11-25 — Money stored as integer cents.** Floats drift (`0.1 + 0.2 != 0.3`). Amounts are converted with `Decimal` on input and summed as integers.
- **2026-11-25 — Monthly "reset" = filtering by month, never deleting.** Each month's status only counts expenses dated in that month, so the history stays available for the yearly view.
- **2026-11-25 — Every expense has a `source`** (`manual`, `receipt`, `synthetic`) so demo data is always labelled and never shown as real.

- **2026-11-25 — AI coach = tool-calling agent on a local model.** Model: `qwen2.5:3b` via Ollama. In a benchmark on an M1 with 8 GB of RAM, `qwen3:4b` took about 100 s per answer, because of its built-in "thinking", and leaked its reasoning even with `think: false`. `qwen2.5:3b` took about 7–12 s per answer and picked the right tool every time.
- **2026-11-25 — The model never computes money.** Tools (`can_afford`, `forecast_month_end`, …) compute in Python. `can_afford` also returns a ready-made `summary` sentence: the 3B model rephrased it well, but on its own it turned "tight" into "no".
- **2026-11-25 — Categories are guided and corrected in Python.** In French, the 3B model filed "un week-end à 150 €" under restaurant, and later sent "week-end" as the category itself. The tool now lists keywords per category in EN/FR/IT (`CATEGORY_HINTS`), and Python maps any of those words to the real category.
- **2026-11-25 — Python's verdict is shown word for word.** The model still sometimes turns "tight" into "no" (especially in FR/IT), so the app shows can_afford's own `summary` under the reply ("📌 From your data").
- **2026-11-25 — Forecast = day-to-day pace.** Non-rent spending is averaged over the days elapsed, then extended to the rest of the month.
- **2026-11-25 — Conversation history lives in the browser** and is re-sent with each question (the last 10 messages). The backend stays stateless.

## Temporary limitations

- One budget per category, the same every month (no per-month override yet).
- The yearly view uses the calendar year (Jan–Dec), not the exchange period.
- Single user: no accounts or authentication.
- AI coach: answers take ~7–12 s, and the first question after Ollama starts is slower (the model has to load). Italian answers are weaker (it once invented a "weekly" budget).
- AI coach is read-only: it cannot add expenses yet (planned with a confirmation step).
- The chat is lost when the page reloads.
