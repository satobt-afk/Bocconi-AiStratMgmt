# 1. What this is
We believe students make better budgeting decisions when guidance uses complete, current financial data.
Our users are students managing everyday spending and limited income.
Done by 26 November means a working demo of budgeting guidance, daily connection checks, and feedback comparing the first month of use with the previous three months.

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
Verify `http://127.0.0.1:8000/health` returns HTTP 200 and `{"status": "ok"}`.
One backend process must serve the page and API on the same port.

# 3. Where things live
`backend/` owns application logic; `backend/model_client.py` is the only file allowed to call the model.
`backend/agent.py` runs the AI coach: it defines the tools the model may call and the agent loop; tools only wrap tested functions from `budgeting.py` and `transactions.py`.
`frontend/` uses plain HTML, CSS, and JavaScript; do not introduce a frontend framework.
`data/` holds retrieval material; use synthetic or explicitly approved, non-sensitive material.
`tests/` is where every feature starts, with a test describing the expected behavior.
`.claude/` holds shared Claude configuration; keep personal preferences out.
`NOTES.md` records decisions, temporary limitations, and changing project context.
`BACKLOG.md` holds future feature ideas, which do not authorize implementation.

# 4. How to behave
- State assumptions before acting; ask when uncertainty changes scope or expected behavior.
- Make the smallest change that solves the requested task; touch only relevant files.
- Write a test for the expected behavior first, confirm it fails for the expected reason, then implement.
- Keep financial calculations deterministic in Python; use the model to explain results.
- Treat disconnected accounts, missing accounts, and stale data as different limitations; never imply complete coverage without evidence.
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
