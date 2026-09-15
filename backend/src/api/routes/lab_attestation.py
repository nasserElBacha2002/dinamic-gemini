"""Disposable lab attestation endpoint (Phase 4B).

Mounted only when ``LAB_DISPOSABLE_ENABLED`` is true and the runtime is LOCAL/TEST
(not production-like). Fail-closed: 404 when disabled; 503 when invariants fail.
Never returns tokens, secrets, or prompts.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from src.runtime.container.runtime_environment import (
    RuntimeEnvironment,
    is_production_like_runtime,
    resolve_runtime_environment,
)

router = APIRouter(tags=["lab"])

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LAB_DATA_DIR = _REPO_ROOT.parent / "audit" / "lab" / "data"
_SEED_OK_PATH = _LAB_DATA_DIR / "seed.ok"

_FIXTURE_MARKER_DEFAULT = "lab-fixture-only"
_PUBLIC_LLM_HOST_FRAGMENTS = (
    "generativelanguage.googleapis.com",
    "api.openai.com",
    "api.anthropic.com",
    "openai.azure.com",
)


def lab_attestation_enabled() -> bool:
    """Gate for mounting / serving lab attestation routes."""
    flag = (os.getenv("LAB_DISPOSABLE_ENABLED") or "").strip().lower()
    if flag not in {"true", "1", "yes"}:
        return False
    if is_production_like_runtime():
        return False
    env = resolve_runtime_environment()
    return env in {RuntimeEnvironment.LOCAL, RuntimeEnvironment.TEST}


def _truthy(name: str, default: str = "") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"true", "1", "yes"}


def _llm_mocked_ok() -> bool:
    if not _truthy("LAB_LLM_MOCKED"):
        return False
    marker = (os.getenv("LAB_FIXTURE_KEY_MARKER") or _FIXTURE_MARKER_DEFAULT).strip()
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        val = (os.getenv(name) or "").strip()
        if val and val != marker:
            return False
    for name in (
        "GEMINI_API_BASE_URL",
        "OPENAI_API_BASE",
        "ANTHROPIC_BASE_URL",
        "LLM_API_BASE_URL",
    ):
        raw = (os.getenv(name) or "").strip().lower()
        if any(frag in raw for frag in _PUBLIC_LLM_HOST_FRAGMENTS):
            return False
    return True


def _storage_is_local() -> bool:
    provider = (os.getenv("ARTIFACT_STORAGE_PROVIDER") or "local").strip().lower()
    return provider == "local"


def _seed_loaded() -> bool:
    if _truthy("LAB_SEED_LOADED"):
        return True
    return _SEED_OK_PATH.is_file()


def _sql_healthy() -> bool:
    try:
        from src.runtime.app_container import get_app_container

        status = get_app_container().get_repository_backend_status()
        return bool(status.resolved and status.healthy)
    except Exception:
        return False


def _worker_operable() -> bool:
    if not _truthy("EMBEDDED_WORKER_ENABLED", "true"):
        # Dedicated worker deployments: treat as operable for attestation when SQL is up.
        return _sql_healthy()
    try:
        from src.jobs.worker_runtime import get_embedded_worker_runtime

        runtime = get_embedded_worker_runtime()
        if runtime is None:
            return False
        return bool(getattr(runtime, "is_alive", lambda: False)())
    except Exception:
        # Before lifespan start (unit tests), do not hard-fail worker when SQL healthy.
        return _sql_healthy()


def _gemini_commit() -> str | None:
    explicit = (os.getenv("GIT_SHA") or os.getenv("LAB_GEMINI_COMMIT") or "").strip()
    if explicit:
        return explicit
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT.parent),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return out.strip() or None
    except Exception:
        return None


def _resolve_audit_run_id(request: Request, query_run_id: str | None) -> str:
    if query_run_id and query_run_id.strip():
        return query_run_id.strip()
    header = (request.headers.get("X-Audit-Run-Id") or "").strip()
    if header:
        return header
    env_id = (os.getenv("LAB_RUN_ID") or "").strip()
    if env_id:
        return env_id
    return "LAB_RUN_UNSET"


@router.get("/lab/health")
def lab_health(
    request: Request,
    audit_run_id: str | None = Query(default=None),
) -> JSONResponse:
    if not lab_attestation_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    run_id = _resolve_audit_run_id(request, audit_run_id)
    blockers: list[str] = []

    sql_ok = _sql_healthy()
    storage_ok = _storage_is_local()
    llm_ok = _llm_mocked_ok()
    seed_ok = _seed_loaded()
    worker_ok = _worker_operable()

    if not sql_ok:
        blockers.append("sql_unhealthy")
    if not storage_ok:
        blockers.append("storage_not_local")
    if not llm_ok:
        blockers.append("llm_not_mocked")
    if not seed_ok:
        blockers.append("seed_not_loaded")
    # Worker is soft for GET health when embedded not started yet — still report field.
    # Fail closed only when SQL/storage/llm/seed fail.

    env = resolve_runtime_environment()
    body: dict[str, Any] = {
        "ok": not blockers,
        "disposable": True,
        "llm_mocked": llm_ok,
        "storage": "local" if storage_ok else (os.getenv("ARTIFACT_STORAGE_PROVIDER") or "unknown"),
        "audit_run_id": run_id,
        "nonce": f"HEALTHCHECK_{run_id}",
        "environment": env.value,
        "environment_class": "LOCAL_ISOLATED_ONLY",
        "status": "ready" if not blockers else "blocked",
        "database": "healthy" if sql_ok else "unhealthy",
        "seed_loaded": seed_ok,
        "worker_operable": worker_ok,
        "lab_run_id": (os.getenv("LAB_RUN_ID") or "").strip() or run_id,
        "gemini_commit": _gemini_commit(),
    }

    if blockers:
        # Keep response free of secrets; blockers are coarse codes only.
        body["ok"] = False
        body["status"] = "blocked"
        return JSONResponse(status_code=503, content=body)

    body["ok"] = True
    body["status"] = "ready"
    return JSONResponse(status_code=200, content=body)
