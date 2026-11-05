"""Application entry point: serves the frontend and the health endpoint.

This is the single FastAPI process that will eventually wire together
account connections, transactions, budgeting, advice, daily checks, and
evaluation. For now it only starts the server, serves the static
frontend at "/", and exposes "/health".
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="Personal Financial Agent")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Serve frontend assets (styles.css, app.js, etc.) under /static.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health")
def health():
    """Simple liveness check used to confirm the server is running."""
    return {"status": "ok"}


@app.get("/")
def read_index():
    """Serve the frontend page."""
    return FileResponse(FRONTEND_DIR / "index.html")
