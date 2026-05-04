"""Integration tests for RecomputeConsolidatedCountsUseCase — v3.2.3."""

from datetime import datetime, timezone

from src.application.ports.repositories import (
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.labels.entities import RawLabel
from src.domain.labels.merge import MergeRuleEngine
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository


def _raw(
    id_: str,
    position_id: str,
    group_key: str,
    evidence_id: str,
    sku_raw: str,
    inventory_id: str = "inv1",
    aisle_id: str = "aisle1",
) -> RawLabel:
    return RawLabel(
        id=id_,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        position_id=position_id,
        evidence_id=evidence_id,
        group_key=group_key,
        provider="pipeline",
        source_type="hybrid",
        source_reference=None,
        sku_raw=sku_raw,
        sku_candidate=sku_raw,
        product_name_raw=None,
        detected_text=None,
        confidence=0.9,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


def test_recompute_duplicate_raw_same_group_does_not_inflate():
    """Duplicate raw labels (same SKU, same group) → 1 normalized → 1 final record; quantity = 1."""
    raw_repo: RawLabelRepository = MemoryRawLabelRepository()
    norm_repo: NormalizedLabelRepository = MemoryNormalizedLabelRepository()
    final_repo: FinalCountRepository = MemoryFinalCountRepository()
    product_repo: ProductRecordRepository = MemoryProductRecordRepository()
    position_repo: PositionRepository = MemoryPositionRepository()

    now = datetime.now(timezone.utc)
    pos_id = "pos-1"
    # 3 raw labels same SKU same group (same evidence)
    raw_repo.save_many(
        [
            _raw("r1", pos_id, "g1", "ev1", "SKU-X"),
            _raw("r2", pos_id, "g1", "ev1", "SKU-X"),
            _raw("r3", pos_id, "g1", "ev1", "SKU-X"),
        ]
    )
    # One product record with authoritative explicit quantity: must be preserved.
    prod = ProductRecord(
        id="prod-1",
        position_id=pos_id,
        sku="SKU-X",
        description="",
        detected_quantity=36,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        qty_source="detected",
        qty_parse_status="valid_positive",
    )
    product_repo.save(prod)
    # Position needed for projection over aisle scope.
    from src.domain.positions.entities import Position, PositionStatus

    position_repo.save(
        Position(
            id=pos_id,
            aisle_id="aisle1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={},
            corrected_summary_json=None,
        )
    )

    uc = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
    result = uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            apply_to_product_records=True,
        )
    )

    assert result.raw_count == 3
    assert result.normalized_count == 1
    assert result.final_count == 1
    assert result.product_records_updated == 0

    final_list = list(final_repo.list_for_scope("inv1", "aisle1"))
    assert len(final_list) == 1
    assert final_list[0].quantity == 1
    assert final_list[0].sku == "SKU-X"

    updated_prod = product_repo.get_by_id("prod-1")
    assert updated_prod is not None
    assert updated_prod.detected_quantity == 36
    assert updated_prod.qty_source == "detected"


def test_recompute_updates_only_non_authoritative_products():
    """
    Full-scope reconciliation:
    - multiple ProductRecords for same (position, sku) are all updated
    - unmatched ProductRecords are reset to 0
    """
    raw_repo: RawLabelRepository = MemoryRawLabelRepository()
    norm_repo: NormalizedLabelRepository = MemoryNormalizedLabelRepository()
    final_repo: FinalCountRepository = MemoryFinalCountRepository()
    product_repo: ProductRecordRepository = MemoryProductRecordRepository()
    position_repo: PositionRepository = MemoryPositionRepository()

    now = datetime.now(timezone.utc)
    pos_id = "pos-1"

    # Two raw duplicates => final quantity 1 for SKU-X
    raw_repo.save_many(
        [
            _raw("r1", pos_id, "g1", "ev1", "SKU-X"),
            _raw("r2", pos_id, "g1", "ev1", "SKU-X"),
        ]
    )

    # Explicit authoritative record must be preserved.
    product_repo.save(
        ProductRecord(
            id="p1",
            position_id=pos_id,
            sku="SKU-X",
            description="",
            detected_quantity=31,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="detected",
            qty_parse_status="valid_positive",
        )
    )
    # Non-authoritative record can be reconciled by merge artifact.
    product_repo.save(
        ProductRecord(
            id="p2",
            position_id=pos_id,
            sku="SKU-X",
            description="",
            detected_quantity=42,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="unknown",
        )
    )
    # Manual override must be preserved.
    product_repo.save(
        ProductRecord(
            id="p3",
            position_id=pos_id,
            sku="SKU-Y",
            description="",
            detected_quantity=3,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            corrected_quantity=9,
            qty_source="manual_review",
        )
    )

    from src.domain.positions.entities import Position, PositionStatus

    position_repo.save(
        Position(
            id=pos_id,
            aisle_id="aisle1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={},
            corrected_summary_json=None,
        )
    )

    uc = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
    res = uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="aisle1", apply_to_product_records=True
        )
    )
    assert res.final_count == 1

    assert product_repo.get_by_id("p1").detected_quantity == 31
    assert product_repo.get_by_id("p1").qty_source == "detected"
    assert product_repo.get_by_id("p2").detected_quantity == 1
    assert product_repo.get_by_id("p2").qty_source == "merge_inferred"
    assert product_repo.get_by_id("p3").detected_quantity == 3
    assert product_repo.get_by_id("p3").corrected_quantity == 9


def test_merge_inferred_allowed_when_explicit_missing():
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    product_repo = MemoryProductRecordRepository()
    position_repo = MemoryPositionRepository()
    now = datetime.now(timezone.utc)

    raw_repo.save_many([_raw("r1", "pos-m1", "g1", "ev1", "SKU-M")])
    product_repo.save(
        ProductRecord(
            id="p-m1",
            position_id="pos-m1",
            sku="SKU-M",
            description="",
            detected_quantity=0,
            confidence=0.9,
            created_at=now,
            updated_at=now,
            qty_source="unknown",
        )
    )

    from src.domain.positions.entities import Position, PositionStatus

    position_repo.save(
        Position(
            id="pos-m1",
            aisle_id="aisle1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={},
            corrected_summary_json=None,
        )
    )
    uc = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="aisle1", apply_to_product_records=True
        )
    )
    updated = product_repo.get_by_id("p-m1")
    assert updated is not None
    assert updated.detected_quantity == 1
    assert updated.qty_source == "merge_inferred"


def test_recompute_same_scope_idempotent():
    """Recomputing the same scope twice does not duplicate normalized/final records."""
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()
    product_repo = MemoryProductRecordRepository()
    position_repo = MemoryPositionRepository()

    raw_repo.save_many(
        [
            _raw("r1", "pos1", "g1", "ev1", "SKU-A"),
        ]
    )

    now = datetime.now(timezone.utc)
    from src.domain.positions.entities import Position, PositionStatus

    position_repo.save(
        Position(
            id="pos1",
            aisle_id="aisle1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={},
            corrected_summary_json=None,
        )
    )
    uc = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )

    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="aisle1", apply_to_product_records=False
        )
    )
    n1 = len(list(norm_repo.list_for_scope("inv1", "aisle1")))
    f1 = len(list(final_repo.list_for_scope("inv1", "aisle1")))

    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv1", aisle_id="aisle1", apply_to_product_records=False
        )
    )
    n2 = len(list(norm_repo.list_for_scope("inv1", "aisle1")))
    f2 = len(list(final_repo.list_for_scope("inv1", "aisle1")))

    assert n1 == n2
    assert f1 == f2
    assert n2 == 1
    assert f2 == 1
