"""Demo data: three months in the life of an exchange student in Milan.

Run it before a demo:

    python -m backend.demo

It (re)creates data/demo.db, never your real data/budget.db, and prints how
to start the app on it. Every expense is labelled source="synthetic".

The story is built relative to today, so the key moments of the demo script
exist whatever the date: restaurant spending runs ahead (💡 tip), a 150 €
weekend trip is "possible but tight", and last month went over budget.
"""

import calendar
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from backend.budgeting import set_budget
from backend.db import create_user
from backend.transactions import DEFAULT_DB_PATH, add_expense, connect

DEMO_DB_PATH = DEFAULT_DB_PATH.parent / "demo.db"
DEMO_RECEIPT_PATH = DEFAULT_DB_PATH.parent / "demo-receipt.jpg"

BUDGETS = {"rent": 450, "groceries": 180, "restaurant": 70, "transport": 35,
           "leisure": 70, "travel": 80, "other": 25}  # 910 € a month

# (day, amount, category, merchant) for a typical past month
TYPICAL_MONTH = [
    (1, 450, "rent", "Rent"),
    (1, 35, "transport", "ATM monthly pass"),
    (4, 38, "groceries", "Esselunga"),
    (6, 15, "restaurant", "Pizza al taglio"),
    (9, 25, "leisure", "Cinema"),
    (11, 38, "groceries", "Lidl"),
    (13, 15, "restaurant", "Poke bowl"),
    (15, 15, "other", "Pharmacy"),
    (18, 38, "groceries", "Carrefour"),
    (20, 15, "restaurant", "Aperitivo"),
    (23, 25, "leisure", "Museum + drinks"),
    (25, 38, "groceries", "Esselunga"),
    (27, 15, "restaurant", "Trattoria"),
]
# Last month also had a weekend in Rome and a concert: 932 €, over budget
LAST_MONTH_EXTRAS = [(17, 130, "travel", "Weekend in Rome (train + hostel)"), (20, 40, "leisure", "Concert")]
# This month: like usual, but restaurant spending runs hot
THIS_MONTH = [
    (1, 450, "rent", "Rent"),
    (1, 35, "transport", "ATM monthly pass"),
    (4, 36, "groceries", "Esselunga"),
    (9, 25, "leisure", "Cinema"),
    (11, 36, "groceries", "Lidl"),
    (15, 15, "other", "Pharmacy"),
    (18, 36, "groceries", "Carrefour"),
    (25, 36, "groceries", "Esselunga"),
]
HOT_RESTAURANTS = [(0.2, "Sushi with flatmates"), (0.55, "Erasmus dinner"), (0.9, "Burger night")]


def _month(today: date, back: int):
    index = today.year * 12 + today.month - 1 - back
    return index // 12, index % 12 + 1


def seed_demo(conn: sqlite3.Connection, user_id: str, today: Optional[date] = None) -> None:
    """Replace `user_id`'s expenses and budgets with the demo story. Other users are not touched."""
    today = today or date.today()
    with conn:
        conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM budgets WHERE user_id = ?", (user_id,))
    for category, amount in BUDGETS.items():
        set_budget(conn, user_id, category, amount)

    for back, extras in ((2, []), (1, LAST_MONTH_EXTRAS)):
        year, month = _month(today, back)
        last_day = calendar.monthrange(year, month)[1]
        for day, amount, category, merchant in TYPICAL_MONTH + extras:
            add_expense(conn, user_id, amount, category, date(year, month, min(day, last_day)).isoformat(),
                        merchant=merchant, source="synthetic")

    for day, amount, category, merchant in THIS_MONTH:
        if day <= today.day:
            add_expense(conn, user_id, amount, category, today.replace(day=day).isoformat(),
                        merchant=merchant, source="synthetic")
    for fraction, merchant in HOT_RESTAURANTS:
        day = max(1, round(fraction * today.day))
        add_expense(conn, user_id, 28, "restaurant", today.replace(day=day).isoformat(),
                    merchant=merchant, source="synthetic")


RECEIPT_TEXT = """      SUPERMERCATO STELLA
   Via dell'Esempio 12 - Milano
    (demo receipt - not real)

DESCRIZIONE                PREZZO
PASTA INTEGRALE 500G         1,29
LATTE INTERO 1L              1,49
PETTO POLLO 600G             6,90
POMODORI CILIEGINI           2,35
MOZZARELLA 125G              0,99
PANE INTEGRALE               1,80
YOGURT GRECO X2              2,58
DETERSIVO PIATTI             2,30
----------------------------------
TOTALE COMPLESSIVO          19,70
PAGAMENTO ELETTRONICO       19,70

   {date}   18:42
       GRAZIE E ARRIVEDERCI
"""


def make_demo_receipt(today: date, out: Path = DEMO_RECEIPT_PATH) -> bool:
    """Draw a receipt dated today as a JPEG, with macOS built-in tools. Returns False if unavailable."""
    if not (shutil.which("cupsfilter") and shutil.which("sips")):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        text, pdf, png = Path(tmp, "r.txt"), Path(tmp, "r.pdf"), Path(tmp, "r.png")
        text.write_text(RECEIPT_TEXT.format(date=today.strftime("%d-%m-%Y")))
        steps = [
            f"cupsfilter -o cpi=12 -o lpi=7 '{text}' > '{pdf}' 2>/dev/null",
            f"sips -s format png -Z 3000 '{pdf}' --out '{png}' >/dev/null",
            f"sips -c 1400 1250 --cropOffset 30 30 '{png}' --out '{png}' >/dev/null",
            # JPEG has no transparency: a transparent PNG looks black to the vision model
            f"sips -s format jpeg '{png}' --out '{out}' >/dev/null",
        ]
        for step in steps:
            if subprocess.run(step, shell=True).returncode != 0:
                return False
    return out.exists()


def main() -> None:
    DEMO_DB_PATH.parent.mkdir(exist_ok=True)
    # demo.db only ever holds generated data: rebuild it from scratch each time.
    # (Your real data lives in data/budget.db, which this script never opens.)
    DEMO_DB_PATH.unlink(missing_ok=True)
    conn = connect(DEMO_DB_PATH)
    demo_user = create_user(conn, label="demo")
    seed_demo(conn, demo_user)
    conn.close()
    print(f"Demo data ready in {DEMO_DB_PATH}")
    if make_demo_receipt(date.today()):
        print(f"Demo receipt (dated today, total 19.70 €): {DEMO_RECEIPT_PATH}")
    print("\nStart the app on the demo data:")
    print("  BUDGET_DB=data/demo.db python -m uvicorn backend.main:app --host 0.0.0.0")


if __name__ == "__main__":
    sys.exit(main())
