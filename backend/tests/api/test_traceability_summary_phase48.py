"""Phase 4.8 — job traceability summary endpoint tests."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_resolve_aisle_job_for_inventory_read_use_case,
    get_result_evidence_query_service,
)
from src.api.server import app
from src.application.services.result_evidence_query_service import (
    JobTraceabilityReadModel,
    ResultEvidenceViewModel,
    TraceabilityArtifactReadModel,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.jobs.entities import Job, JobStatus


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)


class StubResolve:
    def execute(self, inventory_id, aisle_id, job_id) -> Job:
        return Job(
            id="job-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={"aisle_id": "aisle-1"},
            created_at=NOW,
            updated_at=NOW,
        )


class StubTraceabilityQuery:
    def get_job_traceability(self, **_kwargs) -> JobTraceabilityReadModel:
        view = ResultEvidenceViewModel(
            displayable=True,
            traceability_status="valid",
            traceability_warning=None,
            role="primary_evidence",
            source_image_id="asset-1",
            source_asset_id="asset-1",
            resolved_manifest_entry_id="IMG_001",
            raw_manifest_entry_id="IMG_001",
            raw_source_image_id=None,
            image_url="https://cdn.example.com/a.jpg",
            thumbnail_url=None,
            image_access_status="available",
            source_kind="structural_result_evidence",
            provider="gemini",
            model_name="gemini-2.0",
        )
        return JobTraceabilityReadModel(
            job_id="job-1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            traceability_status="available",
            artifact=TraceabilityArtifactReadModel(
                kind="traceability_manifest",
                published=True,
                required=True,
                status="published",
                storage_key="jobs/job-1/run/traceability_manifest.json",
                content_hash="hash",
                size_bytes=100,
                published_at=NOW,
            ),
            summary={
                "total_evidence_rows": 1,
                "valid": 1,
                "invalid": 0,
                "missing": 0,
                "unvalidated": 0,
                "displayable": 1,
                "not_displayable": 0,
                "reference_rejected": 0,
                "unknown_identifier": 0,
                "conflicting_identifier": 0,
                "manifest_unavailable": 0,
                "manifest_invalid": 0,
                "artifact_published": 1,
            },
            entities=[
                {
                    "position_id": "pos-1",
                    "entity_uid": "job_E1",
                    "model_entity_id": "E1",
                    "evidence": view,
                }
            ],
        )


def test_job_traceability_endpoint_shape() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_resolve_aisle_job_for_inventory_read_use_case] = lambda: StubResolve()
    app.dependency_overrides[get_result_evidence_query_service] = lambda: StubTraceabilityQuery()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-1/aisles/aisle-1/jobs/job-1/traceability")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"] == "job-1"
        assert body["traceability"]["status"] == "available"
        assert body["traceability"]["artifact"]["kind"] == "traceability_manifest"
        assert body["entities"][0]["evidence"]["displayable"] is True
        assert body["traceability"]["summary"]["displayable"] == 1
    finally:
        app.dependency_overrides.clear()
