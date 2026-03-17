"""Tests for BackfillLegacyAislesUseCase — v3.2.3.E4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import pytest
from src.application.ports.repositories import (
    AisleRepository,
    FinalCountRepository,
    InventoryRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.use_cases.backfill_legacy_aisles import (
    BackfillLegacyAislesCommand,
    BackfillLegacyAislesUseCase,
)
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.labels.entities import RawLabel
from src.domain.labels.merge import MergeRuleEngine
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_normalized_label_repository import MemoryNormalizedLabelRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService


def _make_recompute_uc(
    raw_repo: RawLabelRepository,
    norm_repo: NormalizedLabelRepository,
    final_repo: FinalCountRepository,
    product_repo: ProductRecordRepository,
    position_repo: PositionRepository,
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


def _raw(
    id_: str,
    position_id: str,
    group_key: str,
    evidence_id: str,
    sku_raw: str,
    inventory_id: str,
    aisle_id: str,
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


def test_backfill_one_inventory_recomputes_all_aisles() -> None:
    """Scenario A: backfill one inventory recomputes all its aisles and returns success summary."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()
    raw_repo: RawLabelRepository = MemoryRawLabelRepository()
    norm_repo: NormalizedLabelRepository = MemoryNormalizedLabelRepository()
    final_repo: FinalCountRepository = MemoryFinalCountRepository()
    product_repo: ProductRecordRepository = MemoryProductRecordRepository()
    position_repo: PositionRepository = MemoryPositionRepository()

    inv = Inventory("inv-bf-1", "Backfill WH", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)

    a1 = Aisle("aisle-bf-1", inv.id, "BF-1", AisleStatus.CREATED, now, now)
    a2 = Aisle("aisle-bf-2", inv.id, "BF-2", AisleStatus.CREATED, now, now)
    aisle_repo.save(a1)
    aisle_repo.save(a2)

    # Positions and raw labels for each aisle (1 final count each after dedupe).
    for idx, aisle in enumerate((a1, a2), start=1):
        pos_id = f"pos-{idx}"
        position_repo.save(
            Position(
                id=pos_id,
                aisle_id=aisle.id,
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
        product_repo.save(
            ProductRecord(
                id=f"prod-{idx}",
                position_id=pos_id,
                sku="SKU-X",
                description="",
                detected_quantity=5,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )
        raw_repo.save_many(
            [
                _raw(f"r{idx}-1", pos_id, "g1", "ev1", "SKU-X", inv.id, aisle.id),
                _raw(f"r{idx}-2", pos_id, "g1", "ev1", "SKU-X", inv.id, aisle.id),
            ]
        )

    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=_make_recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo),
    )
    result = uc.execute(BackfillLegacyAislesCommand(inventory_id=inv.id))

    assert result.total_aisles_scanned == 2
    assert result.total_aisles_recomputed == 2
    assert result.total_failures == 0
    # One final record per aisle.
    finals: List[object] = list(final_repo.list_for_scope(inv.id, a1.id)) + list(
        final_repo.list_for_scope(inv.id, a2.id)
    )
    assert len(finals) == 2


def test_backfill_explicit_aisle_list_only_targets_those_aisles() -> None:
    """Scenario B: explicit aisle list only recomputes the requested aisles."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()
    raw_repo: RawLabelRepository = MemoryRawLabelRepository()
    norm_repo: NormalizedLabelRepository = MemoryNormalizedLabelRepository()
    final_repo: FinalCountRepository = MemoryFinalCountRepository()
    product_repo: ProductRecordRepository = MemoryProductRecordRepository()
    position_repo: PositionRepository = MemoryPositionRepository()

    inv = Inventory("inv-bf-2", "Backfill WH 2", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)

    a1 = Aisle("aisle-exp-1", inv.id, "EXP-1", AisleStatus.CREATED, now, now)
    a2 = Aisle("aisle-exp-2", inv.id, "EXP-2", AisleStatus.CREATED, now, now)
    aisle_repo.save(a1)
    aisle_repo.save(a2)

    for aisle in (a1, a2):
        pos_id = f"pos-{aisle.id}"
        position_repo.save(
            Position(
                id=pos_id,
                aisle_id=aisle.id,
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
        product_repo.save(
            ProductRecord(
                id=f"prod-{aisle.id}",
                position_id=pos_id,
                sku="SKU-Y",
                description="",
                detected_quantity=7,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )
        raw_repo.save_many(
            [
                _raw(f"r-{aisle.id}-1", pos_id, "g1", "ev1", "SKU-Y", inv.id, aisle.id),
            ]
        )

    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=_make_recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo),
    )
    result = uc.execute(BackfillLegacyAislesCommand(aisle_ids=[a1.id]))

    assert result.total_aisles_scanned == 1
    assert result.total_aisles_recomputed == 1
    assert result.total_failures == 0
    assert len(list(final_repo.list_for_scope(inv.id, a1.id))) == 1
    assert len(list(final_repo.list_for_scope(inv.id, a2.id))) == 0


class _FailingRecompute(RecomputeConsolidatedCountsUseCase):
    """Test double that fails for a specific aisle id."""

    def __init__(self, fail_aisle_id: str) -> None:
        self._fail_aisle_id = fail_aisle_id

    def execute(self, command: RecomputeConsolidatedCountsCommand) -> RecomputeConsolidatedCountsResult:  # type: ignore[override]
        if command.aisle_id == self._fail_aisle_id:
            raise RuntimeError("synthetic failure")
        return RecomputeConsolidatedCountsResult(
            raw_count=1,
            normalized_count=1,
            final_count=1,
            product_records_updated=1,
        )


def test_backfill_one_aisle_fails_others_continue() -> None:
    """Scenario C: one aisle fails but others are processed and reported."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()

    inv = Inventory("inv-bf-3", "Backfill WH 3", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    a1 = Aisle("aisle-ok", inv.id, "OK", AisleStatus.CREATED, now, now)
    a2 = Aisle("aisle-fail", inv.id, "FAIL", AisleStatus.CREATED, now, now)
    aisle_repo.save(a1)
    aisle_repo.save(a2)

    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=_FailingRecompute(fail_aisle_id=a2.id),
    )
    result = uc.execute(BackfillLegacyAislesCommand(inventory_id=inv.id))

    assert result.total_aisles_scanned == 2
    assert result.total_failures == 1
    assert result.total_successes == 1
    by_id = {r.aisle_id: r for r in result.aisle_results}
    assert by_id[a1.id].success is True
    assert by_id[a2.id].success is False
    assert "synthetic failure" in (by_id[a2.id].error_message or "")


def test_backfill_same_scope_twice_is_idempotent() -> None:
    """Scenario D: running backfill twice on the same scope does not duplicate output."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()
    raw_repo: RawLabelRepository = MemoryRawLabelRepository()
    norm_repo: NormalizedLabelRepository = MemoryNormalizedLabelRepository()
    final_repo: FinalCountRepository = MemoryFinalCountRepository()
    product_repo: ProductRecordRepository = MemoryProductRecordRepository()
    position_repo: PositionRepository = MemoryPositionRepository()

    inv = Inventory("inv-bf-4", "Backfill WH 4", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-bf-4", inv.id, "BF-4", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)

    pos_id = "pos-bf-4"
    position_repo.save(
        Position(
            id=pos_id,
            aisle_id=aisle.id,
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
    product_repo.save(
        ProductRecord(
            id="prod-bf-4",
            position_id=pos_id,
            sku="SKU-Z",
            description="",
            detected_quantity=10,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )
    raw_repo.save_many(
        [
            _raw("r-bf-4-1", pos_id, "g1", "ev1", "SKU-Z", inv.id, aisle.id),
        ]
    )

    recompute_uc = _make_recompute_uc(raw_repo, norm_repo, final_repo, product_repo, position_repo)
    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=recompute_uc,
    )

    cmd = BackfillLegacyAislesCommand(aisle_ids=[aisle.id])
    res1 = uc.execute(cmd)
    res2 = uc.execute(cmd)

    assert res1.total_failures == 0
    assert res2.total_failures == 0
    # Idempotence: exactly one normalized and one final record for the scope.
    assert len(list(norm_repo.list_for_scope(inv.id, aisle.id))) == 1
    assert len(list(final_repo.list_for_scope(inv.id, aisle.id))) == 1


def test_backfill_invalid_explicit_aisle_reports_failure() -> None:
    """Scenario E: invalid explicit aisle id yields explicit failure result, not silent skip."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()

    inv = Inventory("inv-bf-5", "Backfill WH 5", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)

    # Use Fake recompute; it should never be called because aisle id is invalid.
    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=_FailingRecompute(fail_aisle_id="nonexistent"),
    )
    result = uc.execute(BackfillLegacyAislesCommand(aisle_ids=["missing-aisle"]))

    assert result.total_aisles_scanned == 1
    assert result.total_aisles_recomputed == 0
    assert result.total_failures == 1
    assert result.aisle_results[0].success is False
    assert result.aisle_results[0].error_message == "Aisle not found"


def test_backfill_invalid_inventory_raises_value_error() -> None:
    """Invalid inventory id must fail explicitly, not be treated as '0 aisles' success."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()

    # No inventories saved → any inventory_id is invalid.
    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=_FailingRecompute(fail_aisle_id="never-used"),
    )

    with pytest.raises(ValueError) as exc:
        uc.execute(BackfillLegacyAislesCommand(inventory_id="missing-inv"))
    assert "Inventory not found" in str(exc.value)


def test_backfill_command_rejects_ambiguous_targeting_modes() -> None:
    """Command must not allow ambiguous combinations of targeting modes."""
    now = datetime.now(timezone.utc)
    inv_repo: InventoryRepository = MemoryInventoryRepository()
    aisle_repo: AisleRepository = MemoryAisleRepository()

    inv = Inventory("inv-bf-6", "Backfill WH 6", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)

    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=_FailingRecompute(fail_aisle_id="never-used"),
    )

    # Both inventory_id and aisle_ids set → ambiguous.
    with pytest.raises(ValueError):
        uc.execute(BackfillLegacyAislesCommand(inventory_id=inv.id, aisle_ids=["a1"]))

    # inventory_id and all_aisles=True set → ambiguous.
    with pytest.raises(ValueError):
        uc.execute(BackfillLegacyAislesCommand(inventory_id=inv.id, all_aisles=True))


