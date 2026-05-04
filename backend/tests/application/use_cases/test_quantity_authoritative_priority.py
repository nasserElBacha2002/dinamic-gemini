from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.application.use_cases.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.labels.entities import RawLabel
from src.domain.labels.merge import MergeRuleEngine
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository


@dataclass
class _FixedClock:
    now_value: datetime

    def now(self) -> datetime:
        return self.now_value


def _raw(id_: str, position_id: str, sku: str) -> RawLabel:
    return RawLabel(
        id=id_,
        inventory_id="inv1",
        aisle_id="a1",
        position_id=position_id,
        evidence_id="ev1",
        group_key="g1",
        provider="pipeline",
        source_type="hybrid",
        source_reference=None,
        sku_raw=sku,
        sku_candidate=sku,
        product_name_raw=None,
        detected_text=None,
        confidence=0.9,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


def _recompute_uc(
    raw_repo, norm_repo, final_repo, product_repo, position_repo
) -> RecomputeConsolidatedCountsUseCase:
    return RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )


def test_explicit_qty_preserved_after_persist_flow() -> None:
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now))
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    recompute = _recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo)
    uc = PersistAisleResultUseCase(
        position_repo=position_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        clock=_FixedClock(now),
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        recompute_consolidated_uc=recompute,
    )
    report = {
        "entities": [
            {
                "entity_uid": "j1_e1",
                "entity_type": "PALLET",
                "pallet_id": "P1",
                "internal_code": "SKU-36",
                "product_label_quantity": 36,
                "final_quantity": 36,
                "count_status": "COUNTED",
                "confidence": 0.92,
                "evidence_path": "evidence/p1.jpg",
            }
        ]
    }
    uc.execute(
        PersistAisleResultCommand(
            aisle_id="a1", job_id="j1", report=report, run_dir=Path("output/j1/run")
        )
    )
    positions = list(position_repo.list_by_aisle("a1"))
    assert len(positions) == 1
    products = list(product_repo.list_by_position(positions[0].id))
    assert len(products) == 1
    assert products[0].detected_quantity == 36
    assert products[0].qty_source == "label_explicit"


def test_explicit_qty_not_overwritten_by_recompute() -> None:
    now = datetime.now(timezone.utc)
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    product_repo = MemoryProductRecordRepository()
    position_repo = MemoryPositionRepository()
    position_repo.save(
        Position("p1", "a1", PositionStatus.DETECTED, 0.9, False, None, now, now, {}, None)
    )
    product_repo.save(
        ProductRecord(
            id="pr1",
            position_id="p1",
            sku="SKU-36",
            description="",
            detected_quantity=36,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="label_explicit",
            qty_parse_status="valid_positive",
        )
    )
    raw_repo.save_many([_raw("r1", "p1", "SKU-36")])
    uc = _recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo)
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="a1", apply_to_product_records=True
        )
    )
    saved = product_repo.get_by_id("pr1")
    assert saved is not None
    assert saved.detected_quantity == 36
    assert saved.qty_source == "label_explicit"


def test_merge_inferred_allowed_when_explicit_missing() -> None:
    now = datetime.now(timezone.utc)
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    product_repo = MemoryProductRecordRepository()
    position_repo = MemoryPositionRepository()
    position_repo.save(
        Position("p2", "a1", PositionStatus.DETECTED, 0.9, False, None, now, now, {}, None)
    )
    product_repo.save(
        ProductRecord(
            id="pr2",
            position_id="p2",
            sku="SKU-X",
            description="",
            detected_quantity=0,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="unknown",
        )
    )
    raw_repo.save_many([_raw("r2", "p2", "SKU-X")])
    uc = _recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo)
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="a1", apply_to_product_records=True
        )
    )
    saved = product_repo.get_by_id("pr2")
    assert saved is not None
    assert saved.detected_quantity == 1
    assert saved.qty_source == "merge_inferred"


def test_manual_override_has_priority_over_merge() -> None:
    now = datetime.now(timezone.utc)
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    product_repo = MemoryProductRecordRepository()
    position_repo = MemoryPositionRepository()
    position_repo.save(
        Position("p3", "a1", PositionStatus.DETECTED, 0.9, False, None, now, now, {}, None)
    )
    product_repo.save(
        ProductRecord(
            id="pr3",
            position_id="p3",
            sku="SKU-Y",
            description="",
            detected_quantity=5,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            corrected_quantity=8,
            qty_source="manual_review",
        )
    )
    raw_repo.save_many([_raw("r3", "p3", "SKU-Y")])
    uc = _recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo)
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="a1", apply_to_product_records=True
        )
    )
    saved = product_repo.get_by_id("pr3")
    assert saved is not None
    assert saved.detected_quantity == 5
    assert saved.corrected_quantity == 8
    assert saved.qty_source == "manual_review"


def test_qty_source_transition_is_valid() -> None:
    now = datetime.now(timezone.utc)
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    product_repo = MemoryProductRecordRepository()
    position_repo = MemoryPositionRepository()
    position_repo.save(
        Position("p4", "a1", PositionStatus.DETECTED, 0.9, False, None, now, now, {}, None)
    )
    product_repo.save(
        ProductRecord(
            id="pr4a",
            position_id="p4",
            sku="SKU-E",
            description="",
            detected_quantity=31,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="label_explicit",
            qty_parse_status="valid_positive",
        )
    )
    product_repo.save(
        ProductRecord(
            id="pr4b",
            position_id="p4",
            sku="SKU-M",
            description="",
            detected_quantity=0,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="unknown",
        )
    )
    raw_repo.save_many([_raw("r4a", "p4", "SKU-E"), _raw("r4b", "p4", "SKU-M")])
    uc = _recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo)
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="a1", apply_to_product_records=True
        )
    )
    explicit = product_repo.get_by_id("pr4a")
    merged = product_repo.get_by_id("pr4b")
    assert explicit is not None and merged is not None
    assert explicit.qty_source == "label_explicit"
    assert merged.qty_source == "merge_inferred"
