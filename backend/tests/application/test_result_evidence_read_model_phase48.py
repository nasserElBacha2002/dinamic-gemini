"""Phase 4.8 — structural result_evidence read model tests."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.result_evidence_query_service import ResultEvidenceQueryService
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_TRACEABILITY_MANIFEST
from src.domain.positions.entities import Position, PositionStatus
from src.domain.result_evidence.display import compute_structural_api_displayable
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus
from src.infrastructure.persistence.memory_artifact_manifest_store import (
    MemoryArtifactManifestStore,
)
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 18, tzinfo=timezone.utc)


def _row(**overrides) -> ResultEvidenceRecord:
    base = ResultEvidenceRecord(
        id="re-1",
        job_id="job-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position_id="pos-1",
        entity_uid="job_E1",
        model_entity_id="E1",
        raw_manifest_entry_id="IMG_001",
        manifest_entry_id="IMG_001",
        raw_source_image_id=None,
        resolved_manifest_entry_id="IMG_001",
        source_image_id="asset-1",
        source_asset_id="asset-1",
        traceability_status=TraceabilityStatus.VALID.value,
        traceability_warning=None,
        role=ResultEvidenceRole.PRIMARY_EVIDENCE,
        provider="gemini",
        model_name="gemini-2.0",
        schema_version="2.1",
        manifest_version=1,
        has_valid_evidence=True,
        evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
        created_at=_now(),
        updated_at=_now(),
    )
    return ResultEvidenceRecord(**{**base.__dict__, **overrides})


class _AssetRepo:
    def list_by_aisle(self, aisle_id: str):
        if aisle_id != "aisle-1":
            return []
        return [
            SourceAsset(
                id="asset-1",
                aisle_id="aisle-1",
                type=SourceAssetType.PHOTO,
                original_filename="a.jpg",
                storage_path="photos/a.jpg",
                mime_type="image/jpeg",
                uploaded_at=_now(),
            )
        ]


def _service(
    rows: list[ResultEvidenceRecord] | None = None,
    *,
    manifest_store: MemoryArtifactManifestStore | None = None,
    image_resolver=None,
) -> ResultEvidenceQueryService:
    repo = MemoryResultEvidenceRepository()
    if rows:
        repo.save_many(rows)
    resolver = image_resolver or (lambda asset, artifact_store=None: ("https://cdn.example.com/a.jpg", False))
    return ResultEvidenceQueryService(
        result_evidence_repo=repo,
        source_asset_repo=_AssetRepo(),
        manifest_store=manifest_store,
        artifact_store=None,
        image_url_resolver=resolver,
    )


def test_valid_structural_row_displayable_true() -> None:
    view = _service([_row()]).build_evidence_view(
        _row(),
        inventory_id="inv-1",
        aisle_id="aisle-1",
        assets_by_id={"asset-1": _AssetRepo().list_by_aisle("aisle-1")[0]},
    )
    assert view.displayable is True
    assert view.traceability_status == TraceabilityStatus.VALID.value


def test_valid_row_missing_url_makes_displayable_false() -> None:
    def _fail_url(_asset, artifact_store=None):
        raise RuntimeError("signing failed")

    view = _service([_row()], image_resolver=_fail_url).build_evidence_view(
        _row(),
        inventory_id="inv-1",
        aisle_id="aisle-1",
        assets_by_id={"asset-1": _AssetRepo().list_by_aisle("aisle-1")[0]},
    )
    assert view.image_access_status == "url_unavailable"
    assert view.displayable is False


def test_invalid_reference_displayable_false() -> None:
    row = _row(
        traceability_status=TraceabilityStatus.INVALID.value,
        role=ResultEvidenceRole.REFERENCE_IMAGE,
        has_valid_evidence=False,
        traceability_warning="Provider returned reference REF_001.",
    )
    view = _service([row]).build_evidence_view(
        row,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        assets_by_id={},
    )
    assert view.displayable is False


def test_missing_row_displayable_false() -> None:
    row = _row(
        traceability_status=TraceabilityStatus.MISSING.value,
        has_valid_evidence=False,
        source_image_id=None,
    )
    view = _service([row]).build_evidence_view(row, inventory_id="inv-1", aisle_id="aisle-1", assets_by_id={})
    assert view.displayable is False


def test_unvalidated_row_displayable_false() -> None:
    row = _row(
        traceability_status=TraceabilityStatus.UNVALIDATED.value,
        has_valid_evidence=False,
    )
    view = _service([row]).build_evidence_view(row, inventory_id="inv-1", aisle_id="aisle-1", assets_by_id={})
    assert view.displayable is False


def test_no_structural_row_legacy_unavailable() -> None:
    view = _service([]).build_evidence_view(None, inventory_id="inv-1", aisle_id="aisle-1", assets_by_id={})
    assert view.displayable is False
    assert view.traceability_status == "legacy_unavailable"
    assert view.source_kind == "unavailable"


def test_traceability_artifact_metadata_when_published() -> None:
    store = MemoryArtifactManifestStore()
    now = _now()
    store.mark_published(
        job_id="job-1",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        storage_key="jobs/job-1/run/traceability_manifest.json",
        size_bytes=100,
        content_hash="abc",
        required=True,
        now=now,
    )
    model = _service([_row()], manifest_store=store).get_job_traceability(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        job_id="job-1",
    )
    assert model.artifact is not None
    assert model.artifact.published is True
    assert model.summary["artifact_published"] == 1


def test_required_artifact_missing_sets_artifact_unavailable() -> None:
    store = MemoryArtifactManifestStore()
    now = _now()
    store.mark_pending(
        job_id="job-1",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        required=True,
        now=now,
    )
    model = _service([_row()], manifest_store=store).get_job_traceability(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        job_id="job-1",
    )
    assert model.traceability_status == "artifact_unavailable"


def test_compute_structural_api_displayable_requires_asset() -> None:
    row = _row(source_asset_id=None)
    assert compute_structural_api_displayable(row, resolved_source_asset_id=None) is False


def _position(**overrides) -> Position:
    base = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=_now(),
        updated_at=_now(),
        detected_summary_json={"entity_uid": "job_E1"},
        job_id="old-job",
    )
    return Position(**{**base.__dict__, **overrides})


def test_position_detail_blocks_when_required_artifact_unpublished() -> None:
    store = MemoryArtifactManifestStore()
    store.mark_pending(
        job_id="job-1",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        required=True,
        now=_now(),
    )
    view = _service([_row()], manifest_store=store).get_position_evidence_view(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position=_position(),
        job_id="job-1",
    )
    assert view.displayable is False
    assert view.traceability_status == "artifact_unavailable"
    assert view.image_url is None
    assert view.image_access_status == "not_allowed"


def test_position_detail_allows_when_required_artifact_published() -> None:
    store = MemoryArtifactManifestStore()
    store.mark_published(
        job_id="job-1",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        storage_key="jobs/job-1/run/traceability_manifest.json",
        size_bytes=100,
        content_hash="abc",
        required=True,
        now=_now(),
    )
    view = _service([_row()], manifest_store=store).get_position_evidence_view(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position=_position(),
        job_id="job-1",
    )
    assert view.displayable is True
    assert view.traceability_status == TraceabilityStatus.VALID.value
    assert view.image_url is not None


def test_position_evidence_uses_resolved_job_not_storage_job_id() -> None:
    row = _row(job_id="current-job", position_id="pos-1")
    svc = _service([row])
    view = svc.get_position_evidence_view(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position=_position(job_id="old-job"),
        job_id="current-job",
    )
    assert view.source_kind == "structural_result_evidence"
    assert view.displayable is True


def test_position_evidence_with_null_storage_job_uses_resolved_job() -> None:
    row = _row(job_id="current-job", position_id="pos-1")
    svc = _service([row])
    view = svc.get_position_evidence_view(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position=_position(job_id=None),
        job_id="current-job",
    )
    assert view.displayable is True
    assert view.traceability_status == TraceabilityStatus.VALID.value


def test_source_asset_mismatch_blocks_display() -> None:
    row = _row(source_image_id="asset-1", source_asset_id="asset-2")
    view = _service([row]).build_evidence_view(
        row,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        assets_by_id={"asset-2": _AssetRepo().list_by_aisle("aisle-1")[0]},
    )
    assert view.displayable is False
    assert view.image_access_status == "not_allowed"
    assert view.traceability_status == TraceabilityStatus.INVALID.value
    assert "does not match" in (view.traceability_warning or "")


def test_summary_malformed_identifier_bucket() -> None:
    row = _row(
        traceability_status=TraceabilityStatus.INVALID.value,
        has_valid_evidence=False,
        traceability_warning="Malformed identifier img_001.",
    )
    view = _service([row]).build_evidence_view(
        row,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        assets_by_id={},
    )
    summary = _service([row])._summary_from_rows([view])
    assert summary["malformed_identifier"] == 1


def test_summary_unvalidated_unknown_bucket() -> None:
    row = _row(
        traceability_status=TraceabilityStatus.UNVALIDATED.value,
        has_valid_evidence=False,
        traceability_warning="Could not validate evidence.",
    )
    view = _service([row]).build_evidence_view(
        row,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        assets_by_id={},
    )
    summary = _service([row])._summary_from_rows([view])
    assert summary["unvalidated_unknown"] == 1


def test_summary_artifact_required_unpublished() -> None:
    store = MemoryArtifactManifestStore()
    store.mark_pending(
        job_id="job-1",
        artifact_kind=ARTIFACT_KIND_TRACEABILITY_MANIFEST,
        required=True,
        now=_now(),
    )
    model = _service([_row()], manifest_store=store).get_job_traceability(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        job_id="job-1",
    )
    assert model.summary["artifact_required"] == 1
    assert model.summary["artifact_published"] == 0
