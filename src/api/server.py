"""Stage 7 — FastAPI server and API key middleware.

Run: uvicorn src.api.server:app --reload
"""

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes.entities import router as entities_router
from src.api.routes.inventories_v3 import router as inventories_v3_router
from src.api.routes.jobs import router as jobs_router
from src.api.schemas.responses import HealthResponse
from src.config import load_settings
from src.jobs.queue import dequeue
from src.jobs.worker import run_job

logger = logging.getLogger(__name__)

app = FastAPI(title="Inventory Engine API", version="2.0.0")

# CORS for v3 frontend (e.g. Vite dev server on localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(jobs_router)
app.include_router(entities_router)
app.include_router(inventories_v3_router)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Require X-API-Key header if settings.api_key is set."""
    if request.url.path == "/health":
        return await call_next(request)
    settings = load_settings()
    if not settings.api_key:
        return await call_next(request)
    key = request.headers.get("X-API-Key")
    if key != settings.api_key:
        return JSONResponse(status_code=403, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Healthcheck."""
    return HealthResponse(ok=True)


def _worker_thread_fn() -> None:
    base = Path(load_settings().output_dir)
    while True:
        try:
            job_id = dequeue(timeout=1.0)
            if job_id:
                run_job(base, job_id)
        except Exception as e:
            logger.exception("Worker error: %s", e)


@app.on_event("startup")
def start_worker() -> None:
    """Start background worker thread."""
    t = threading.Thread(target=_worker_thread_fn, daemon=True)
    t.start()
    logger.info("Worker thread started")
