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
    return persister, saved_positions, saved_products, coverage_repo, now


def test_all_labels_duplicate_skips_empty_position() -> None:
    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    for lid, pid in (("A1B2C3D4E5", "p0"), ("FGHJKMNPQR", "p1")):
        counted.try_claim(
            InventoryCountedProductLabel(
                id=f"c-{lid}",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                label_id=lid,
                first_product_record_id=pid,
                first_source_asset_id="a0",
                first_job_id="j0",
                first_position_id="pos0",
                created_at=now,
            )
        )
    persister, saved_positions, saved_products, _, _ = _harness(counted=counted)
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


def test_all_labels_duplicate_same_asset_clones_position_for_current_job() -> None:
    """Cross-job reprocess must clone Position under the new job_id (not link old job)."""
    from src.domain.positions.entities import Position, PositionCreationSource, PositionStatus
    from src.domain.products.entities import ProductRecord

    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    for lid, pid in (("A1B2C3D4E5", "p0"), ("FGHJKMNPQR", "p1")):
        counted.try_claim(
            InventoryCountedProductLabel(
                id=f"c-{lid}",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                label_id=lid,
                first_product_record_id=pid,
                first_source_asset_id="asset-1",
                first_job_id="j0",
                first_position_id="pos-prior",
                created_at=now,
            )
        )
    prior = Position(
        id="pos-prior",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=1.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        job_id="j0",
        creation_source=PositionCreationSource.AUTOMATIC,
        detected_summary_json={"internal_code": "SKU1"},
    )
    prior_products = [
        ProductRecord(
            id="p0",
            position_id="pos-prior",
            sku="SKU1",
            detected_quantity=2,
            confidence=1.0,
            created_at=now,
            updated_at=now,
            label_id="A1B2C3D4E5",
            qty_source="label_explicit",
            qty_parse_status="valid_positive",
            raw_qty=2,
        ),
        ProductRecord(
            id="p1",
            position_id="pos-prior",
            sku="SKU1",
            detected_quantity=2,
            confidence=1.0,
            created_at=now,
            updated_at=now,
            label_id="FGHJKMNPQR",
            qty_source="label_explicit",
            qty_parse_status="valid_positive",
            raw_qty=2,
        ),
    ]
    job_source = MagicMock()
    job_source.list_for_job.return_value = [_link(job_id="job-1", asset_id="asset-1")]
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(
        storage_path="path/asset-1.jpg",
        storage_key="key/asset-1.jpg",
        content_type="image/jpeg",
        file_size_bytes=100,
    )
    saved_positions: list = []
    saved_products: list = []
    position_repo = MagicMock()
    product_repo = MagicMock()
    position_repo.get_by_id.return_value = prior
    product_repo.list_by_position.return_value = prior_products
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

    outcome = persister.persist(
        result=_result(_spec("A1B2C3D4E5"), _spec("FGHJKMNPQR")),
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    assert outcome.persisted is True
    assert outcome.idempotent_replay is True
    assert outcome.position_id != "pos-prior"
    assert outcome.products_persisted == 2
    assert outcome.products_skipped_duplicate == 2
    assert len(saved_positions) == 1
    assert saved_positions[0].job_id == "job-1"
    assert saved_positions[0].id == outcome.position_id
    assert len(saved_products) == 2
    assert {p.label_id for p in saved_products} == {"A1B2C3D4E5", "FGHJKMNPQR"}
    assert all(p.position_id == outcome.position_id for p in saved_products)
    coverage_repo.save.assert_called_once()
    saved_cov = coverage_repo.save.call_args.args[0]
    assert saved_cov.position_id == outcome.position_id
    assert saved_cov.source_asset_id == "asset-1"


def test_cross_job_coverage_heals_on_reprocess() -> None:
    """Existing coverage pointing at a prior-job Position must clone under this job."""
    from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
    from src.domain.positions.entities import Position, PositionCreationSource, PositionStatus
    from src.domain.products.entities import ProductRecord

    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    counted.try_claim(
        InventoryCountedProductLabel(
            id="c1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            label_id="A1B2C3D4E5",
            first_product_record_id="p0",
            first_source_asset_id="asset-1",
            first_job_id="j0",
            first_position_id="pos-prior",
            created_at=now,
        )
    )
    prior = Position(
        id="pos-prior",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=1.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        job_id="j0",
        creation_source=PositionCreationSource.AUTOMATIC,
    )
    prior_product = ProductRecord(
        id="p0",
        position_id="pos-prior",
        sku="SKU773421",
        detected_quantity=24,
        confidence=1.0,
        created_at=now,
        updated_at=now,
        label_id="A1B2C3D4E5",
        qty_source="label_explicit",
        qty_parse_status="valid_positive",
        raw_qty=24,
    )
    existing_cov = ManualImageCoverageLink(
        id="cov-old",
        job_id="job-1",
        job_source_asset_id="jsa-asset-1",
        source_asset_id="asset-1",
        position_id="pos-prior",
        aisle_id="aisle-1",
        inventory_id="inv-1",
        created_by_user_id=None,
        created_at=now,
    )
    job_source = MagicMock()
    job_source.list_for_job.return_value = [_link(job_id="job-1", asset_id="asset-1")]
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(
        storage_path="path/asset-1.jpg",
        storage_key="key/asset-1.jpg",
        content_type="image/jpeg",
        file_size_bytes=100,
    )
    saved_positions: list = []
    saved_products: list = []
    position_repo = MagicMock()
    product_repo = MagicMock()
    position_repo.get_by_id.return_value = prior
    product_repo.list_by_position.return_value = [prior_product]
    position_repo.save.side_effect = lambda p: saved_positions.append(p)
    product_repo.save.side_effect = lambda p: saved_products.append(p)
    coverage_repo = MagicMock()
    coverage_repo.get_by_job_and_asset.return_value = existing_cov
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

    outcome = persister.persist(
        result=_result(_spec("A1B2C3D4E5")),
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    assert outcome.persisted is True
    assert outcome.idempotent_replay is True
    assert outcome.position_id != "pos-prior"
    assert len(saved_positions) == 1
    assert saved_positions[0].job_id == "job-1"
    assert len(saved_products) == 1
    saved_cov = coverage_repo.save.call_args.args[0]
    assert saved_cov.id == "cov-old"
    assert saved_cov.position_id == outcome.position_id


def test_mixed_duplicate_and_new_persists_only_new() -> None:
    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    counted.try_claim(
        InventoryCountedProductLabel(
            id="c1",
            inventory_id="inv-1",
            aisle_id="aisle-1",
            label_id="A1B2C3D4E5",
            first_product_record_id="p0",
            first_source_asset_id="a0",
            first_job_id="j0",
            first_position_id="pos0",
            created_at=now,
        )
    )
    persister, saved_positions, saved_products, _, _ = _harness(counted=counted)
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


def test_same_label_other_aisle_does_not_block() -> None:
    counted = MemoryInventoryCountedProductLabelRepository()
    now = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
    counted.try_claim(
        InventoryCountedProductLabel(
            id="c1",
            inventory_id="inv-1",
            aisle_id="aisle-other",
            label_id="A1B2C3D4E5",
            first_product_record_id="p0",
            first_source_asset_id="a0",
            first_job_id="j0",
            first_position_id="pos0",
            created_at=now,
        )
    )
    persister, saved_positions, saved_products, _, _ = _harness(counted=counted)
    outcome = persister.persist(
        result=_result(_spec("A1B2C3D4E5")),
        inventory_id="inv-1",
        aisle_id="aisle-1",
    )
    assert outcome.persisted is True
    assert outcome.products_skipped_duplicate == 0
    assert outcome.products_persisted == 1
    assert len(saved_products) == 1
    assert saved_products[0].label_id == "A1B2C3D4E5"
