"""Unit tests for ProcessingResultPersister NEEDS_REVIEW (code without quantity)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.services.image_processing.processing_result_persister import (
    PersistenceMode,
    PersistOutcome,
    PersistSkipReason,
    ProcessingResultPersister,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _link(*, job_id: str, asset_id: str) -> JobSourceAssetLink:
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    return JobSourceAssetLink(
        id=f"jsa-{asset_id}",
        job_id=job_id,
        source_asset_id=asset_id,
        asset_role="primary",
        position_order=0,
        checksum=None,
        storage_key=f"key/{asset_id}.jpg",
        mime_type="image/jpeg",
        size_bytes=100,
        width=None,
        height=None,
        stage=None,
        provider_request_id=None,
        created_at=now,
        original_filename=f"{asset_id}.jpg",
    )


def _persister_harness(
    *,
    asset_id: str = "asset-1",
    job_id: str = "job-1",
    existing_coverage=None,
    existing_position=None,
):
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    job_source = MagicMock()
    job_source.list_for_job.return_value = [_link(job_id=job_id, asset_id=asset_id)]
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(
        storage_path=f"path/{asset_id}.jpg",
        storage_key=f"key/{asset_id}.jpg",
        content_type="image/jpeg",
        file_size_bytes=100,
    )

    saved: dict[str, object] = {}
    position_repo = MagicMock()
    position_repo.get_by_id.return_value = existing_position
    product_repo = MagicMock()
    evidence_repo = MagicMock()
    coverage_repo = MagicMock()
    coverage_repo.get_by_job_and_asset.return_value = existing_coverage
    image_coverage_repo = MagicMock()
    image_coverage_repo.has_results_for_asset.return_value = False
    result_evidence_repo = MagicMock()

    def _save_position(pos):
        saved["position"] = pos

    def _save_product(prod):
        saved["product"] = prod

    position_repo.save.side_effect = _save_position
    product_repo.save.side_effect = _save_product

    repos = SimpleNamespace(
        manual_coverage_repo=coverage_repo,
        image_coverage_repo=image_coverage_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        result_evidence_repo=result_evidence_repo,
        counted_product_label_repo=MagicMock(),
    )
    uow = MagicMock()
    uow.repositories = repos
    uow.__enter__ = MagicMock(return_value=uow)
    uow.__exit__ = MagicMock(return_value=False)

    persister = ProcessingResultPersister(
        job_source_asset_repo=job_source,
        source_asset_repo=source_repo,
        clock=FixedClock(now),
        unit_of_work_factory=lambda: uow,
    )
    return persister, saved, job_id, asset_id


def test_persist_code_without_quantity_creates_needs_review_position():
    persister, saved, job_id, asset_id = _persister_harness()
    result = ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.RESOLVED_EXTERNAL,
        processing_mode="EXTERNAL_PROVIDER",
        resolved_by="EXTERNAL_PROVIDER",
        internal_code="3075807",
        quantity=None,
        execution_scope=ExecutionScope.AISLE_BATCH,
        logical_asset_attempt=True,
        provider_name="claude",
        evidence={"identity_valid": True, "missing_fields": ["quantity"]},
    )

    outcome = persister.persist(result=result, inventory_id="inv-1", aisle_id="aisle-1")

    # Identity preserved as review position; no ProductRecord / no qty=0 invent.
    assert outcome.persisted is True
    assert outcome.products_persisted == 0
    assert outcome.skipped_reason is None
    assert outcome.persistence_mode is PersistenceMode.IDENTITY_REVIEW
    position = saved["position"]
    assert position.needs_review is True
    assert position.detected_summary_json["quantity_status"] == "MISSING"
    assert position.detected_summary_json["internal_code"] == "3075807"
    assert "product" not in saved or saved.get("product") is None


def test_persist_pending_identity_also_creates_review():
    persister, saved, job_id, asset_id = _persister_harness()
    result = ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.PENDING_MANUAL_REVIEW,
        processing_mode="CODE_SCAN",
        resolved_by="code_scan",
        internal_code="PRD-123456",
        quantity=None,
        error_code="MISSING_QUANTITY",
        evidence={"identity_valid": True, "enrichment_complete": False},
    )
    outcome = persister.persist(result=result, inventory_id="inv-1", aisle_id="aisle-1")
    assert outcome.persisted is True
    assert saved["position"].needs_review is True
    assert outcome.products_persisted == 0


def test_persist_code_with_positive_quantity_unchanged():
    persister, saved, job_id, asset_id = _persister_harness()
    result = ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.RESOLVED_EXTERNAL,
        processing_mode="EXTERNAL_PROVIDER",
        resolved_by="EXTERNAL_PROVIDER",
        internal_code="3075807",
        quantity=16.0,
        execution_scope=ExecutionScope.AISLE_BATCH,
        logical_asset_attempt=True,
        provider_name="claude",
    )

    outcome = persister.persist(result=result, inventory_id="inv-1", aisle_id="aisle-1")

    assert outcome.persisted is True
    assert saved["position"].needs_review is False
    assert saved["product"].detected_quantity == 16
    assert saved["product"].qty_parse_status == "valid_positive"


def test_persist_missing_code_still_skipped():
    persister, saved, job_id, asset_id = _persister_harness()
    result = ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.RESOLVED_EXTERNAL,
        processing_mode="EXTERNAL_PROVIDER",
        resolved_by="EXTERNAL_PROVIDER",
        internal_code=None,
        quantity=None,
        execution_scope=ExecutionScope.AISLE_BATCH,
        logical_asset_attempt=True,
    )

    outcome = persister.persist(result=result, inventory_id="inv-1", aisle_id="aisle-1")

    assert outcome.persisted is False
    assert outcome.skipped_reason is PersistSkipReason.MISSING_CODE_OR_QUANTITY
    assert "position" not in saved


def test_persist_outcome_rejects_persisted_with_skipped_reason() -> None:
    with pytest.raises(ValueError, match="skipped_reason"):
        PersistOutcome(
            persisted=True,
            skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
        )


def test_decimal_quantity_is_not_truncated_to_product_record() -> None:
    persister, saved, job_id, asset_id = _persister_harness()
    result = ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.RESOLVED_EXTERNAL,
        processing_mode="EXTERNAL_PROVIDER",
        resolved_by="EXTERNAL_PROVIDER",
        internal_code="3075807",
        quantity=1.5,
        execution_scope=ExecutionScope.AISLE_BATCH,
        logical_asset_attempt=True,
        provider_name="claude",
        evidence={"identity_valid": True, "missing_fields": ["quantity"]},
    )
    outcome = persister.persist(result=result, inventory_id="inv-1", aisle_id="aisle-1")
    assert outcome.persisted is True
    assert outcome.persistence_mode is PersistenceMode.IDENTITY_REVIEW
    assert outcome.skipped_reason is None
    assert "product" not in saved
    assert saved["position"].needs_review is True


def test_identity_review_idempotent_replay() -> None:
    existing = SimpleNamespace(position_id="pos-existing", created_by_user_id=None)
    linked = SimpleNamespace(job_id="job-1")
    persister, saved, job_id, asset_id = _persister_harness(
        existing_coverage=existing,
        existing_position=linked,
    )
    result = ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.PENDING_MANUAL_REVIEW,
        processing_mode="CODE_SCAN",
        resolved_by="code_scan",
        internal_code="PRD-123456",
        quantity=None,
        error_code="MISSING_QUANTITY",
        evidence={"identity_valid": True, "enrichment_complete": False},
    )
    outcome = persister.persist(result=result, inventory_id="inv-1", aisle_id="aisle-1")
    assert outcome.persisted is True
    assert outcome.idempotent_replay is True
    assert outcome.persistence_mode is PersistenceMode.IDENTITY_REVIEW
    assert outcome.skipped_reason is None
    assert outcome.position_id == "pos-existing"
    assert "position" not in saved
    assert "product" not in saved
