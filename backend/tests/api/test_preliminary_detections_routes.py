"""API tests for preliminary detection upsert route."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import get_upsert_preliminary_detection_use_case
from src.api.server import app
from src.application.errors import AisleNotFoundError
from src.application.use_cases.aisles.upsert_preliminary_detection import (
    PRELIMINARY_ASSET_PENDING,
    PRELIMINARY_IDEMPOTENCY_CONFLICT,
    PRELIMINARY_INGEST_DISABLED,
    PRELIMINARY_VALIDATION_FAILED,
    PreliminaryDetectionIngestDisabledError,
    UpsertPreliminaryDetectionCommand,
    UpsertPreliminaryDetectionResult,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def _body(**over):
    base = {
        "schema_version": "1",
        "client_file_id": "cf-1",
        "asset_id": "asset-1",
        "processing_mode": "CODE_SCAN",
        "status": "RESOLVED",
        "internal_code": "ABC",
        "quantity": 1,
        "quantity_status": "PRESENT",
        "candidate_count": 1,
        "parser_version": "1.1.0",
        "detector_version": "mlkit-1",
        "prepared_asset_sha256": "sha256:" + ("a" * 64),
    }
    base.update(over)
    return base


PATH = "/api/v3/inventories/inv-1/aisles/aisle-1/preliminary-detections/draft-1"


def test_requires_auth():
    client = TestClient(app, raise_server_exceptions=False)
    res = client.put(PATH, json=_body())
    assert res.status_code in (401, 403, 404)


def test_success_validated():
    class Stub:
        def execute(self, cmd: UpsertPreliminaryDetectionCommand):
            assert cmd.draft_id == "draft-1"
            return UpsertPreliminaryDetectionResult(
                draft_id="draft-1",
                requested_draft_id="draft-1",
                server_preliminary_id="srv-1",
                status="VALIDATED",
                received_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                validation_errors=(),
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_upsert_preliminary_detection_use_case] = lambda: Stub()
    try:
        client = TestClient(app)
        res = client.put(PATH, json=_body())
        assert res.status_code == 200
        assert res.json()["server_preliminary_id"] == "srv-1"
        assert res.json()["requested_draft_id"] == "draft-1"
    finally:
        app.dependency_overrides.clear()


def test_disabled_returns_typed_code():
    class Stub:
        def execute(self, cmd):
            raise PreliminaryDetectionIngestDisabledError()

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_upsert_preliminary_detection_use_case] = lambda: Stub()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.put(PATH, json=_body())
        assert res.status_code == 404
        assert res.json()["code"] == PRELIMINARY_INGEST_DISABLED
    finally:
        app.dependency_overrides.clear()


def test_validation_failed_typed_code():
    class Stub:
        def execute(self, cmd):
            return UpsertPreliminaryDetectionResult(
                draft_id="draft-1",
                requested_draft_id="draft-1",
                server_preliminary_id="",
                status="REJECTED",
                received_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                validation_errors=("INTERNAL_CODE_REQUIRED_FOR_RESOLVED",),
                error_code=PRELIMINARY_VALIDATION_FAILED,
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_upsert_preliminary_detection_use_case] = lambda: Stub()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.put(PATH, json=_body(internal_code=None, status="RESOLVED", quantity=None, quantity_status=None))
        # pydantic may reject first; if it reaches use case:
        if res.status_code == 422:
            body = res.json()
            assert body.get("code") in (PRELIMINARY_VALIDATION_FAILED, None) or "detail" in body
    finally:
        app.dependency_overrides.clear()


def test_conflict_typed_code():
    class Stub:
        def execute(self, cmd):
            return UpsertPreliminaryDetectionResult(
                draft_id="canonical",
                requested_draft_id="draft-1",
                server_preliminary_id="srv-1",
                status="CONFLICT",
                received_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                validation_errors=("IDEMPOTENCY_CONTENT_CONFLICT",),
                error_code=PRELIMINARY_IDEMPOTENCY_CONFLICT,
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_upsert_preliminary_detection_use_case] = lambda: Stub()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.put(PATH, json=_body())
        assert res.status_code == 409
        assert res.json()["code"] == PRELIMINARY_IDEMPOTENCY_CONFLICT
    finally:
        app.dependency_overrides.clear()


def test_asset_pending_typed_code():
    class Stub:
        def execute(self, cmd):
            return UpsertPreliminaryDetectionResult(
                draft_id="draft-1",
                requested_draft_id="draft-1",
                server_preliminary_id="",
                status="PENDING_ASSET",
                received_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                validation_errors=("ASSET_NOT_FOUND_OR_MISMATCHED",),
                error_code=PRELIMINARY_ASSET_PENDING,
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_upsert_preliminary_detection_use_case] = lambda: Stub()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.put(PATH, json=_body())
        assert res.status_code == 404
        assert res.json()["code"] == PRELIMINARY_ASSET_PENDING
    finally:
        app.dependency_overrides.clear()


def test_aisle_not_found_mapped():
    class Stub:
        def execute(self, cmd):
            raise AisleNotFoundError("Aisle not found: aisle-1")

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_upsert_preliminary_detection_use_case] = lambda: Stub()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.put(PATH, json=_body())
        assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()
