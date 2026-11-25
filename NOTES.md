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

- **2026-11-25 — Receipt scanning = vision model + Python validation + human confirmation.** Model: `qwen3-vl:2b-instruct` (1.9 GB, chosen for the 8 GB Mac). Ollama's structured output (`format` = JSON schema) forces the answer's shape. Python then fixes or flags the predictable errors: European dates (`23-11-2026`), `19,60`, future or very old dates, unknown categories. The form is pre-filled and saved only when the student taps Save (`source = "receipt"`).
- **2026-11-25 — Photos are redrawn on a white background in the browser** (max 1280 px, JPEG) before upload. In testing, a transparent PNG looked "entirely black" to the model, and it invented a whole receipt. Photos are not stored.

- **2026-11-25 — Charts are plain SVG drawn in the browser, with no chart library.** They work offline (the demo room may have no internet) and add no dependency. Python computes the data (`/api/daily`, `/api/year`); the browser only draws it.
- **2026-11-25 — "Ideal pace" = rent due on day 1, the rest of the budget spread evenly over the month.** This is the same split as the forecast, so a rent payment on the 1st does not look like overspending.

- **2026-11-25 — Proactive tips are rules in Python (`advice.py`), not AI.** They appear instantly on Home, with no 10 s model wait, and they are explainable. "Usual" = the average spent in that category by the same day of the month, over the previous active months (up to 3). A category that was never used before is compared with its budget pace instead: with the demo data, "usually 0 €" produced a nonsense tip ("skip 1 ride" for a transport pass). A tip needs ≥ 10 € and ≥ 25 % above usual; at most 3 tips, biggest first; rent never gets one. The coach can read the same tips through `get_saving_tips`.

- **2026-11-25 — Demo data lives in a separate database** (`data/demo.db`, chosen with `BUDGET_DB`), rebuilt by `python -m backend.demo`. The story is generated relative to today, so the demo moments (restaurant tip, "tight" 150 € weekend, last month over budget) exist on any date; tests check 6 different dates. The demo receipt is fictional ("Supermercato Stella") and dated today.

- **2026-11-25 — Tips explain WHY a category runs ahead** (`advice._explain`, still plain Python). The checks, in order: pricier than usual (average ≥ 1.3× the usual, about the same count) → "pick cheaper places, you would have saved X"; more often than usual (≥ 2 more than usual) → the general tip; one place taking ≥ 50% of the category (≥ 2 visits) → name it; ≥ 70% on weekends (≥ 2) → a weekend limit. If none applies, there is no insight. The coach's saving answers also get the 📌 card with Python's exact wording: in testing, Qwen said "28 €, which is 39 € more than usual" (39 € was the total saving, not the difference per meal).

## Temporary limitations

- One budget per category, the same every month (no per-month override yet). Past months are compared with today's budgets: if you change a budget, the yearly chart changes too.
- The yearly view uses the calendar year (Jan–Dec), not the exchange period.
- Single user: no accounts or authentication.
- AI coach: answers take ~7–12 s, and the first question after Ollama starts is slower (the model has to load). Italian answers are weaker (it once invented a "weekly" budget).
- AI coach is read-only: it cannot add expenses yet (planned with a confirmation step).
- The chat is lost when the page reloads.
- Receipt scanning was tested on clean, generated receipts only, not yet on real crumpled photos. On the M1 with 8 GB, a NEW photo takes ~15 s at 960 px (it took ~25 s at 1280 px, with the same result). Only a photo that was already read comes back in ~3 s, because Ollama caches it: an earlier note claiming "~3 s" was wrong. Both models fit in memory together (2.2 GB each), and `python -m backend.warmup` loads them before a demo.
