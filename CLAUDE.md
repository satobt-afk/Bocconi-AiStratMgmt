# CLAUDE.md — Personal Financial Agent

## Project scope
Personal Financial Agent is a student budgeting and financial guidance
application. The agent will eventually connect to students' financial
accounts and provide personalized budgeting guidance. This repository
currently contains only the initial project skeleton — no product
features are implemented yet.

## Structure
- `backend/` — FastAPI application (single process serves API + frontend)
  - `main.py` — application entry point; serves `frontend/` and `/health`
  - `account_connections.py` — connecting accounts, checking connection status
  - `transactions.py` — retrieving and categorizing transactions
  - `budgeting.py` — calculating student budgets
  - `model_client.py` — the only place that should call an external AI model
  - `advice.py` — generating guidance from budget and financial data
  - `daily_checks.py` — daily connection and data-freshness checks
  - `evaluation.py` — collecting feedback and comparing spending periods
- `frontend/` — plain HTML/CSS/JS, no framework
- `data/` — local data folder; never commit real financial data
- `tests/` — automated tests

## Startup command
```
uvicorn backend.main:app --reload
```
Then open http://127.0.0.1:8000 in a browser.

## Development conventions
- Write tests first for every new feature (TDD). A feature without a
  failing test written beforehand is not considered started.
- Never commit financial data or credentials. Real account data,
  transactions, and secrets stay out of git — see `.gitignore` and
  `data/README.md`.
- Any advice or guidance the agent produces must account for the
  possibility of missing, incomplete, or stale account data. Never
  present guidance as if data completeness and freshness are guaranteed.
- Keep dependencies minimal. The app must start without API keys.
- `backend/model_client.py` is the only module that should ever call an
  external AI model API.
