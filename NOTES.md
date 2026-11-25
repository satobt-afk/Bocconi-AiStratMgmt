# Notes

Decisions, temporary limitations, and changing project context (see CLAUDE.md §3).

## Decisions

- **2026-11-25 — SQLite for expenses and budgets.** Expenses must persist between sessions, so a database is necessary. SQLite ships with Python (`sqlite3`): no server and no new dependency. The file lives at `data/budget.db`, which `.gitignore` already excludes.
- **2026-11-25 — Money stored as integer cents.** Floats drift (`0.1 + 0.2 != 0.3`). Amounts are converted with `Decimal` on input and summed as integers.
- **2026-11-25 — Monthly "reset" = filtering by month, never deleting.** Each month's status only counts expenses dated in that month, so the history stays available for the yearly view.
- **2026-11-25 — Every expense has a `source`** (`manual`, `receipt`, `synthetic`) so demo data is always labelled and never shown as real.

## Temporary limitations

- One budget per category, the same every month (no per-month override yet).
- The yearly view uses the calendar year (Jan–Dec), not the exchange period.
- Single user: no accounts or authentication.
