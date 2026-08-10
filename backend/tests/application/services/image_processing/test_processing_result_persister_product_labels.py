"""ALL_LABELS_DUPLICATE + mixed new/duplicate persist behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.services.image_processing.processing_result_persister import (
    PersistSkipReason,
    ProcessingResultPersister,
)
from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
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


def _spec(label_id: str, sku: str = "SKU1", qty: int = 2) -> ProcessedProductLabel:
    return ProcessedProductLabel(
        label_id=label_id,
        internal_code=sku,
        quantity=qty,
        format_version="D1",
        checksum="6",
        validation_status=ProductLabelOutcomeStatus.VALID,
        raw_payload=f"D1|{label_id}|{sku}|{qty}|6",
        normalized_payload=f"D1|{label_id}|{sku}|{qty}|6",
    )


def _result(*specs: ProcessedProductLabel, job_id: str = "job-1", asset_id: str = "asset-1") -> ImageProcessingResult:
    primary = specs[0]
    return ImageProcessingResult(
        job_id=job_id,
        asset_id=asset_id,
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        internal_code=primary.internal_code,
        quantity=float(primary.quantity or 0),
        product_results=list(specs),
        evidence={"code_scan": True},
    )


def _harness(*, counted: MemoryInventoryCountedProductLabelRepository):
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    job_source = MagicMock()
    job_source.list_for_job.return_value = [_link(job_id="job-1", asset_id="asset-1")]
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(
        storage_path="path/asset-1.jpg",
        storage_key="key/asset-1.jpg",
        content_type="image/jpeg",
        file_size_bytes=100,
    )

    saved_products: list = []
    saved_positions: list = []
    position_repo = MagicMock()
    product_repo = MagicMock()
    position_repo.save.side_effect = lambda p: saved_positions.append(p)
    product_repo.save.side_effect = lambda p: saved_products.append(p)

    coverage_repo = MagicMock()
    coverage_repo.get_by_job_and_asset.return_value = None
    image_coverage_repo = MagicMock()
    image_coverage_repo.has_results_for_asset.return_value = False

    repos = SimpleNamespace(
        manual_coverage_repo=coverage_repo,
        image_coverage_repo=image_coverage_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=MagicMock(),
        result_evidence_repo=MagicMock(),
        counted_product_label_repo=counted,
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
    return persister, saved_positions, saved_products, now


def test_all_labels_duplicate_skips_empty_position() -> None:
    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    for lid, pid in (("A1B2C3D4E5", "p0"), ("FGHJKMNPQR", "p1")):
        counted.try_claim(
            InventoryCountedProductLabel(
                id=f"c-{lid}",
                inventory_id="inv-1",
                label_id=lid,
                first_product_record_id=pid,
                first_source_asset_id="a0",
                first_job_id="j0",
                first_position_id="pos0",
                created_at=now,
            )
        )
    persister, saved_positions, saved_products, _ = _harness(counted=counted)
    outcome = persister.persist(
        result=_result(_spec("A1B2C3D4E5"), _spec("FGHJKMNPQR")),
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    assert outcome.persisted is False
    assert outcome.skipped_reason is PersistSkipReason.ALL_LABELS_DUPLICATE
    assert outcome.products_skipped_duplicate == 2
    assert saved_positions == []
    assert saved_products == []


def test_mixed_duplicate_and_new_persists_only_new() -> None:
    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    counted.try_claim(
        InventoryCountedProductLabel(
            id="c1",
            inventory_id="inv-1",
            label_id="A1B2C3D4E5",
            first_product_record_id="p0",
            first_source_asset_id="a0",
            first_job_id="j0",
            first_position_id="pos0",
            created_at=now,
        )
    )
    persister, saved_positions, saved_products, _ = _harness(counted=counted)
    outcome = persister.persist(
        result=_result(_spec("A1B2C3D4E5"), _spec("FGHJKMNPQR", "SKU2", 3)),
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    assert outcome.persisted is True
    assert outcome.products_skipped_duplicate == 1
    assert outcome.products_persisted == 1
    assert len(saved_positions) == 1
    assert len(saved_products) == 1
    assert saved_products[0].label_id == "FGHJKMNPQR"
    assert saved_products[0].sku == "SKU2"
