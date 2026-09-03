"""FastAPI application entrypoint.

Serves the kiosk page and the session WebSocket. Run with:

    uvicorn chatface.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from chatface.api.ws import router as ws_router

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ChatFace", version="0.1.0")
app.include_router(ws_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    """The kiosk page. Point Chromium at this in kiosk mode."""
    return FileResponse(STATIC_DIR / "index.html")
