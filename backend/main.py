"""Application entry point: serves the frontend, the health check, and the JSON API.

The frontend never touches the database: it calls the /api/... endpoints
below, which validate input and delegate to transactions.py / budgeting.py.
"""

from datetime import date
from pathlib import Path
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import budgeting, transactions

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


class ExpenseIn(BaseModel):
    amount: float
    category: str
    date: str
    merchant: str = ""


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
            conn, expense.amount, expense.category, expense.date, merchant=expense.merchant
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
