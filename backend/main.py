"""Application entry point: serves the frontend, the health check, and the JSON API.

The frontend never touches the database: it calls the /api/... endpoints
below, which validate input and delegate to transactions.py / budgeting.py.
"""

import base64
import binascii
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import access, advice, budgeting, sessions, transactions
from backend.agent import run_agent
from backend.db import GUEST_HOURS, create_user, delete_expired_guests
from backend.limits import RateLimiter
from backend.demo import seed_demo
from backend.model_client import ModelUnavailable, get_model_client
from backend.receipt import read_receipt

# No automatic /docs, /redoc or /openapi.json: on the internet they would describe the whole API to anyone.
app = FastAPI(title="Personal Financial Agent", docs_url=None, redoc_url=None, openapi_url=None)

# Content Security Policy: the page may only load its own files. Inline style attributes are
# allowed (the charts and cards use them); photos are previewed from data:/blob: URLs.
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"  # access links carry a secret in the URL
    response.headers["Content-Security-Policy"] = CSP
    if request.url.path.startswith("/join/"):
        response.headers["Cache-Control"] = "no-store"
    if os.environ.get("APP_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Serve frontend assets (styles.css, app.js, etc.) under /static.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def get_conn() -> Iterator:
    """One database connection per request; tests replace it with an in-memory one."""
    conn = transactions.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn=Depends(get_conn)) -> str:
    """Who is asking: the user of the session cookie, looked up by the server.

    The browser never says who it is; a missing or unknown cookie is refused (401).
    Every endpoint that touches data, or the AI models, depends on this.
    """
    user = sessions.user_for_token(conn, request.cookies.get(sessions.COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="This app is private: open your access link or the demo link.")
    return user


# (max requests, per seconds) for the endpoints that use the Mac's AI. Guests (demo
# visitors) get less than real accounts: the AI must stay usable for its owners.
LIMITS = {
    "chat": {"guest": (6, 60), "member": (20, 60)},
    "scan": {"guest": (3, 60), "member": (10, 60)},
}
# New demo sandboxes: at most this many per hour, and alive at the same time.
DEMO_CAPS = {"per_hour": 20, "active": 50}

limiter = RateLimiter()


def user_kind(conn, user_id: str) -> str:
    """"guest" for a demo sandbox, "member" for a real account."""
    row = conn.execute("SELECT label FROM users WHERE id = ?", (user_id,)).fetchone()
    return "guest" if row and row[0] == "guest" else "member"


def enforce_limit(action: str, conn, user_id: str) -> None:
    """Refuse with 429 when this user has used `action` too often in the last minute."""
    limit, window = LIMITS[action][user_kind(conn, user_id)]
    if not limiter.allow(f"{user_id}:{action}", limit, window):
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests: please wait a minute (max {limit} per minute).",
        )


def get_model():
    """The language model client; tests replace it with a scripted fake."""
    return get_model_client()


class ChatIn(BaseModel):
    message: str
    history: List[dict] = Field(default_factory=list)


class ExpenseIn(BaseModel):
    amount: float
    category: str
    date: str
    merchant: str = ""
    source: Literal["manual", "receipt"] = "manual"  # "synthetic" demo data is never created through the API


class ReceiptIn(BaseModel):
    image: str  # base64, optionally as a data URL ("data:image/jpeg;base64,...")


MAX_IMAGE_BYTES = 10 * 1024 * 1024


class BudgetIn(BaseModel):
    amount: float


def _bad_input(error: ValueError) -> HTTPException:
    """Turn a validation error from the business logic into HTTP 422."""
    return HTTPException(status_code=422, detail=str(error))


@app.get("/health")
def health():
    """Simple liveness check used to confirm the server is running."""
    return {"status": "ok"}


@app.get("/")
def read_index():
    """Serve the frontend page."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/categories")
def list_categories():
    return {"categories": list(transactions.CATEGORIES)}


@app.get("/api/status")
def month_status(month: Optional[str] = None, conn=Depends(get_conn), user=Depends(current_user)):
    """Budget status of `month` (YYYY-MM), the current month by default."""
    try:
        return budgeting.get_budget_status(conn, user, month or date.today().strftime("%Y-%m"))
    except ValueError as error:
        raise _bad_input(error)


@app.get("/api/expenses")
def list_expenses(month: Optional[str] = None, conn=Depends(get_conn), user=Depends(current_user)):
    try:
        return transactions.list_expenses(conn, user, month=month)
    except ValueError as error:
        raise _bad_input(error)


@app.post("/api/expenses", status_code=201)
def create_expense(expense: ExpenseIn, conn=Depends(get_conn), user=Depends(current_user)):
    try:
        new_id = transactions.add_expense(
            conn, user, expense.amount, expense.category, expense.date,
            merchant=expense.merchant, source=expense.source,
        )
    except ValueError as error:
        raise _bad_input(error)
    return next(e for e in transactions.list_expenses(conn, user) if e["id"] == new_id)


@app.delete("/api/expenses/{expense_id}", status_code=204)
def remove_expense(expense_id: int, conn=Depends(get_conn), user=Depends(current_user)):
    """Delete one of YOUR expenses (to fix a mistake). Someone else's id gets the same 404 as a missing one."""
    if not transactions.delete_expense(conn, user, expense_id):
        raise HTTPException(status_code=404, detail="Expense not found")


@app.get("/api/budgets")
def list_budgets(conn=Depends(get_conn), user=Depends(current_user)):
    return budgeting.get_budgets(conn, user)


@app.put("/api/budgets/{category}")
def update_budget(category: str, budget: BudgetIn, conn=Depends(get_conn), user=Depends(current_user)):
    try:
        budgeting.set_budget(conn, user, category, budget.amount)
    except ValueError as error:
        raise _bad_input(error)
    return {"category": category, "budget": budgeting.get_budgets(conn, user)[category]}


@app.post("/api/chat")
def chat(body: ChatIn, conn=Depends(get_conn), user=Depends(current_user), model=Depends(get_model)):
    """Ask the AI budget coach. The browser keeps the conversation and sends it back each time."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is empty")
    enforce_limit("chat", conn, user)
    try:
        return run_agent(conn, user, model, body.history, message)
    except ModelUnavailable:
        raise HTTPException(
            status_code=503,
            detail="The AI coach is offline. Start the Ollama app on this computer and try again.",
        )


@app.post("/api/receipts/scan")
def scan_receipt(body: ReceiptIn, conn=Depends(get_conn), user=Depends(current_user), model=Depends(get_model)):
    """Read a receipt photo and return a PROPOSED expense. Nothing is saved: the student confirms.
    Signed-in users only, and rate-limited: it uses the Mac's AI."""
    enforce_limit("scan", conn, user)
    image = body.image.split(",", 1)[1] if body.image.startswith("data:") else body.image
    try:
        raw = base64.b64decode(image, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="The photo could not be read. Try another one.")
    if not raw:
        raise HTTPException(status_code=422, detail="No photo received.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="The photo is too large.")
    try:
        return read_receipt(model, image)
    except ModelUnavailable:
        raise HTTPException(
            status_code=503,
            detail="The receipt reader is offline. Start the Ollama app on this computer and try again.",
        )


@app.get("/api/daily")
def daily(month: Optional[str] = None, conn=Depends(get_conn), user=Depends(current_user)):
    """Day-by-day spending of a month with the ideal pace (month evolution chart)."""
    try:
        return budgeting.daily_spending(conn, user, month or date.today().strftime("%Y-%m"))
    except ValueError as error:
        raise _bad_input(error)


@app.get("/api/year")
def year_overview(year: Optional[int] = None, conn=Depends(get_conn), user=Depends(current_user)):
    """Spent vs budget for each month of a year (month-by-month comparison chart)."""
    year = year or date.today().year
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=422, detail="Year must be between 2000 and 2100")
    return {"year": year, "months": budgeting.monthly_totals(conn, user, year)}


@app.get("/api/tips")
def tips(conn=Depends(get_conn), user=Depends(current_user)):
    """Proactive saving tips for the current month (computed in Python, shown on Home)."""
    return {"tips": advice.saving_tips(conn, user)}



# ---------- Ways in: personal access links and the demo mode ----------



def demo_enabled() -> bool:
    """The demo door is closed unless the server is started with DEMO_MODE=on."""
    return os.environ.get("DEMO_MODE") == "on"


def _signed_in(response, conn, user_id: str, max_age: Optional[int] = None):
    settings = sessions.cookie_settings()
    if max_age is not None:
        settings["max_age"] = max_age
    response.set_cookie(value=sessions.new_session(conn, user_id), **settings)
    return response


LINK_PROBLEM_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Link not valid</title>
<link rel="stylesheet" href="/static/styles.css"></head><body><div class="app locked-page">
<div class="logo">🔒</div><h1>This link no longer works</h1>
<p class="muted">Access links work once and only for 15 minutes. Ask for a new one.</p></div></body></html>"""


DEMO_FULL_PAGE = LINK_PROBLEM_PAGE.replace("Link not valid", "Demo busy").replace(
    "This link no longer works", "The demo is busy").replace(
    "Access links work once and only for 15 minutes. Ask for a new one.", "Too many demo visitors right now. Try again later.")


SIGN_IN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sign in</title>
<link rel="stylesheet" href="/static/styles.css"></head><body><div class="app locked-page">
<div class="logo">🐷</div><h1>Your budget coach</h1>
<p class="muted">Tap the button to sign in on this device.</p>
<form method="post" action="/join/{token}"><button type="submit" class="primary demo-btn">Sign in</button></form>
</div></body></html>"""


@app.get("/join/{token}")
def join_page(token: str, conn=Depends(get_conn)):
    """Opening an access link only SHOWS a "Sign in" button; it does not use the link up.

    Messages, Notes, WhatsApp, Mail... fetch links to build previews: a link used up
    on GET was consumed by the preview before the person could open it. Previews
    never press buttons, so only the POST below signs in.
    """
    if not access.link_is_usable(conn, token):
        return HTMLResponse(LINK_PROBLEM_PAGE, status_code=400)
    # The token is URL-safe base64 (letters, digits, - and _): safe to put back in the form.
    return HTMLResponse(SIGN_IN_PAGE.replace("{token}", token))


@app.post("/join/{token}")
def join(token: str, conn=Depends(get_conn)):
    """The "Sign in" button: uses the link (once) and signs this browser in to its account."""
    user_id = access.redeem_access_link(conn, token)
    if user_id is None:
        return HTMLResponse(LINK_PROBLEM_PAGE, status_code=400)
    return _signed_in(RedirectResponse("/", status_code=303), conn, user_id)


@app.get("/demo")
def demo(request: Request, conn=Depends(get_conn)):
    """Demo mode (only with DEMO_MODE=on): a new private sandbox, pre-filled with the demo story."""
    if not demo_enabled():
        raise HTTPException(status_code=404)
    # A browser that is already signed in keeps its session: another website could
    # otherwise send a signed-in owner here and swap their session for a sandbox.
    if sessions.user_for_token(conn, request.cookies.get(sessions.COOKIE_NAME)):
        return RedirectResponse("/", status_code=303)
    delete_expired_guests(conn)  # sandboxes older than 24 h go before a new one is made
    created = [r[0] for r in conn.execute("SELECT created_at FROM users WHERE label = 'guest'")]
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")  # same format as created_at
    if len(created) >= DEMO_CAPS["active"] or sum(c > hour_ago for c in created) >= DEMO_CAPS["per_hour"]:
        return HTMLResponse(DEMO_FULL_PAGE, status_code=429)
    guest = create_user(conn, label="guest")
    seed_demo(conn, guest)
    return _signed_in(RedirectResponse("/", status_code=303), conn, guest, max_age=GUEST_HOURS * 3600)


@app.get("/api/me")
def me(request: Request, conn=Depends(get_conn)):
    """Public: lets the page decide between the app and the "private app" screen. Reveals no data."""
    user = sessions.user_for_token(conn, request.cookies.get(sessions.COOKIE_NAME))
    kind = user_kind(conn, user) if user else None
    return {"signed_in": user is not None, "kind": kind, "demo_available": demo_enabled()}
