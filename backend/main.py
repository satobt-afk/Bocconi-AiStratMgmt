"""Application entry point: serves the frontend, the health check, and the JSON API.

The frontend never touches the database: it calls the /api/... endpoints
below, which validate input and delegate to transactions.py / budgeting.py.
"""

import base64
import binascii
from datetime import date
from pathlib import Path
from typing import Iterator, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import budgeting, transactions
from backend.agent import run_agent
from backend.receipt import read_receipt
from backend.model_client import ModelUnavailable, get_model_client

app = FastAPI(title="Personal Financial Agent")

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
def month_status(month: Optional[str] = None, conn=Depends(get_conn)):
    """Budget status of `month` (YYYY-MM), the current month by default."""
    try:
        return budgeting.get_budget_status(conn, month or date.today().strftime("%Y-%m"))
    except ValueError as error:
        raise _bad_input(error)


@app.get("/api/expenses")
def list_expenses(month: Optional[str] = None, conn=Depends(get_conn)):
    try:
        return transactions.list_expenses(conn, month=month)
    except ValueError as error:
        raise _bad_input(error)


@app.post("/api/expenses", status_code=201)
def create_expense(expense: ExpenseIn, conn=Depends(get_conn)):
    try:
        new_id = transactions.add_expense(
            conn, expense.amount, expense.category, expense.date,
            merchant=expense.merchant, source=expense.source,
        )
    except ValueError as error:
        raise _bad_input(error)
    return next(e for e in transactions.list_expenses(conn) if e["id"] == new_id)


@app.get("/api/budgets")
def list_budgets(conn=Depends(get_conn)):
    return budgeting.get_budgets(conn)


@app.put("/api/budgets/{category}")
def update_budget(category: str, budget: BudgetIn, conn=Depends(get_conn)):
    try:
        budgeting.set_budget(conn, category, budget.amount)
    except ValueError as error:
        raise _bad_input(error)
    return {"category": category, "budget": budgeting.get_budgets(conn)[category]}


@app.post("/api/chat")
def chat(body: ChatIn, conn=Depends(get_conn), model=Depends(get_model)):
    """Ask the AI budget coach. The browser keeps the conversation and sends it back each time."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is empty")
    try:
        return run_agent(conn, model, body.history, message)
    except ModelUnavailable:
        raise HTTPException(
            status_code=503,
            detail="The AI coach is offline. Start the Ollama app on this computer and try again.",
        )


@app.post("/api/receipts/scan")
def scan_receipt(body: ReceiptIn, model=Depends(get_model)):
    """Read a receipt photo and return a PROPOSED expense. Nothing is saved: the student confirms."""
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
def daily(month: Optional[str] = None, conn=Depends(get_conn)):
    """Day-by-day spending of a month with the ideal pace (month evolution chart)."""
    try:
        return budgeting.daily_spending(conn, month or date.today().strftime("%Y-%m"))
    except ValueError as error:
        raise _bad_input(error)


@app.get("/api/year")
def year_overview(year: Optional[int] = None, conn=Depends(get_conn)):
    """Spent vs budget for each month of a year (month-by-month comparison chart)."""
    year = year or date.today().year
    if not 2000 <= year <= 2100:
        raise HTTPException(status_code=422, detail="Year must be between 2000 and 2100")
    return {"year": year, "months": budgeting.monthly_totals(conn, year)}
