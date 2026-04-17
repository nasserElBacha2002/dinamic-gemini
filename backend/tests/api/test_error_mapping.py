"""Tests for centralized API error mapping and safe fallbacks."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.dependencies import get_get_inventory_use_case
from src.api.errors.error_mapping import mapped_http_exception, reraise_if_mapped, review_exception_to_http
from src.api.server import app
from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    InventoryVisualReferenceNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    PositionNotFoundError,
    ProductNotFoundError,
)
from src.api.services.v3_stored_artifact_access import StoredArtifactAccessError


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


def test_reraise_if_mapped_raises_when_mapped() -> None:
    with pytest.raises(HTTPException) as excinfo:
        reraise_if_mapped(InventoryNotFoundError())
    assert excinfo.value.status_code == 404


def test_reraise_if_mapped_no_op_for_value_error() -> None:
    reraise_if_mapped(ValueError("route layer should handle"))


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


@pytest.mark.parametrize(
    "exc,expected_detail",
    [
        (AisleNotFoundError(), "Aisle not found or does not belong to this inventory"),
        (PositionNotFoundError(), "Position not found or does not belong to this aisle"),
        (ProductNotFoundError(), "Product not found or does not belong to this position"),
        (InventoryVisualReferenceNotFoundError(), "Visual reference not found"),
    ],
)
def test_mapped_stable_not_found_details(exc: Exception, expected_detail: str) -> None:
    http = mapped_http_exception(exc)
    assert http is not None
    assert http.status_code == 404
    assert http.detail == expected_detail


def test_mapped_stored_artifact_access_passes_curated_detail() -> None:
    exc = StoredArtifactAccessError(404, "Stored artifact file not found.", "local_file_missing")
    http = mapped_http_exception(exc)
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Stored artifact file not found."


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


def test_real_app_global_handler_does_not_echo_internal_error() -> None:
    """App-level 500 must match server contract (no raw exception text in JSON)."""

    class _BadInventoryUseCase:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("INTERNAL_LEAK_TOKEN_123")

    app.dependency_overrides[get_get_inventory_use_case] = lambda: _BadInventoryUseCase()
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/api/v3/inventories/any-id")
        assert r.status_code == 500
        assert "INTERNAL_LEAK" not in r.text
        assert r.json().get("detail") == "An unexpected error occurred."
    finally:
        app.dependency_overrides.pop(get_get_inventory_use_case, None)
