"""Stage 7 — FastAPI server and API key middleware.

Run: uvicorn src.api.server:app --reload
"""

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes.v3 import router as v3_router
from src.api.schemas.responses import HealthResponse
from src.auth.errors import AuthHttpError
from src.auth.routes import router as auth_router
from src.config import load_settings
from src.jobs.worker import worker_loop

logger = logging.getLogger(__name__)

app = FastAPI(title="Inventory Engine API", version="2.0.0")

# CORS for v3 frontend (e.g. Vite dev server on localhost:5173)
settings = load_settings()
raw_cors_allow_origins = (settings.cors_allow_origins or "").strip()
cors_allow_origins = (
    [o.strip() for o in raw_cors_allow_origins.split(",") if o.strip()]
    if raw_cors_allow_origins
    else []
)
if not cors_allow_origins:
    cors_allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (v3 only for inventory operations; legacy v1 jobs/entities removed in Stage 3).
app.include_router(v3_router)
app.include_router(auth_router)


@app.exception_handler(AuthHttpError)
async def auth_http_error_handler(_: Request, exc: AuthHttpError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_response_body())


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
    try:
        worker_loop(base)
    except Exception as e:
        logger.exception("Worker error: %s", e)


@app.on_event("startup")
def start_worker() -> None:
    """Start background worker thread when embedded worker mode is enabled."""
    if not load_settings().embedded_worker_enabled:
        logger.info(
            "Embedded worker disabled (EMBEDDED_WORKER_ENABLED=false); "
            "run dedicated worker process (e.g. `python -m src.jobs.run_worker`)."
        )
        return
    t = threading.Thread(target=_worker_thread_fn, daemon=True)
    t.start()
    logger.info("Worker thread started")
