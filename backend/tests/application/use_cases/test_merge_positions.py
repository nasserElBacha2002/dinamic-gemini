"""Tests for operator position merge (preview + confirm)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    InventoryNotFoundError,
    PositionMergeConflictError,
    PositionMergeStalePreviewError,
    PositionMergeValidationError,
    PositionNotFoundError,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.positions.merge_positions import (
    ConfirmMergePositionsUseCase,
    PreviewMergePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionReviewResolution, PositionStatus
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction, ReviewActionType
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubReviewRepo:
    def __init__(self) -> None:
        self._actions: list[ReviewAction] = []

    def save(self, review: ReviewAction) -> None:
        self._actions.append(review)

    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]:
        return [a for a in self._actions if a.position_id == position_id]


def _platform() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="admin",
        client_id=None,
        roles=frozenset({"platform_admin"}),
        is_platform=True,
    )


def _seed(
    *,
    qtys: Sequence[int] = (4, 3, 2),
    sku: str = "SKU-100",
    position_codes: Sequence[str | None] | None = None,
    deleted_inventory: bool = False,
) -> tuple:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    inv = Inventory(
        "inv-1",
        "WH",
        InventoryStatus.DRAFT,
        now,
        now,
        client_id="client-a",
        deleted_at=now if deleted_inventory else None,
        deleted_by="admin" if deleted_inventory else None,
    )
    aisle = Aisle("aisle-1", "inv-1", "A01", AisleStatus.PROCESSED, now, now)
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(inv)
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(aisle)
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    review_repo = StubReviewRepo()
    codes = position_codes or (None,) * len(qtys)
    ids: list[str] = []
    for i, qty in enumerate(qtys):
        pid = f"pos-{i + 1}"
        ids.append(pid)
        created = now + timedelta(seconds=i)
        position_repo.save(
            Position(
                id=pid,
                aisle_id="aisle-1",
                status=PositionStatus.DETECTED,
                confidence=0.9,
                needs_review=True,
                primary_evidence_id=None,
                created_at=created,
                updated_at=created,
                detected_summary_json={
                    "internal_code": sku,
                    "final_quantity": qty,
                    "source_image_id": f"img-{i + 1}",
                    "source_image_original_filename": f"IMG_{i + 1:03d}.jpg",
                    **({"pallet_id": codes[i]} if i < len(codes) and codes[i] else {}),
                },
                corrected_position_code=codes[i] if i < len(codes) else None,
            )
        )
        product_repo.save(
            ProductRecord(
                id=f"prod-{i + 1}",
                position_id=pid,
                sku=sku,
                detected_quantity=qty,
                confidence=0.9,
                created_at=created,
                updated_at=created,
                description="Widget",
            )
        )
    clock = FixedClock(now + timedelta(hours=1))
    access = InventoryAccessPolicy(inv_repo, aisle_repo=aisle_repo)
    sync = AisleReviewLifecycleSync(
        aisle_repo,
        position_repo,
        clock,
        InventoryStatusReconciler(inv_repo, aisle_repo, clock),
    )
    preview = PreviewMergePositionsUseCase(
        access_policy=access,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
    )
    confirm = ConfirmMergePositionsUseCase(
        access_policy=access,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=sync,
        uow_factory=None,
    )
    return ids, preview, confirm, position_repo, product_repo, review_repo, inv_repo


def test_preview_happy_path_sums_quantities() -> None:
    ids, preview, _, *_ = _seed()
    result = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    assert result.can_merge is True
    assert result.merged_quantity == 9
    assert result.survivor_id == "pos-1"
    assert result.source_count == 3
    assert result.preview_token
    assert not result.conflicts


def test_confirm_merges_and_preserves_sources() -> None:
    ids, preview, confirm, position_repo, product_repo, review_repo, _ = _seed()
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    out = confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    assert out.survivor_id == "pos-1"
    assert out.merged_quantity == 9
    survivor = position_repo.get_by_id("pos-1")
    assert survivor is not None
    assert survivor.detected_summary_json is not None
    assert survivor.detected_summary_json.get("final_quantity") == 9
    assert survivor.detected_summary_json.get("aggregated_from_ids") == ids
    src2 = position_repo.get_by_id("pos-2")
    src3 = position_repo.get_by_id("pos-3")
    assert src2 is not None and src2.merged_into_position_id == "pos-1"
    assert src3 is not None and src3.merged_into_position_id == "pos-1"
    assert src2.review_resolution == PositionReviewResolution.MERGED
    assert src2.status != PositionStatus.DELETED
    listed = position_repo.list_by_aisle("aisle-1", page_size=50)
    assert [p.id for p in listed] == ["pos-1"]
    prod = product_repo.get_by_id("prod-1")
    assert prod is not None
    assert prod.corrected_quantity == 9
    actions = review_repo.list_by_position("pos-1")
    assert len(actions) == 1
    assert actions[0].action_type == ReviewActionType.MERGE_POSITIONS


def test_confirm_idempotent_retry() -> None:
    ids, preview, confirm, *_ = _seed(qtys=(2, 2))
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    again = confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    assert again.already_merged is True
    assert again.survivor_id == "pos-1"


def test_stale_preview_rejected() -> None:
    ids, preview, confirm, position_repo, *_ = _seed(qtys=(1, 1))
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    p = position_repo.get_by_id("pos-1")
    assert p is not None
    p.updated_at = p.updated_at + timedelta(seconds=5)
    position_repo.save(p)
    with pytest.raises(PositionMergeStalePreviewError):
        confirm.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=ids,
            preview_token=pre.preview_token,
            principal=_platform(),
        )


def test_sku_mismatch_blocks() -> None:
    ids, preview, confirm, position_repo, product_repo, review_repo, inv_repo = _seed(qtys=(1, 1))
    # Change second product SKU
    prod = product_repo.get_by_id("prod-2")
    assert prod is not None
    prod.sku = "OTHER"
    product_repo.save(prod)
    pos = position_repo.get_by_id("pos-2")
    assert pos is not None
    assert isinstance(pos.detected_summary_json, dict)
    pos.detected_summary_json = {**pos.detected_summary_json, "internal_code": "OTHER"}
    position_repo.save(pos)
    result = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    assert result.can_merge is False
    assert any(c.code == "sku_mismatch" for c in result.conflicts)
    with pytest.raises(PositionMergeConflictError):
        confirm.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=ids,
            preview_token=result.preview_token,
            principal=_platform(),
        )


def test_position_code_mismatch_blocks() -> None:
    ids, preview, *_ = _seed(qtys=(1, 1), position_codes=("A01", "A02"))
    result = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    assert result.can_merge is False
    assert any(c.code == "position_code_mismatch" for c in result.conflicts)


def test_validation_single_id() -> None:
    ids, preview, *_ = _seed(qtys=(1, 1))
    with pytest.raises(PositionMergeValidationError):
        preview.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=[ids[0]],
            principal=_platform(),
        )


def test_validation_duplicate_ids() -> None:
    ids, preview, *_ = _seed(qtys=(1, 1))
    with pytest.raises(PositionMergeValidationError):
        preview.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=[ids[0], ids[0]],
            principal=_platform(),
        )


def test_missing_id() -> None:
    ids, preview, *_ = _seed(qtys=(1, 1))
    with pytest.raises(PositionNotFoundError):
        preview.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=[ids[0], "missing"],
            principal=_platform(),
        )


def test_deleted_inventory_blocks() -> None:
    ids, preview, *_ = _seed(qtys=(1, 1), deleted_inventory=True)
    with pytest.raises(InventoryNotFoundError):
        preview.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=ids,
            principal=_platform(),
        )


def test_already_merged_source_blocks_new_merge() -> None:
    ids, preview, confirm, position_repo, *_ = _seed(qtys=(1, 1, 1))
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids[:2],
        principal=_platform(),
    )
    confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids[:2],
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    result = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=[ids[0], ids[2]],
        principal=_platform(),
    )
    # survivor pos-1 still active; pos-2 merged. Merging pos-1 with pos-3 should work.
    assert result.can_merge is True
    blocked = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=[ids[1], ids[2]],
        principal=_platform(),
    )
    assert blocked.can_merge is False
    assert any(c.code == "already_merged" for c in blocked.conflicts)


def test_multi_product_position_blocks_merge() -> None:
    ids, preview, _, _, product_repo, *_ = _seed(qtys=(1, 1))
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    product_repo.save(
        ProductRecord(
            id="prod-extra",
            position_id=ids[0],
            sku="OTHER-SKU",
            detected_quantity=1,
            confidence=0.5,
            created_at=now + timedelta(seconds=10),
            updated_at=now + timedelta(seconds=10),
        )
    )
    result = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    assert result.can_merge is False
    assert any(c.code == "ambiguous_position_products" for c in result.conflicts)


def test_stale_when_product_quantity_changes() -> None:
    ids, preview, confirm, _, product_repo, *_ = _seed(qtys=(4, 3))
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    assert pre.merged_quantity == 7
    prod = product_repo.get_by_id("prod-2")
    assert prod is not None
    prod.corrected_quantity = 5
    prod.updated_at = prod.updated_at + timedelta(seconds=1)
    product_repo.save(prod)
    with pytest.raises(PositionMergeStalePreviewError):
        confirm.execute(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            result_ids=ids,
            preview_token=pre.preview_token,
            principal=_platform(),
        )


def test_resolve_product_record_ids_as_result_ids() -> None:
    ids, preview, confirm, position_repo, *_ = _seed(qtys=(2, 2))
    product_ids = ["prod-1", "prod-2"]
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=product_ids,
        principal=_platform(),
    )
    assert pre.can_merge is True
    out = confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=product_ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    assert out.survivor_id == ids[0]
    merged = position_repo.get_by_id(ids[1])
    assert merged is not None
    assert merged.merged_into_position_id == ids[0]


def test_review_action_sets_user_id() -> None:
    ids, preview, confirm, _, _, review_repo, _ = _seed(qtys=(1, 1))
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    actions = review_repo.list_by_position(ids[0])
    assert len(actions) == 1
    assert actions[0].user_id == "admin"
    assert actions[0].action_type == ReviewActionType.MERGE_POSITIONS


def test_list_by_aisles_hides_merged_sources_list_all_keeps_them() -> None:
    ids, preview, confirm, position_repo, _, _, _ = _seed(qtys=(2, 2))
    pre = preview.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        principal=_platform(),
    )
    confirm.execute(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        result_ids=ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    operational = list(position_repo.list_by_aisles(["aisle-1"]))
    assert len(operational) == 1
    assert operational[0].id == ids[0]
    historical = list(position_repo.list_all_by_aisles(["aisle-1"]))
    assert len(historical) == 2
    assert {p.id for p in historical} == set(ids)
