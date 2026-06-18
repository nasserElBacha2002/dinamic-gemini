"""Phase 4.8 — position detail structural evidence API contract tests."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import get_get_position_detail_use_case, get_result_evidence_query_service
from src.api.schemas.result_evidence_schemas import ResultEvidenceViewResponse
from src.api.server import app
from src.application.use_cases.positions.get_position_detail import (
    PositionDetailResult,
    PositionDetailRunContext,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.positions.entities import Position, PositionStatus


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)


def _position() -> Position:
    return Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={
            "entity_uid": "job-1_E1",
            "source_image_id": "asset-1",
            "traceability_status": "valid",
            "has_valid_evidence": True,
        },
        job_id="job-1",
    )


class StubDetailUseCase:
    def execute(self, *_args, **_kwargs) -> PositionDetailResult:
        return PositionDetailResult(
            position=_position(),
            products=[],
            evidences=[],
            review_actions=[],
            run_context=PositionDetailRunContext(
                job_id="job-1",
                result_context_source="explicit",
                resolved_job_id="job-1",
            ),
        )


class StubEvidenceQuery:
    def get_position_evidence_view(self, **_kwargs):
        from src.application.services.result_evidence_query_service import ResultEvidenceViewModel

        return ResultEvidenceViewModel(
            displayable=True,
            traceability_status="valid",
            traceability_warning=None,
            role="primary_evidence",
            source_image_id="asset-1",
            source_asset_id="asset-1",
            resolved_manifest_entry_id="IMG_001",
            raw_manifest_entry_id="IMG_001",
            raw_source_image_id=None,
            image_url="https://cdn.example.com/asset-1.jpg",
            thumbnail_url="https://cdn.example.com/asset-1.jpg",
            image_access_status="available",
            source_kind="structural_result_evidence",
            provider="gemini",
            model_name="gemini-2.0",
        )

    def get_traceability_artifact(self, job_id=None, **_kwargs):
        from src.application.services.result_evidence_query_service import TraceabilityArtifactReadModel

        return TraceabilityArtifactReadModel(
            kind="traceability_manifest",
            published=True,
            required=True,
            status="published",
            storage_key="jobs/job-1/run/traceability_manifest.json",
            content_hash="hash-abc",
            size_bytes=100,
            published_at=NOW,
        )


def test_position_detail_includes_structural_evidence_object() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_get_position_detail_use_case] = lambda: StubDetailUseCase()
    app.dependency_overrides[get_result_evidence_query_service] = lambda: StubEvidenceQuery()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1")
        assert resp.status_code == 200
        body = resp.json()
        assert "evidence" in body
        assert body["evidence"]["displayable"] is True
        assert body["evidence"]["source_kind"] == "structural_result_evidence"
        assert body["evidences"] == []
        assert body["traceability_artifact"]["content_hash"] == "hash-abc"
        ResultEvidenceViewResponse.model_validate(body["evidence"])
    finally:
        app.dependency_overrides.clear()


def test_position_detail_uses_resolved_job_id_for_evidence_lookup() -> None:
    captured: dict[str, object] = {}

    class ResolvingQuery(StubEvidenceQuery):
        def get_position_evidence_view(self, **kwargs):
            captured.update(kwargs)
            return super().get_position_evidence_view(**kwargs)

    class MismatchedStorageUseCase(StubDetailUseCase):
        def execute(self, *_args, **_kwargs) -> PositionDetailResult:
            result = super().execute()
            return PositionDetailResult(
                position=Position(
                    id="pos-1",
                    aisle_id="aisle-1",
                    status=PositionStatus.DETECTED,
                    confidence=0.9,
                    needs_review=False,
                    primary_evidence_id="ev-1",
                    created_at=NOW,
                    updated_at=NOW,
                    detected_summary_json={"entity_uid": "job_E1"},
                    job_id="old-job",
                ),
                products=[],
                evidences=[],
                review_actions=[],
                run_context=PositionDetailRunContext(
                    job_id="job-1",
                    result_context_source="operational",
                    resolved_job_id="current-job",
                ),
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_get_position_detail_use_case] = lambda: MismatchedStorageUseCase()
    app.dependency_overrides[get_result_evidence_query_service] = lambda: ResolvingQuery()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1")
        assert resp.status_code == 200
        assert captured.get("job_id") == "current-job"
    finally:
        app.dependency_overrides.clear()


def test_invalid_evidence_has_no_image_url() -> None:
    class InvalidQuery(StubEvidenceQuery):
        def get_position_evidence_view(self, **_kwargs):
            from src.application.services.result_evidence_query_service import ResultEvidenceViewModel

            return ResultEvidenceViewModel(
                displayable=False,
                traceability_status="invalid",
                traceability_warning="unknown",
                role="unknown",
                source_image_id="IMG_999",
                source_asset_id=None,
                resolved_manifest_entry_id=None,
                raw_manifest_entry_id=None,
                raw_source_image_id=None,
                image_url=None,
                thumbnail_url=None,
                image_access_status="not_allowed",
                source_kind="structural_result_evidence",
                provider="gemini",
                model_name="gemini-2.0",
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_get_position_detail_use_case] = lambda: StubDetailUseCase()
    app.dependency_overrides[get_result_evidence_query_service] = lambda: InvalidQuery()
    try:
        client = TestClient(app)
        body = client.get("/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1").json()
        assert body["evidence"]["displayable"] is False
        assert body["evidence"]["image_url"] is None
    finally:
        app.dependency_overrides.clear()
