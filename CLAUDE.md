# 1. What this is
For exchange students living on a fixed budget, we offer real-time spending control and personalized saving advice, using receipt scanning, auto-categorization, monthly/annual dashboards and an AI budget coach.
We believe exchange students spend better when they always know where they stand against their monthly budget and can ask "can I afford this?" before buying.
Done for the live demo means: add expenses (manually and by receipt photo with confirmation), per-category monthly budgets with history, dashboards, an AI coach that answers from the student's real data, and proactive saving alerts.

# 2. How to run it
Run these commands from the project root.
Create the virtual environment:
`python -m venv .venv`
Activate on macOS/Linux:
`source .venv/bin/activate`
Activate on Windows PowerShell:
`.venv\Scripts\Activate.ps1`
Install dependencies:
`python -m pip install -r requirements.txt`
Start the server:
`python -m uvicorn backend.main:app --reload`
Run tests:
`python -m pytest`
Open the page at `http://127.0.0.1:8000/`.
Demo data (separate database, never `data/budget.db`): `python -m backend.demo`, then start the server with `BUDGET_DB=data/demo.db`. Load the models before a demo: `python -m backend.warmup`.
Verify `http://127.0.0.1:8000/health` returns HTTP 200 and `{"status": "ok"}`.
One backend process must serve the page and API on the same port.

# 3. Where things live
`backend/` owns application logic; `backend/model_client.py` is the only file allowed to call the model.
`backend/receipt.py` turns a receipt photo into a proposed expense: the vision model reads it, Python validates every field, and nothing is saved until the student confirms.
`backend/agent.py` runs the AI coach: it defines the tools the model may call and the agent loop; tools only wrap tested functions from `budgeting.py` and `transactions.py`.
`frontend/` uses plain HTML, CSS, and JavaScript; do not introduce a frontend framework.
`data/` holds the local SQLite database (`budget.db`), never committed; demo data must use `source="synthetic"`.
`tests/` is where every feature starts, with a test describing the expected behavior.
`.claude/` holds shared Claude configuration; keep personal preferences out.
`NOTES.md` records decisions, temporary limitations, and changing project context.
`BACKLOG.md` holds future feature ideas, which do not authorize implementation.

# 4. How to behave
- State assumptions before acting; ask when uncertainty changes scope or expected behavior.
- Make the smallest change that solves the requested task; touch only relevant files.
- Write a test for the expected behavior first, confirm it fails for the expected reason, then implement.
- Keep financial calculations deterministic in Python; use the model to explain results.
- Data is only what the student entered; never imply the app knows about spending it was not told about.
- Label synthetic data clearly; never present a simulated connection or model response as real.
- Before calling work complete, run relevant tests and concrete checks; report results and anything unverified.
- Record consequential decisions and temporary workarounds in `NOTES.md`; keep future ideas in `BACKLOG.md`.

# 5. What not to do
- Do not add frameworks, databases, or dependencies unnecessary for the requested task.
- Do not implement unrequested features or expand the task with unrelated refactoring.
- Do not weaken, delete, or edit a test merely to make failing code pass.
- Never read or print `.env`; use `.env.example` to understand configuration names.
- Never commit credentials, account tokens, or real personal financial data.
- Do not send raw account identifiers or unnecessary personal details to the model.
- Do not move money, execute transactions, or turn budgeting guidance into investment recommendations.
- Do not claim verification succeeded unless you actually performed it.

# 6. Mistakes we have seen
<!-- Add one concise prevention rule after each observed mistake. -->
- This file once named a missing `backend/llm.py` and a wrong `/health` response, and `python -m pytest` failed because test tools were missing from `requirements.txt`. When you rename a file, change an endpoint, or add a tool, update this file and `requirements.txt` in the same commit.
