"""Stage 7 — FastAPI server and API key middleware.

Run: uvicorn src.api.server:app --reload
"""

import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.api.api_key_policy import (
    api_keys_match,
    parse_api_key_path_prefixes,
    path_requires_api_key,
)
from src.api.constants.error_wire import (
    HTTP_DETAIL_API_KEY_INVALID_OR_MISSING,
    HTTP_DETAIL_UNEXPECTED_ERROR,
)
from src.api.errors.structured_api_http import INTERNAL_SERVER_ERROR, StructuredApiHttpError
from src.api.routes.v3 import router as v3_router
from src.api.routes.v3.admin_ai_config import router as v3_admin_ai_config_router
from src.api.routes.v3.admin_finalization_recovery import (
    router as v3_admin_finalization_recovery_router,
)
from src.api.routes.v3.admin_storage import router as v3_admin_storage_router
from src.api.routes.v3.analytics_api import router as v3_analytics_router
from src.api.routes.v3.clients import router as v3_clients_router
from src.api.routes.v3.config import router as v3_config_router
from src.api.routes.v3.observability import router as v3_observability_router
from src.api.routes.v3.review_queue import router as v3_review_queue_router
from src.api.schema_guard import schema_guard_state
from src.api.schemas.responses import HealthResponse
from src.api.security_headers import (
    SAFE_CORS_ALLOW_HEADERS,
    SAFE_CORS_ALLOW_METHODS,
    SecurityHeadersMiddleware,
    normalize_cors_allow_origins,
    resolve_hsts_enabled,
)
from src.auth.errors import AuthHttpError
from src.auth.routes import router as auth_router
from src.config import load_settings, resolve_sqlserver_connection_config
from src.database.migrations import ensure_schema_compatibility, get_required_schema_version
from src.database.sqlserver import SqlServerClient
from src.jobs.worker import worker_loop
from src.observability.metrics.registry import get_metrics_registry
from src.observability.metrics_auth import metrics_access_allowed
from src.observability.middleware import ObservabilityMiddleware
from src.observability.runtime_wiring import (
    configure_metrics_registry_limits,
    refresh_operational_gauges_for_scrape,
    stop_recovery_scheduler,
    wire_operational_metrics_collector,
    wire_recovery_scheduler,
)
from src.runtime.container.runtime_environment import resolve_runtime_environment

logger = logging.getLogger(__name__)

app = FastAPI(title="Inventory Engine API", version="2.0.0")

# CORS for v3 frontend (e.g. Vite dev server on localhost:5173)
settings = load_settings()
_rt = resolve_runtime_environment()
cors_allow_origins = normalize_cors_allow_origins(
    settings.cors_allow_origins,
    allow_credentials=True,
    env=_rt,
)

artifact_provider = (settings.artifact_storage_provider or "local").strip().lower()
if artifact_provider == "s3":
    logger.info(
        "Artifact storage config: provider=s3 bucket=%s region=%s prefix=%s signed_url_ttl_sec=%s legacy_local_read=%s",
        settings.artifact_s3_bucket,
        settings.artifact_s3_region or "<default>",
        settings.artifact_s3_prefix,
        settings.artifact_s3_signed_url_ttl_sec,
        settings.artifact_storage_legacy_local_read_enabled,
    )
elif artifact_provider == "gcs":
    logger.info(
        "Artifact storage config: provider=gcs bucket=%s project=%s prefix=%s signed_url_ttl_sec=%s legacy_local_read=%s",
        settings.artifact_gcs_bucket,
        settings.artifact_gcs_project_id or "<default>",
        settings.artifact_gcs_prefix,
        settings.artifact_gcs_signed_url_ttl_sec,
        settings.artifact_storage_legacy_local_read_enabled,
    )
else:
    logger.info(
        "Artifact storage config: provider=local output_dir=%s legacy_local_read=%s",
        settings.output_dir,
        settings.artifact_storage_legacy_local_read_enabled,
    )

# Observability outermost among app middleware (Starlette: last added = first executed).
app.add_middleware(
    ObservabilityMiddleware,
    metrics_enabled=bool(getattr(settings, "metrics_enabled", True)),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=True,
    allow_methods=SAFE_CORS_ALLOW_METHODS,
    allow_headers=SAFE_CORS_ALLOW_HEADERS,
    # Location: asset 307 → signed URL (fetch redirect: manual).
    # Content-Disposition: blob downloads via fetch (apiDownloadBlob) need the filename.
    expose_headers=["Location", "Content-Disposition"],
)

# HSTS: hosted only, ENABLE_HSTS=true, and FORWARDED_TRUSTED_HOSTS set (TLS at edge).
_hsts_on, _hsts_max_age = resolve_hsts_enabled(
    env=_rt,
    forwarded_trusted_hosts=settings.forwarded_trusted_hosts,
)
app.add_middleware(
    SecurityHeadersMiddleware,
    enable_hsts=_hsts_on,
    hsts_max_age_sec=_hsts_max_age,
)

# Behind HTTPS-terminating ALB, redirects must use https; middleware trusts X-Forwarded-Proto from listed hosts.
_forwarded = (settings.forwarded_trusted_hosts or "").strip()
if _forwarded:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=_forwarded)

# Model A: JWT for public clients. API_KEY is optional and only enforced on configured
# path prefixes (API_KEY_REQUIRED_PATH_PREFIXES). Empty prefixes = no HTTP API-key gate.
_api_key_prefixes = parse_api_key_path_prefixes(
    getattr(settings, "api_key_required_path_prefixes", None)
    or os.getenv("API_KEY_REQUIRED_PATH_PREFIXES", "")
)
if (settings.api_key or "").strip() and _api_key_prefixes:
    logger.info(
        "API key enforcement enabled for path prefixes=%s (Model A — public JWT clients unaffected)",
        _api_key_prefixes,
    )
elif (settings.api_key or "").strip():
    logger.info(
        "API_KEY is set but API_KEY_REQUIRED_PATH_PREFIXES is empty — "
        "no HTTP routes require X-API-Key (Model A default; JWT for public clients)."
    )

# Include routers (v3 only for inventory operations; legacy v1 jobs/entities removed in Stage 3).
app.include_router(v3_router)
app.include_router(v3_clients_router)
app.include_router(v3_analytics_router)
app.include_router(v3_review_queue_router)
app.include_router(v3_observability_router)
app.include_router(v3_config_router)
app.include_router(auth_router)
app.include_router(v3_admin_ai_config_router)
app.include_router(v3_admin_storage_router)
app.include_router(v3_admin_finalization_recovery_router)


@app.exception_handler(AuthHttpError)
async def auth_http_error_handler(_: Request, exc: AuthHttpError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_response_body())


@app.exception_handler(StructuredApiHttpError)
async def structured_api_http_error_handler(
    request: Request, exc: StructuredApiHttpError
) -> JSONResponse:
    """Emit flat JSON ``code`` + ``detail`` for Category A, selected Category B, and direct raises.

    Logs at INFO with stable ``error_code`` for operations dashboards (no PII in ``detail`` here).
    """
    logger.info(
        "v3_structured_api_error status=%s code=%s path=%s",
        exc.status_code,
        exc.error_code,
        request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.error_code, "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safe 500 for unexpected failures; business rules should map to HTTPException earlier.

    **Error contract:** additive ``code`` + generic ``detail`` — never ``str(exc)``, stack
    traces, or other internal diagnostics (see ``src.api.errors.error_mapping``). More
    specific handlers win via Starlette's MRO lookup before this handler.
    """
    logger.exception(
        "Unhandled exception method=%s path=%s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": INTERNAL_SERVER_ERROR,
            "detail": HTTP_DETAIL_UNEXPECTED_ERROR,
        },
    )


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Enforce X-API-Key only on configured internal path prefixes (Model A).

    Public browser/mobile clients use JWT. ``/health`` and ``/ready`` never require a key.
    """
    settings = load_settings()
    expected = (settings.api_key or "").strip()
    prefixes = parse_api_key_path_prefixes(
        getattr(settings, "api_key_required_path_prefixes", None)
        or os.getenv("API_KEY_REQUIRED_PATH_PREFIXES", "")
    )
    if not expected or not path_requires_api_key(request.url.path, prefixes):
        return await call_next(request)
    key = (request.headers.get("X-API-Key") or "").strip()
    if not api_keys_match(key, expected):
        return JSONResponse(
            status_code=403, content={"detail": HTTP_DETAIL_API_KEY_INVALID_OR_MISSING}
        )
    return await call_next(request)


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus text exposition — internal only (not a public internet surface)."""
    settings = load_settings()
    if not bool(getattr(settings, "metrics_enabled", True)):
        return Response(status_code=404, content="metrics disabled")
    if not metrics_access_allowed(
        request,
        api_key=settings.api_key or "",
        auth_mode=getattr(settings, "metrics_internal_auth", "api_key") or "api_key",
        env=resolve_runtime_environment(),
    ):
        return JSONResponse(status_code=403, content={"detail": "metrics access denied"})
    refresh_operational_gauges_for_scrape()
    body = get_metrics_registry().render_prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness with schema compatibility metadata and repository backend observability.

    ``ok`` is always ``True`` here — this endpoint only asserts the process is alive and
    serving requests. Repository backend problems are surfaced (not hidden) via the
    ``repository_backend_resolved`` / ``repository_backend_healthy`` /
    ``repository_backend_reason_code`` fields; use ``/ready`` for the actual readiness gate.
    Uses the public :meth:`AppContainer.get_repository_backend_status` API — never touches the
    internal resolution cache directly, and never leaks connection strings or probe exceptions.
    """
    _sha = (os.environ.get("GIT_SHA") or "").strip() or None
    from src.runtime.app_container import get_app_container

    backend_status = get_app_container().get_repository_backend_status()
    return HealthResponse(
        ok=True,
        deploy_git_sha=_sha,
        schema_guard_checked=schema_guard_state.checked,
        schema_compatible=schema_guard_state.compatible,
        schema_service=schema_guard_state.service,
        required_schema_version=schema_guard_state.required_version,
        current_schema_version=schema_guard_state.current_version,
        schema_reason=schema_guard_state.reason,
        repository_backend=backend_status.mode,
        repository_backend_environment=backend_status.environment,
        fallback_activated=backend_status.fallback_activated,
        repository_backend_resolved=backend_status.resolved,
        repository_backend_healthy=backend_status.healthy,
        repository_backend_reason_code=backend_status.reason_code,
    )


@app.get("/ready")
async def ready() -> Response:
    """Readiness: fail when schema is incompatible or the repository backend is unusable.

    503 cases (repository backend): SQL required but unavailable, MEMORY_ONLY forbidden for
    this environment, MEMORY_FALLBACK forbidden for this environment — all surfaced as
    ``resolved=False`` / ``healthy=False`` by :meth:`AppContainer.get_repository_backend_status`,
    which never raises. No bare ``except Exception: return 200`` here.
    """
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
    from src.runtime.app_container import get_app_container

    backend_status = get_app_container().get_repository_backend_status()
    if not backend_status.resolved or not backend_status.healthy:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "reason": "REPOSITORY_BACKEND_UNAVAILABLE",
                "repository_backend_environment": backend_status.environment,
                "repository_backend_reason_code": backend_status.reason_code,
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
    from src.application.services.position_traceability import (
        set_traceability_stored_artifact_reader,
    )
    from src.runtime.v3_deps import get_stored_artifact_reader

    set_traceability_stored_artifact_reader(get_stored_artifact_reader())

    _git_sha = (os.environ.get("GIT_SHA") or "").strip()
    if _git_sha:
        logger.info("API startup deploy_git_sha=%s", _git_sha)
    settings = load_settings()
    sql_res = resolve_sqlserver_connection_config()
    if sql_res.connection_string.strip() and sql_res.sql_server_connect_target:
        logger.info(
            "SQL Server ODBC SERVER (non-secret): %s config_mode=%s",
            sql_res.sql_server_connect_target,
            sql_res.mode,
        )
    if (
        settings.db_schema_guard_enabled
        and settings.sqlserver_enabled
        and sql_res.connection_string.strip()
    ):
        required_version = settings.db_schema_required_version or get_required_schema_version()
        if required_version:
            client = SqlServerClient(sql_res.connection_string.strip())
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
            logger.warning(
                "Schema guard enabled but no migration files found; skipping required version check."
            )
    elif (
        settings.db_schema_guard_enabled
        and settings.sqlserver_enabled
        and sql_res.mode == "incomplete_split"
    ):
        logger.error(
            "Schema guard skipped: SQL Server config incomplete (mode=%s missing=%s). %s",
            sql_res.mode,
            list(sql_res.missing_env_vars),
            sql_res.hint or "",
        )
    elif (
        settings.db_schema_guard_enabled and settings.sqlserver_enabled and sql_res.mode == "unset"
    ):
        logger.warning(
            "Schema guard enabled but SQL Server connection is not configured (mode=unset); "
            "skipping startup compatibility check."
        )
    configure_metrics_registry_limits(settings)
    from src.runtime.app_container import get_app_container

    container = get_app_container()
    wire_operational_metrics_collector(container, settings)
    wire_recovery_scheduler(container, settings)

    if not settings.embedded_worker_enabled:
        logger.info(
            "Embedded worker disabled (EMBEDDED_WORKER_ENABLED=false); "
            "run dedicated worker process (e.g. `python -m src.jobs.run_worker`)."
        )
        return
    t = threading.Thread(target=_worker_thread_fn, daemon=True)
    t.start()
    logger.info("Worker thread started")


@app.on_event("shutdown")
def stop_observability_runtime() -> None:
    stop_recovery_scheduler()
