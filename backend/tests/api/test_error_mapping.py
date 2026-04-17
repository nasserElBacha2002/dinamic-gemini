"""Tests for centralized API error mapping and safe fallbacks."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.errors.error_mapping import mapped_http_exception, review_exception_to_http
from src.api.server import app
from src.application.errors import (
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)


def test_mapped_http_exception_job_scope_returns_404() -> None:
    exc = JobDoesNotBelongToAisleError("Job x is not scoped to aisle y")
    http = mapped_http_exception(exc)
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Job x is not scoped to aisle y"


def test_mapped_http_exception_unknown_returns_none() -> None:
    assert mapped_http_exception(RuntimeError("internal")) is None


def test_mapped_http_exception_excludes_value_error() -> None:
    """Broad ValueError stays out of the shared mapper (route-specific status/detail)."""
    assert mapped_http_exception(ValueError("semantic validation")) is None


def test_review_exception_unknown_returns_safe_500_detail() -> None:
    http = review_exception_to_http(RuntimeError("do_not_leak_this"))
    assert http.status_code == 500
    assert "do_not_leak" not in (http.detail or "")
    assert http.detail


def test_review_value_error_still_422() -> None:
    http = review_exception_to_http(ValueError("bad input"))
    assert http.status_code == 422
    assert http.detail == "bad input"


def test_mapped_inventory_not_found() -> None:
    http = mapped_http_exception(InventoryNotFoundError())
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Inventory not found"


def test_server_registers_global_exception_handler() -> None:
    assert Exception in app.exception_handlers


def test_minimal_app_global_handler_hides_internal_message() -> None:
    """Mirrors server wiring: unmapped errors must not echo exception text to clients."""

    mini = FastAPI()

    @mini.exception_handler(Exception)
    async def _unhandled(_request, _exc: Exception):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})

    @mini.get("/boom")
    def boom():
        raise RuntimeError("secret_token_xyz")

    r = TestClient(mini, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert "secret_token_xyz" not in str(body)
    assert body.get("detail") == "An unexpected error occurred."


def test_job_not_found_mapping_detail_preserved() -> None:
    http = mapped_http_exception(JobNotFoundError("Job not found: j-missing"))
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Job not found: j-missing"
