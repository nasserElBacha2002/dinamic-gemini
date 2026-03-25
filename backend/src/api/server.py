"""Stage 7 — FastAPI server and API key middleware.

Run: uvicorn src.api.server:app --reload
"""

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.api.routes.v3 import router as v3_router
from src.api.schema_guard import schema_guard_state
from src.api.schemas.responses import HealthResponse
from src.auth.errors import AuthHttpError
from src.auth.routes import router as auth_router
from src.config import load_settings, resolve_sqlserver_effective_connection_string
from src.database.migrations import ensure_schema_compatibility, get_required_schema_version
from src.database.sqlserver import SqlServerClient
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
    """Liveness with schema compatibility metadata."""
    return HealthResponse(
        ok=True,
        schema_guard_checked=schema_guard_state.checked,
        schema_compatible=schema_guard_state.compatible,
        schema_service=schema_guard_state.service,
        required_schema_version=schema_guard_state.required_version,
        current_schema_version=schema_guard_state.current_version,
        schema_reason=schema_guard_state.reason,
    )


@app.get("/ready")
async def ready() -> Response:
    """Readiness: fail when schema guard is incompatible."""
    if schema_guard_state.checked and not schema_guard_state.compatible:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "reason": "SCHEMA_INCOMPATIBLE",
                "service": schema_guard_state.service,
                "required_schema_version": schema_guard_state.required_version,
                "current_schema_version": schema_guard_state.current_version,
                "detail": schema_guard_state.reason,
            },
        )
    return JSONResponse(status_code=200, content={"ok": True})


def _worker_thread_fn() -> None:
    base = Path(load_settings().output_dir)
    try:
        worker_loop(base)
    except Exception as e:
        logger.exception("Worker error: %s", e)


@app.on_event("startup")
def start_worker() -> None:
    """Run schema compatibility guard and start optional worker."""
    settings = load_settings()
    conn_str, sql_missing = resolve_sqlserver_effective_connection_string()
    if settings.db_schema_guard_enabled and settings.sqlserver_enabled and conn_str.strip():
        required_version = settings.db_schema_required_version or get_required_schema_version()
        if required_version:
            client = SqlServerClient(conn_str.strip())
            status = ensure_schema_compatibility(
                client=client,
                service=settings.db_schema_service_name,
                required_version=required_version,
            )
            schema_guard_state.checked = True
            schema_guard_state.compatible = status.compatible
            schema_guard_state.required_version = status.required_version
            schema_guard_state.current_version = status.current_version
            schema_guard_state.service = status.service
            schema_guard_state.reason = status.reason
            if status.compatible:
                logger.info(
                    "Schema compatibility OK service=%s required=%s current=%s",
                    status.service,
                    status.required_version,
                    status.current_version,
                )
            else:
                logger.error(
                    "Schema compatibility FAILED service=%s required=%s current=%s reason=%s",
                    status.service,
                    status.required_version,
                    status.current_version,
                    status.reason,
                )
                if settings.db_schema_guard_block_startup:
                    raise RuntimeError(
                        "Schema compatibility check failed. "
                        f"service={status.service} required={status.required_version} "
                        f"current={status.current_version} reason={status.reason}"
                    )
        else:
            logger.warning("Schema guard enabled but no migration files found; skipping required version check.")
    elif settings.db_schema_guard_enabled and settings.sqlserver_enabled and sql_missing:
        logger.error(
            "Schema guard skipped: incomplete SQL Server env (missing: %s). "
            "Set SQLSERVER_CONNECTION_STRING or all split vars plus ODBC driver; see Settings docs.",
            ", ".join(sql_missing),
        )
    elif settings.db_schema_guard_enabled and settings.sqlserver_enabled and not conn_str.strip():
        logger.warning(
            "Schema guard enabled but no SQL Server connection is configured; "
            "skipping startup compatibility check."
        )
    if not settings.embedded_worker_enabled:
        logger.info(
            "Embedded worker disabled (EMBEDDED_WORKER_ENABLED=false); "
            "run dedicated worker process (e.g. `python -m src.jobs.run_worker`)."
        )
        return
    t = threading.Thread(target=_worker_thread_fn, daemon=True)
    t.start()
    logger.info("Worker thread started")
