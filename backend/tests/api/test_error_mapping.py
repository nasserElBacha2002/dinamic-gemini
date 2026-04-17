"""Tests for centralized API error mapping and safe fallbacks."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.dependencies import get_get_inventory_use_case
from src.api.errors.error_mapping import mapped_http_exception, reraise_if_mapped, review_exception_to_http
from src.api.errors.structured_api_http import (
    AISLE_NOT_FOUND,
    INVENTORY_NOT_FOUND,
    INTERNAL_SERVER_ERROR,
    POSITION_NOT_FOUND,
    PRODUCT_NOT_FOUND,
    VISUAL_REFERENCE_NOT_FOUND,
    StructuredApiHttpError,
)
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
    assert not isinstance(http, StructuredApiHttpError)


def test_mapped_http_exception_unknown_returns_none() -> None:
    assert mapped_http_exception(RuntimeError("internal")) is None


def test_mapped_http_exception_excludes_value_error() -> None:
    """Broad ValueError stays out of the shared mapper (route-specific status/detail)."""
    assert mapped_http_exception(ValueError("semantic validation")) is None


def test_reraise_if_mapped_raises_when_mapped() -> None:
    with pytest.raises(StructuredApiHttpError) as excinfo:
        reraise_if_mapped(InventoryNotFoundError())
    assert excinfo.value.status_code == 404
    assert excinfo.value.error_code == INVENTORY_NOT_FOUND


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
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 404
    assert http.detail == "Inventory not found"
    assert http.error_code == INVENTORY_NOT_FOUND


@pytest.mark.parametrize(
    "exc,expected_detail,expected_code",
    [
        (AisleNotFoundError(), "Aisle not found or does not belong to this inventory", AISLE_NOT_FOUND),
        (PositionNotFoundError(), "Position not found or does not belong to this aisle", POSITION_NOT_FOUND),
        (ProductNotFoundError(), "Product not found or does not belong to this position", PRODUCT_NOT_FOUND),
        (InventoryVisualReferenceNotFoundError(), "Visual reference not found", VISUAL_REFERENCE_NOT_FOUND),
    ],
)
def test_mapped_stable_not_found_details(exc: Exception, expected_detail: str, expected_code: str) -> None:
    http = mapped_http_exception(exc)
    assert http is not None
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 404
    assert http.detail == expected_detail
    assert http.error_code == expected_code


def test_mapped_stored_artifact_access_passes_curated_detail() -> None:
    exc = StoredArtifactAccessError(404, "Stored artifact file not found.", "local_file_missing")
    http = mapped_http_exception(exc)
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Stored artifact file not found."
    assert not isinstance(http, StructuredApiHttpError)


def test_server_registers_global_exception_handler() -> None:
    assert Exception in app.exception_handlers


def test_minimal_app_global_handler_hides_internal_message() -> None:
    """Mirrors server wiring: unmapped errors must not echo exception text to clients."""

    mini = FastAPI()

    @mini.exception_handler(Exception)
    async def _unhandled(_request, _exc: Exception):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={
                "code": INTERNAL_SERVER_ERROR,
                "detail": "An unexpected error occurred.",
            },
        )

    @mini.get("/boom")
    def boom():
        raise RuntimeError("secret_token_xyz")

    r = TestClient(mini, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert "secret_token_xyz" not in str(body)
    assert body.get("detail") == "An unexpected error occurred."
    assert body.get("code") == INTERNAL_SERVER_ERROR


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
        body = r.json()
        assert body.get("detail") == "An unexpected error occurred."
        assert body.get("code") == INTERNAL_SERVER_ERROR
    finally:
        app.dependency_overrides.pop(get_get_inventory_use_case, None)


def test_get_inventory_not_found_returns_structured_json() -> None:
    """Integration: stable not-found through app exception handler."""

    class _MissingInventory:
        def execute(self, _inventory_id: str):
            raise InventoryNotFoundError()

    app.dependency_overrides[get_get_inventory_use_case] = lambda: _MissingInventory()
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/api/v3/inventories/any-id")
        assert r.status_code == 404
        assert r.json() == {"code": INVENTORY_NOT_FOUND, "detail": "Inventory not found"}
    finally:
        app.dependency_overrides.pop(get_get_inventory_use_case, None)


def test_app_registers_structured_api_http_handler() -> None:
    assert StructuredApiHttpError in app.exception_handlers


def test_default_http_exception_is_detail_only_no_code_key() -> None:
    """Legacy shape: Starlette/FastAPI default handler for plain ``HTTPException`` (Category B style)."""
    mini = FastAPI()

    @mini.get("/legacy")
    def _legacy():
        raise HTTPException(status_code=404, detail="Job not found: j-legacy")

    r = TestClient(mini, raise_server_exceptions=False).get("/legacy")
    assert r.status_code == 404
    assert r.json() == {"detail": "Job not found: j-legacy"}
    assert "code" not in r.json()


def test_structured_handler_emits_code_and_detail() -> None:
    """Structured shape: matches production ``structured_api_http_error_handler`` contract."""
    from fastapi.responses import JSONResponse

    mini = FastAPI()

    @mini.exception_handler(StructuredApiHttpError)
    async def _structured(_request, exc: StructuredApiHttpError):
        return JSONResponse(status_code=exc.status_code, content={"code": exc.error_code, "detail": exc.detail})

    @mini.get("/s")
    def _structured_route():
        raise StructuredApiHttpError(404, error_code=INVENTORY_NOT_FOUND, detail="Inventory not found")

    r = TestClient(mini, raise_server_exceptions=False).get("/s")
    assert r.status_code == 404
    assert r.json() == {"code": INVENTORY_NOT_FOUND, "detail": "Inventory not found"}


def test_backward_compat_clients_read_detail_only() -> None:
    """Clients that only access ``detail`` keep working when ``code`` is additive."""
    body = {"code": INVENTORY_NOT_FOUND, "detail": "Inventory not found"}
    assert body["detail"] == "Inventory not found"


def test_reraise_if_mapped_polymorphic_raises_http_exception_subclass() -> None:
    """``reraise_if_mapped`` may raise ``StructuredApiHttpError``; both are ``HTTPException`` subclasses."""
    with pytest.raises(HTTPException):
        reraise_if_mapped(InventoryNotFoundError())
    with pytest.raises(StructuredApiHttpError):
        reraise_if_mapped(InventoryNotFoundError())
    m = mapped_http_exception(JobNotFoundError("Job not found: j1"))
    assert m is not None
    with pytest.raises(HTTPException):
        raise m
    assert not isinstance(m, StructuredApiHttpError)
