"""Tests for centralized API error mapping and safe fallbacks."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.constants.error_wire import (
    HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING,
    HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
    HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
    HTTP_DETAIL_SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
)
from src.api.dependencies import (
    get_compare_aisle_runs_use_case,
    get_get_aisle_processing_status_use_case,
    get_get_inventory_use_case,
    get_get_position_detail_use_case,
    get_list_inventory_visual_references_use_case,
    get_promote_aisle_operational_job_use_case,
    get_resolve_aisle_job_for_inventory_read_use_case,
    get_start_aisle_processing_use_case,
)
from src.api.errors.error_mapping import (
    mapped_http_exception,
    reraise_if_mapped,
    review_exception_to_http,
)
from src.api.errors.structured_api_http import (
    ACTIVE_JOB_EXISTS,
    AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING,
    AISLE_NOT_FOUND,
    AISLE_NOT_FOUND_FOR_ASSIGNMENT,
    ANALYTICS_SCOPE_VALIDATION_FAILED,
    BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
    CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
    CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
    CAPTURE_SESSION_GROUP_INTEGRITY_VIOLATION,
    CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
    CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
    CAPTURE_SESSION_GROUP_NOT_FOUND,
    CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
    CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
    CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
    CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
    EMPTY_UPLOAD,
    INTERNAL_SERVER_ERROR,
    INVENTORY_NOT_FOUND,
    JOB_NOT_FOUND,
    JOB_NOT_IN_AISLE_SCOPE,
    JOB_PROMOTION_NOT_ALLOWED,
    POSITION_NOT_FOUND,
    PRODUCT_NOT_FOUND,
    SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
    UNSUPPORTED_ASSET_TYPE,
    VISUAL_REFERENCE_NOT_FOUND,
    ZERO_BYTE_FILE,
    StructuredApiHttpError,
)
from src.api.server import app
from src.api.services.v3_stored_artifact_access import StoredArtifactAccessError
from src.application.errors import (
    ActiveJobExistsError,
    AisleNotFoundError,
    AisleNotFoundForAssignmentError,
    AnalyticsScopeValidationError,
    BenchmarkCompareJobsMustDifferError,
    CaptureSessionGroupAlreadyAssignedError,
    CaptureSessionGroupAssignmentNotAllowedError,
    CaptureSessionGroupingNotAllowedError,
    CaptureSessionGroupIntegrityError,
    CaptureSessionGroupNotAssignedForMaterializationError,
    CaptureSessionGroupNotAssignedForPreviewError,
    CaptureSessionGroupNotFoundError,
    CaptureSessionGroupNotMaterializedForPreviewError,
    CaptureSessionInvalidClockOffsetError,
    CaptureSessionNoItemsForGroupingError,
    CaptureSessionPreviewNotAllowedError,
    EmptyUploadError,
    InventoryNotFoundError,
    InventoryVisualReferenceNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    JobPromotionNotAllowedError,
    MergeJobScopeAmbiguousError,
    NoSourceAssetsForAisleProcessingError,
    PositionNotFoundError,
    ProductNotFoundError,
    SupplierReferenceImageNotFoundError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)


def test_mapped_http_exception_job_scope_returns_404() -> None:
    exc = JobDoesNotBelongToAisleError("Job x does not belong to aisle y")
    http = mapped_http_exception(exc)
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Job x is not scoped to aisle y"
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == JOB_NOT_IN_AISLE_SCOPE


def test_mapped_job_does_not_belong_preserves_not_scoped_phrase() -> None:
    exc = JobDoesNotBelongToAisleError("Job j1 is not scoped to aisle aisle-1")
    http = mapped_http_exception(exc)
    assert http is not None
    assert http.detail == "Job j1 is not scoped to aisle aisle-1"


def test_mapped_job_does_not_belong_non_canonical_message_maps_to_stable_generic_detail() -> None:
    """Unparseable ``JobDoesNotBelongToAisleError`` → stable generic (no raw ``str(exc)``)."""
    http = mapped_http_exception(JobDoesNotBelongToAisleError("legacy ad-hoc scope message"))
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == JOB_NOT_IN_AISLE_SCOPE
    assert http.detail == "Job is not scoped to this aisle"


def test_integration_benchmark_compare_job_not_in_aisle_scope_returns_structured_json() -> None:
    """Route + handler: ``JobDoesNotBelongToAisleError`` via ``reraise_if_mapped`` (known pattern)."""

    class _CompareScope:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise JobDoesNotBelongToAisleError("Job j-bad is not scoped to aisle aisle-1")

    app.dependency_overrides[get_compare_aisle_runs_use_case] = lambda: _CompareScope()
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/benchmark/compare",
            params={"job_a_id": "ja", "job_b_id": "jb"},
        )
        assert r.status_code == 404
        body = r.json()
        assert body.get("code") == JOB_NOT_IN_AISLE_SCOPE
        assert body.get("detail") == "Job j-bad is not scoped to aisle aisle-1"
    finally:
        app.dependency_overrides.pop(get_compare_aisle_runs_use_case, None)


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
    http = review_exception_to_http(RuntimeError("secret internal text"))
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 500
    assert http.error_code == INTERNAL_SERVER_ERROR
    assert http.detail == "An unexpected error occurred."
    assert "secret" not in http.detail


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
        (
            AisleNotFoundError(),
            "Aisle not found or does not belong to this inventory",
            AISLE_NOT_FOUND,
        ),
        (
            PositionNotFoundError(),
            "Position not found or does not belong to this aisle",
            POSITION_NOT_FOUND,
        ),
        (
            ProductNotFoundError(),
            "Product not found or does not belong to this position",
            PRODUCT_NOT_FOUND,
        ),
        (
            InventoryVisualReferenceNotFoundError(),
            "Visual reference not found",
            VISUAL_REFERENCE_NOT_FOUND,
        ),
        (
            SupplierReferenceImageNotFoundError(),
            HTTP_DETAIL_SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
            SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
        ),
    ],
)
def test_mapped_stable_not_found_details(
    exc: Exception, expected_detail: str, expected_code: str
) -> None:
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


def test_job_not_found_canonical_shape_preserves_id_in_detail() -> None:
    """Canonical ``Job not found: <id>`` → same controlled ``detail`` (Phase 3 mapper rule)."""
    http = mapped_http_exception(JobNotFoundError("Job not found: j-missing"))
    assert http is not None
    assert http.status_code == 404
    assert http.detail == "Job not found: j-missing"
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == JOB_NOT_FOUND


def test_job_not_found_non_canonical_message_maps_to_stable_detail() -> None:
    """Non-canonical ``JobNotFoundError`` message → stable generic ``detail`` (not ``str(exc)``)."""
    http = mapped_http_exception(JobNotFoundError("legacy ad-hoc message"))
    assert http is not None
    assert http.detail == "Job not found"
    assert http.error_code == JOB_NOT_FOUND


@pytest.mark.parametrize(
    "exc,expected_code,status",
    [
        (
            ActiveJobExistsError("Aisle a already has an active job (status=QUEUED)"),
            ACTIVE_JOB_EXISTS,
            409,
        ),
        (
            JobPromotionNotAllowedError("Only succeeded jobs can be promoted (status=FAILED)"),
            JOB_PROMOTION_NOT_ALLOWED,
            409,
        ),
    ],
)
def test_mapped_category_b_conflict_structured_preserves_detail(
    exc: Exception, expected_code: str, status: int
) -> None:
    http = mapped_http_exception(exc)
    assert http is not None
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == status
    assert http.error_code == expected_code
    assert http.detail == str(exc).strip()


def test_mapped_merge_scope_ambiguous_stays_legacy_detail_only() -> None:
    """Category B branch not yet expanded: plain HTTPException, no ``code`` in JSON."""
    http = mapped_http_exception(MergeJobScopeAmbiguousError("merge scope ambiguous"))
    assert http is not None
    assert http.status_code == 422
    assert http.detail == "merge scope ambiguous"
    assert not isinstance(http, StructuredApiHttpError)


def test_mapped_benchmark_compare_jobs_must_differ_is_structured() -> None:
    http = mapped_http_exception(BenchmarkCompareJobsMustDifferError("ignored body"))
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 422
    assert http.error_code == BENCHMARK_COMPARE_JOBS_MUST_DIFFER
    assert http.detail == "job_a_id and job_b_id must be different benchmark runs"


def test_mapped_analytics_scope_validation_is_structured() -> None:
    http = mapped_http_exception(AnalyticsScopeValidationError("ignored"))
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 422
    assert http.error_code == ANALYTICS_SCOPE_VALIDATION_FAILED
    assert http.detail == "aisle_id does not belong to the given inventory_id"


def test_mapped_active_job_exists_non_canonical_detail_is_generic() -> None:
    http = mapped_http_exception(ActiveJobExistsError("unexpected ad-hoc copy"))
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == ACTIVE_JOB_EXISTS
    assert http.detail == "An active job already exists for this aisle"


def test_mapped_no_source_assets_for_processing_is_structured_409() -> None:
    http = mapped_http_exception(
        NoSourceAssetsForAisleProcessingError(
            "No source assets for aisle x; upload media before processing."
        )
    )
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == 409
    assert http.error_code == AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING
    assert http.detail == HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING


def test_mapped_job_promotion_not_allowed_non_canonical_detail_is_generic() -> None:
    http = mapped_http_exception(JobPromotionNotAllowedError("unexpected ad-hoc"))
    assert isinstance(http, StructuredApiHttpError)
    assert http.error_code == JOB_PROMOTION_NOT_ALLOWED
    assert http.detail == "This job cannot be promoted to operational"


@pytest.mark.parametrize(
    "exc,status,expected_code,expected_detail",
    [
        (InventoryNotFoundError(), 404, INVENTORY_NOT_FOUND, "Inventory not found"),
        (
            AisleNotFoundError(),
            404,
            AISLE_NOT_FOUND,
            "Aisle not found or does not belong to this inventory",
        ),
        (
            PositionNotFoundError(),
            404,
            POSITION_NOT_FOUND,
            "Position not found or does not belong to this aisle",
        ),
        (
            ProductNotFoundError(),
            404,
            PRODUCT_NOT_FOUND,
            "Product not found or does not belong to this position",
        ),
        (
            InventoryVisualReferenceNotFoundError(),
            404,
            VISUAL_REFERENCE_NOT_FOUND,
            "Visual reference not found",
        ),
        (
            SupplierReferenceImageNotFoundError(),
            404,
            SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
            HTTP_DETAIL_SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
        ),
        (JobNotFoundError("Job not found: z1"), 404, JOB_NOT_FOUND, "Job not found: z1"),
        (
            JobDoesNotBelongToAisleError("Job zz does not belong to aisle aa"),
            404,
            JOB_NOT_IN_AISLE_SCOPE,
            "Job zz is not scoped to aisle aa",
        ),
        (
            ActiveJobExistsError("Aisle A1 already has an active job (status=RUNNING)"),
            409,
            ACTIVE_JOB_EXISTS,
            "Aisle A1 already has an active job (status=RUNNING)",
        ),
        (
            NoSourceAssetsForAisleProcessingError("ignored message shape"),
            409,
            AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING,
            HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING,
        ),
        (
            JobPromotionNotAllowedError("Only process_aisle jobs can be promoted (got other)"),
            409,
            JOB_PROMOTION_NOT_ALLOWED,
            "Only process_aisle jobs can be promoted (got other)",
        ),
        (
            BenchmarkCompareJobsMustDifferError("ignored"),
            422,
            BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
            "job_a_id and job_b_id must be different benchmark runs",
        ),
        (
            AnalyticsScopeValidationError("ignored"),
            422,
            ANALYTICS_SCOPE_VALIDATION_FAILED,
            "aisle_id does not belong to the given inventory_id",
        ),
        (
            EmptyUploadError("ignored raw message"),
            422,
            EMPTY_UPLOAD,
            HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
        ),
        (
            ZeroByteFileError("ignored raw message"),
            422,
            ZERO_BYTE_FILE,
            HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
        ),
        (
            UnsupportedAssetTypeError("image/bmp is not a supported asset type"),
            400,
            UNSUPPORTED_ASSET_TYPE,
            "image/bmp is not a supported asset type",
        ),
        (
            CaptureSessionInvalidClockOffsetError("clock offset bad"),
            422,
            CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
            "clock offset bad",
        ),
        (
            CaptureSessionPreviewNotAllowedError("preview blocked"),
            409,
            CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
            "preview blocked",
        ),
        (
            CaptureSessionGroupingNotAllowedError("grouping blocked"),
            409,
            CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
            "grouping blocked",
        ),
        (
            CaptureSessionNoItemsForGroupingError("no qualifying items"),
            422,
            CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
            "no qualifying items",
        ),
        (
            CaptureSessionGroupNotFoundError("group missing"),
            404,
            CAPTURE_SESSION_GROUP_NOT_FOUND,
            "group missing",
        ),
        (
            CaptureSessionGroupNotAssignedForMaterializationError(""),
            422,
            CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
            HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
        ),
        (
            CaptureSessionGroupNotAssignedForPreviewError(""),
            422,
            CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
            HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
        ),
        (
            CaptureSessionGroupNotMaterializedForPreviewError(""),
            422,
            CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
            HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
        ),
        (
            CaptureSessionGroupIntegrityError("integrity broken"),
            422,
            CAPTURE_SESSION_GROUP_INTEGRITY_VIOLATION,
            "integrity broken",
        ),
        (
            CaptureSessionGroupAlreadyAssignedError("already done"),
            409,
            CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
            "already done",
        ),
        (
            CaptureSessionGroupAssignmentNotAllowedError("not allowed now"),
            409,
            CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
            "not allowed now",
        ),
        (
            AisleNotFoundForAssignmentError("bad aisle"),
            404,
            AISLE_NOT_FOUND_FOR_ASSIGNMENT,
            "bad aisle",
        ),
    ],
)
def test_final_v3_structured_mapper_contract_matrix(
    exc: Exception,
    status: int,
    expected_code: str,
    expected_detail: str,
) -> None:
    """Lock the full set of mapper-produced structured v3 errors (status, ``code``, ``detail``)."""
    http = mapped_http_exception(exc)
    assert isinstance(http, StructuredApiHttpError)
    assert http.status_code == status
    assert http.error_code == expected_code
    assert http.detail == expected_detail


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


def test_structured_api_error_logs_stable_code_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Observability: ``src.api.server`` logs stable ``error_code`` for structured v3 errors."""

    class _MissingInventory:
        def execute(self, _inventory_id: str):
            raise InventoryNotFoundError()

    app.dependency_overrides[get_get_inventory_use_case] = lambda: _MissingInventory()
    try:
        import logging

        caplog.set_level(logging.INFO, logger="src.api.server")
        TestClient(app, raise_server_exceptions=False).get("/api/v3/inventories/any-id")
        joined = " ".join(rec.getMessage() for rec in caplog.records)
        assert "v3_structured_api_error" in joined
        assert INVENTORY_NOT_FOUND in joined
    finally:
        app.dependency_overrides.pop(get_get_inventory_use_case, None)


def test_get_aisle_status_aisle_not_found_returns_structured_json() -> None:
    """Integration: Category A aisle not-found via ``reraise_if_mapped`` on a real v3 route."""

    class _MissingAisle:
        def execute(self, inventory_id: str, aisle_id: str) -> None:
            raise AisleNotFoundError()

    app.dependency_overrides[get_get_aisle_processing_status_use_case] = lambda: _MissingAisle()
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/status"
        )
        assert r.status_code == 404
        assert r.json() == {
            "code": AISLE_NOT_FOUND,
            "detail": "Aisle not found or does not belong to this inventory",
        }
    finally:
        app.dependency_overrides.pop(get_get_aisle_processing_status_use_case, None)


def test_get_position_detail_position_not_found_returns_structured_json() -> None:
    """Integration: Category A position not-found through positions detail route."""

    class _MissingPosition:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise PositionNotFoundError()

    app.dependency_overrides[get_get_position_detail_use_case] = lambda: _MissingPosition()
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1"
        )
        assert r.status_code == 404
        assert r.json() == {
            "code": POSITION_NOT_FOUND,
            "detail": "Position not found or does not belong to this aisle",
        }
    finally:
        app.dependency_overrides.pop(get_get_position_detail_use_case, None)


def test_get_position_detail_product_not_found_returns_structured_json() -> None:
    """Integration: Category A product not-found through positions detail route."""

    class _MissingProduct:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise ProductNotFoundError()

    app.dependency_overrides[get_get_position_detail_use_case] = lambda: _MissingProduct()
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1"
        )
        assert r.status_code == 404
        assert r.json() == {
            "code": PRODUCT_NOT_FOUND,
            "detail": "Product not found or does not belong to this position",
        }
    finally:
        app.dependency_overrides.pop(get_get_position_detail_use_case, None)


def test_get_visual_reference_file_unknown_id_returns_structured_json() -> None:
    """Integration: ``VISUAL_REFERENCE_NOT_FOUND`` when id is absent from list (route + handler)."""

    class _EmptyRefs:
        def execute(self, inventory_id: str) -> list:
            return []

    app.dependency_overrides[get_list_inventory_visual_references_use_case] = lambda: _EmptyRefs()
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/visual-references/missing-ref-id/file"
        )
        assert r.status_code == 404
        assert r.json() == {
            "code": VISUAL_REFERENCE_NOT_FOUND,
            "detail": "Visual reference not found",
        }
    finally:
        app.dependency_overrides.pop(get_list_inventory_visual_references_use_case, None)


def test_start_aisle_processing_active_job_exists_returns_structured_json() -> None:
    """Integration: Category B structured — controlled ``detail`` + ``code``."""

    msg = "Aisle aisle-1 already has an active job (status=QUEUED)"

    class _BlockedStart:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise ActiveJobExistsError(msg)

    app.dependency_overrides[get_start_aisle_processing_use_case] = lambda: _BlockedStart()
    try:
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/v3/inventories/inv-1/aisles/aisle-1/process",
            json={},
        )
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == ACTIVE_JOB_EXISTS
        assert body["detail"] == msg
        assert body["detail"]
    finally:
        app.dependency_overrides.pop(get_start_aisle_processing_use_case, None)


def test_promote_operational_job_not_allowed_returns_structured_json() -> None:
    """Integration: ``JobPromotionNotAllowedError`` through real route + handler."""

    msg = "Only succeeded jobs can be promoted (status=FAILED)"

    class _BadPromote:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise JobPromotionNotAllowedError(msg)

    app.dependency_overrides[get_promote_aisle_operational_job_use_case] = lambda: _BadPromote()
    try:
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/v3/inventories/inv-1/aisles/aisle-1/promote-operational",
            json={"job_id": "job-x"},
        )
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == JOB_PROMOTION_NOT_ALLOWED
        assert body["detail"] == msg
    finally:
        app.dependency_overrides.pop(get_promote_aisle_operational_job_use_case, None)


def test_integration_category_b_job_not_found_client_reads_detail_only() -> None:
    """Real HTTP: canonical ``Job not found: …`` through compare route; detail-only clients OK."""

    class _CompareFails:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise JobNotFoundError("Job not found: job-compare-missing")

    app.dependency_overrides[get_compare_aisle_runs_use_case] = lambda: _CompareFails()
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/benchmark/compare",
            params={"job_a_id": "ja", "job_b_id": "jb"},
        )
        assert r.status_code == 404
        payload = r.json()
        assert payload.get("code") == JOB_NOT_FOUND
        detail_only = payload["detail"]
        assert detail_only == "Job not found: job-compare-missing"
        assert "job-compare-missing" in detail_only
    finally:
        app.dependency_overrides.pop(get_compare_aisle_runs_use_case, None)


def test_get_aisle_job_detail_job_not_found_is_category_c_detail_only() -> None:
    """Integration: Phase 6 job-read path stays legacy ``{{\"detail\"}}`` (no ``code``)."""

    class _MissingJob:
        def execute(self, inventory_id: str, aisle_id: str, job_id: str) -> None:
            raise JobNotFoundError("Job not found: internal-id-must-not-leak")

    app.dependency_overrides[get_resolve_aisle_job_for_inventory_read_use_case] = lambda: (
        _MissingJob()
    )
    try:
        r = TestClient(app, raise_server_exceptions=False).get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/jobs/job-missing"
        )
        assert r.status_code == 404
        assert r.json() == {"detail": "Job not found"}
        assert "code" not in r.json()
    finally:
        app.dependency_overrides.pop(get_resolve_aisle_job_for_inventory_read_use_case, None)


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
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.error_code, "detail": exc.detail}
        )

    @mini.get("/s")
    def _structured_route():
        raise StructuredApiHttpError(
            404, error_code=INVENTORY_NOT_FOUND, detail="Inventory not found"
        )

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
    assert isinstance(m, StructuredApiHttpError)
    assert m.error_code == JOB_NOT_FOUND
    with pytest.raises(HTTPException):
        raise m
    with pytest.raises(StructuredApiHttpError):
        raise m
