from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from src.application.errors import PositionResultContextMismatchError
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction, ReviewActionType
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_review_action_repository import (
    MemoryReviewActionRepository,
)


def test_get_position_detail_uses_consolidated_representative_for_group_member() -> None:
    now = datetime.now(timezone.utc)
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()

    inventory_repo.save(Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-01", AisleStatus.CREATED, now, now))

    representative = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.CORRECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-NEW", "final_quantity": 1},
    )
    member = Position(
        id="pos-2",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.85,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-NEW", "final_quantity": 3},
    )
    position_repo.save(representative)
    position_repo.save(member)

    product_repo.save(
        ProductRecord(
            id="prod-1",
            position_id="pos-1",
            sku="SKU-NEW",
            description="Merged product",
            detected_quantity=4,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            corrected_quantity=None,
            qty_source="consolidated",
            qty_inference_reason=None,
            raw_qty=4,
            qty_parse_status="valid_positive",
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-2",
            position_id="pos-2",
            sku="SKU-OLD",
            description="Old member",
            detected_quantity=1,
            confidence=0.85,
            created_at=now,
            updated_at=now,
            corrected_quantity=None,
            qty_source="inferred",
            qty_inference_reason=None,
            raw_qty=1,
            qty_parse_status="valid_positive",
        )
    )
    evidence_repo.save(
        Evidence(
            id="ev-1",
            entity_type="position",
            entity_id="pos-1",
            type=EvidenceType.POSITION_CROP,
            storage_path="/tmp/ev-1.jpg",
            source_asset_id="asset-1",
            is_primary=True,
            frame_index=None,
            timestamp_ms=None,
            bbox_json=None,
            quality_score=None,
        )
    )
    review_repo.save(
        ReviewAction(
            id="ra-1",
            position_id="pos-1",
            action_type=ReviewActionType.UPDATE_SKU,
            before_json={"sku": "SKU-OLD"},
            after_json={"sku": "SKU-NEW"},
            created_at=now,
        )
    )

    job_repo = MemoryJobRepository()
    use_case = GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=ResultContextResolver(job_repo, position_repo),
        positions_aisle_raw_cap=2000,
    )

    result = use_case.execute("inv-1", "aisle-1", "pos-2")

    assert result.position.id == "pos-1"
    assert result.run_context.result_context_source == "legacy"
    assert isinstance(result.position.detected_summary_json, dict)
    assert result.position.detected_summary_json["internal_code"] == "SKU-NEW"
    assert result.position.detected_summary_json["final_quantity"] == 4
    assert result.position.detected_summary_json["aggregated_from_ids"] == ["pos-1", "pos-2"]
    assert [product.id for product in result.products] == ["prod-1"]
    assert [evidence.id for evidence in result.evidences] == ["ev-1"]
    assert [review.id for review in result.review_actions] == ["ra-1"]


def test_get_position_detail_exact_position_returns_member_row() -> None:
    now = datetime.now(timezone.utc)
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()

    inventory_repo.save(Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-01", AisleStatus.CREATED, now, now))

    representative = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.CORRECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-NEW", "final_quantity": 1},
    )
    member = Position(
        id="pos-2",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.85,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-NEW", "final_quantity": 3},
    )
    position_repo.save(representative)
    position_repo.save(member)

    product_repo.save(
        ProductRecord(
            id="prod-1",
            position_id="pos-1",
            sku="SKU-NEW",
            description="Merged product",
            detected_quantity=4,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            corrected_quantity=None,
            qty_source="consolidated",
            qty_inference_reason=None,
            raw_qty=4,
            qty_parse_status="valid_positive",
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-2",
            position_id="pos-2",
            sku="SKU-OLD",
            description="Old member",
            detected_quantity=1,
            confidence=0.85,
            created_at=now,
            updated_at=now,
            corrected_quantity=None,
            qty_source="inferred",
            qty_inference_reason=None,
            raw_qty=1,
            qty_parse_status="valid_positive",
        )
    )
    evidence_repo.save(
        Evidence(
            id="ev-1",
            entity_type="position",
            entity_id="pos-1",
            type=EvidenceType.POSITION_CROP,
            storage_path="/tmp/ev-1.jpg",
            source_asset_id="asset-1",
            is_primary=True,
            frame_index=None,
            timestamp_ms=None,
            bbox_json=None,
            quality_score=None,
        )
    )
    evidence_repo.save(
        Evidence(
            id="ev-2",
            entity_type="position",
            entity_id="pos-2",
            type=EvidenceType.POSITION_CROP,
            storage_path="/tmp/ev-2.jpg",
            source_asset_id="asset-2",
            is_primary=True,
            frame_index=3,
            timestamp_ms=None,
            bbox_json=None,
            quality_score=None,
        )
    )

    job_repo = MemoryJobRepository()
    use_case = GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=ResultContextResolver(job_repo, position_repo),
        positions_aisle_raw_cap=2000,
    )

    result = use_case.execute("inv-1", "aisle-1", "pos-2", exact_position=True)

    assert result.position.id == "pos-2"
    assert [product.id for product in result.products] == ["prod-2"]
    assert [evidence.id for evidence in result.evidences] == ["ev-2"]
    assert result.evidences[0].frame_index == 3


def test_get_position_detail_falls_back_to_raw_position_when_representative_cannot_be_rebuilt(
    caplog,
) -> None:
    now = datetime.now(timezone.utc)
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()

    inventory_repo.save(Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-01", AisleStatus.CREATED, now, now))

    representative = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.CORRECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-NEW", "final_quantity": 1},
    )
    member = Position(
        id="pos-2",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.85,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-NEW", "final_quantity": 3},
    )
    position_repo.save(representative)
    position_repo.save(member)
    product_repo.save(
        ProductRecord(
            id="prod-2",
            position_id="pos-2",
            sku="SKU-OLD",
            description="Old member",
            detected_quantity=1,
            confidence=0.85,
            created_at=now,
            updated_at=now,
            corrected_quantity=None,
            qty_source="inferred",
            qty_inference_reason=None,
            raw_qty=1,
            qty_parse_status="valid_positive",
        )
    )

    job_repo = MemoryJobRepository()
    use_case = GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=ResultContextResolver(job_repo, position_repo),
        positions_aisle_raw_cap=1,
    )

    with caplog.at_level(logging.WARNING):
        result = use_case.execute("inv-1", "aisle-1", "pos-2")

    assert result.position.id == "pos-2"
    assert [product.id for product in result.products] == ["prod-2"]
    assert "position_detail representative fallback" in caplog.text


def test_get_position_detail_explicit_job_matches_job_scoped_position() -> None:
    now = datetime.now(timezone.utc)
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()
    job_repo = MemoryJobRepository()

    inventory_repo.save(Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-01", AisleStatus.CREATED, now, now))
    job_repo.save(
        Job(
            id="job-x",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    position_repo.save(
        Position(
            id="pos-j",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job-x",
        )
    )

    use_case = GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=ResultContextResolver(job_repo, position_repo),
        positions_aisle_raw_cap=2000,
    )
    result = use_case.execute("inv-1", "aisle-1", "pos-j", explicit_job_id="job-x")
    assert result.position.id == "pos-j"
    assert result.run_context.result_context_source == "explicit"
    assert result.run_context.resolved_job_id == "job-x"


def test_get_position_detail_raises_when_legacy_context_excludes_job_scoped_position() -> None:
    now = datetime.now(timezone.utc)
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()
    job_repo = MemoryJobRepository()

    inventory_repo.save(Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A-01", AisleStatus.CREATED, now, now))
    position_repo.save(
        Position(
            id="pos-j",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            job_id="job-x",
        )
    )

    use_case = GetPositionDetailUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=ResultContextResolver(job_repo, position_repo),
        positions_aisle_raw_cap=2000,
    )
    with pytest.raises(PositionResultContextMismatchError):
        use_case.execute("inv-1", "aisle-1", "pos-j")
