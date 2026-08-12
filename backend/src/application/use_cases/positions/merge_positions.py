"""Preview + confirm use cases for operator-driven position merge."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    PositionMergeConflictError,
    PositionMergeStalePreviewError,
    PositionMergeValidationError,
    PositionNotFoundError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.position_operator_merge import (
    MergeConflict,
    MergePlan,
    MergeSourceSnapshot,
    MergeWarning,
    apply_survivor_summary,
    build_preview_token,
    find_duplicate_ids,
    normalize_result_ids,
    plan_position_merge,
)
from src.application.use_cases.shared.review_validation import storage_job_id_for_review_audit
from src.domain.positions.entities import Position, PositionReviewResolution
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction, ReviewActionType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionMergePreviewResult:
    can_merge: bool
    preview_token: str
    sources: tuple[MergeSourceSnapshot, ...]
    conflicts: tuple[MergeConflict, ...]
    warnings: tuple[MergeWarning, ...]
    survivor_id: str | None
    merged_quantity: int | None
    merged_sku: str | None
    merged_internal_code: str | None
    merged_position_code: str | None
    merged_description: str | None
    source_count: int
    image_count: int
    product_identity: str | None


@dataclass(frozen=True)
class PositionMergeConfirmResult:
    survivor_id: str
    merged_quantity: int
    source_ids: tuple[str, ...]
    already_merged: bool = False


class PositionMergeRepositories(Protocol):
    position_repo: PositionRepository
    product_record_repo: ProductRecordRepository
    review_repo: ReviewActionRepository


class PositionMergeUnitOfWork(Protocol):
    repositories: PositionMergeRepositories

    def bind_lifecycle_scope(self, *, inventory_id: str, aisle_id: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


PositionMergeUowFactory = Callable[[], AbstractContextManager[PositionMergeUnitOfWork]]


def _plan_to_preview(plan: MergePlan) -> PositionMergePreviewResult:
    return PositionMergePreviewResult(
        can_merge=plan.can_merge,
        preview_token=plan.preview_token,
        sources=tuple(plan.sources),
        conflicts=tuple(plan.conflicts),
        warnings=tuple(plan.warnings),
        survivor_id=plan.survivor_id,
        merged_quantity=plan.merged_quantity,
        merged_sku=plan.merged_sku,
        merged_internal_code=plan.merged_internal_code,
        merged_position_code=plan.merged_position_code,
        merged_description=plan.merged_description,
        source_count=plan.source_count,
        image_count=plan.image_count,
        product_identity=plan.product_identity,
    )


def _validate_request_ids(result_ids: Sequence[str]) -> list[str]:
    normalized = normalize_result_ids(result_ids)
    dupes = find_duplicate_ids(result_ids)
    if dupes:
        raise PositionMergeValidationError(
            f"Duplicate result_ids are not allowed: {', '.join(dupes)}"
        )
    if len(normalized) < 2:
        raise PositionMergeValidationError("At least two result_ids are required")
    return normalized


def _resolve_position_ids(
    raw_ids: Sequence[str],
    *,
    aisle_id: str,
    position_repo: PositionRepository,
    product_record_repo: ProductRecordRepository,
) -> list[str]:
    """Map result_ids (position id or product_record id) → unique position ids in aisle."""
    ordered: list[str] = []
    seen: set[str] = set()
    missing: list[str] = []
    for raw in raw_ids:
        position = position_repo.get_by_id(raw)
        if position is not None and position.aisle_id == aisle_id:
            if position.id not in seen:
                seen.add(position.id)
                ordered.append(position.id)
            continue
        product = product_record_repo.get_by_id(raw)
        if product is not None:
            parent = position_repo.get_by_id(product.position_id)
            if parent is not None and parent.aisle_id == aisle_id:
                if parent.id not in seen:
                    seen.add(parent.id)
                    ordered.append(parent.id)
                continue
        missing.append(raw)
    if missing:
        raise PositionNotFoundError(
            f"Position not found: {missing[0]}"
            if len(missing) == 1
            else f"Positions not found: {', '.join(missing)}"
        )
    if len(ordered) < 2:
        raise PositionMergeValidationError(
            "At least two distinct positions are required after resolving result_ids"
        )
    return ordered


def _products_by_position_ids(
    position_ids: Sequence[str],
    product_record_repo: ProductRecordRepository,
) -> dict[str, list[ProductRecord]]:
    by_pos: dict[str, list[ProductRecord]] = {pid: [] for pid in position_ids}
    for product in product_record_repo.list_by_position_ids(list(position_ids)):
        by_pos.setdefault(product.position_id, []).append(product)
    return by_pos


def _flat_products(by_pos: Mapping[str, Sequence[ProductRecord]]) -> list[ProductRecord]:
    return [pr for products in by_pos.values() for pr in products]


def _idempotent_confirm_result(
    positions: Sequence[Position],
    *,
    ids: Sequence[str],
    position_repo: PositionRepository,
) -> PositionMergeConfirmResult | None:
    active = [p for p in positions if not p.is_merged_source]
    merged_sources = [p for p in positions if p.is_merged_source]
    if (
        len(active) == 1
        and merged_sources
        and all((p.merged_into_position_id or "").strip() == active[0].id for p in merged_sources)
    ):
        survivor = active[0]
        qty = 0
        summary = (
            survivor.detected_summary_json if isinstance(survivor.detected_summary_json, dict) else {}
        )
        raw_q = summary.get("final_quantity")
        if isinstance(raw_q, int):
            qty = max(0, raw_q)
        return PositionMergeConfirmResult(
            survivor_id=survivor.id,
            merged_quantity=qty,
            source_ids=tuple(ids),
            already_merged=True,
        )
    if len(positions) >= 2 and all(p.is_merged_source for p in positions):
        targets = {(p.merged_into_position_id or "").strip() for p in positions}
        if len(targets) == 1:
            survivor_id = next(iter(targets))
            loaded_survivor = position_repo.get_by_id(survivor_id)
            if loaded_survivor is not None and not loaded_survivor.is_merged_source:
                survivor = loaded_survivor
                qty = 0
                summary = (
                    survivor.detected_summary_json
                    if isinstance(survivor.detected_summary_json, dict)
                    else {}
                )
                raw_q = summary.get("final_quantity")
                if isinstance(raw_q, int):
                    qty = max(0, raw_q)
                return PositionMergeConfirmResult(
                    survivor_id=survivor_id,
                    merged_quantity=qty,
                    source_ids=tuple(ids),
                    already_merged=True,
                )
    return None


class PreviewMergePositionsUseCase:
    def __init__(
        self,
        *,
        access_policy: InventoryAccessPolicy,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
    ) -> None:
        self._access_policy = access_policy
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo

    def execute(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        result_ids: Sequence[str],
        principal: AccessPrincipal,
    ) -> PositionMergePreviewResult:
        self._access_policy.require_aisle(inventory_id, aisle_id, principal)
        normalized = _validate_request_ids(result_ids)
        position_ids = _resolve_position_ids(
            normalized,
            aisle_id=aisle_id,
            position_repo=self._position_repo,
            product_record_repo=self._product_record_repo,
        )
        loaded = self._position_repo.get_by_ids(position_ids)
        by_id = {p.id: p for p in loaded}
        missing = [pid for pid in position_ids if pid not in by_id]
        if missing:
            raise PositionNotFoundError(f"Position not found: {missing[0]}")
        positions = [by_id[pid] for pid in position_ids]
        products_by_position = _products_by_position_ids(position_ids, self._product_record_repo)
        plan = plan_position_merge(
            positions,
            products_by_position=products_by_position,
            aisle_id=aisle_id,
        )
        return _plan_to_preview(plan)


class ConfirmMergePositionsUseCase:
    def __init__(
        self,
        *,
        access_policy: InventoryAccessPolicy,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        review_repo: ReviewActionRepository,
        clock: Clock,
        aisle_review_sync: AisleReviewLifecycleSync,
        uow_factory: PositionMergeUowFactory | None = None,
    ) -> None:
        self._access_policy = access_policy
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._review_repo = review_repo
        self._clock = clock
        self._aisle_review_sync = aisle_review_sync
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        result_ids: Sequence[str],
        preview_token: str,
        principal: AccessPrincipal,
    ) -> PositionMergeConfirmResult:
        token = str(preview_token or "").strip()
        if not token:
            raise PositionMergeValidationError("preview_token is required")
        self._access_policy.require_aisle(inventory_id, aisle_id, principal)
        normalized = _validate_request_ids(result_ids)

        if self._uow_factory is not None:
            with self._uow_factory() as uow:
                uow.bind_lifecycle_scope(inventory_id=inventory_id, aisle_id=aisle_id)
                result = self._confirm_inside_transaction(
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    raw_ids=normalized,
                    preview_token=token,
                    principal=principal,
                    position_repo=uow.repositories.position_repo,
                    product_record_repo=uow.repositories.product_record_repo,
                    review_repo=uow.repositories.review_repo,
                )
                uow.commit()
                return result

        result = self._confirm_inside_transaction(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            raw_ids=normalized,
            preview_token=token,
            principal=principal,
            position_repo=self._position_repo,
            product_record_repo=self._product_record_repo,
            review_repo=self._review_repo,
        )
        self._aisle_review_sync.after_review_mutation(inventory_id, aisle_id)
        return result

    def _confirm_inside_transaction(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        raw_ids: Sequence[str],
        preview_token: str,
        principal: AccessPrincipal,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        review_repo: ReviewActionRepository,
    ) -> PositionMergeConfirmResult:
        # Resolve ids using transactional repos (product→position mapping stays consistent).
        position_ids = _resolve_position_ids(
            raw_ids,
            aisle_id=aisle_id,
            position_repo=position_repo,
            product_record_repo=product_record_repo,
        )
        # Lock selected rows (SQL UPDLOCK); memory = plain batch get.
        loaded = position_repo.get_by_ids_for_update(position_ids)
        by_id = {p.id: p for p in loaded}
        missing = [pid for pid in position_ids if pid not in by_id]
        if missing:
            raise PositionNotFoundError(f"Position not found: {missing[0]}")
        for pid in position_ids:
            if by_id[pid].aisle_id != aisle_id:
                raise PositionNotFoundError(f"Position {pid} does not belong to aisle {aisle_id}")
        positions = [by_id[pid] for pid in position_ids]
        products_by_position = _products_by_position_ids(position_ids, product_record_repo)

        idempotent = _idempotent_confirm_result(
            positions, ids=position_ids, position_repo=position_repo
        )
        if idempotent is not None:
            logger.info(
                "event=position_merge_idempotent inventory_id=%s aisle_id=%s survivor_id=%s sources=%s",
                inventory_id,
                aisle_id,
                idempotent.survivor_id,
                ",".join(position_ids),
            )
            return idempotent

        current_token = build_preview_token(positions, _flat_products(products_by_position))
        if current_token != preview_token:
            raise PositionMergeStalePreviewError(
                "Los registros cambiaron desde que se generó la previsualización. Revisá nuevamente la fusión."
            )

        plan = plan_position_merge(
            positions,
            products_by_position=products_by_position,
            aisle_id=aisle_id,
        )
        if not plan.can_merge or plan.survivor_id is None or plan.merged_quantity is None:
            detail = plan.conflicts[0].message if plan.conflicts else "Merge is not allowed"
            raise PositionMergeConflictError(detail)

        return self._apply_merge(
            positions=positions,
            products_by_position=products_by_position,
            plan=plan,
            now=self._clock.now(),
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            review_repo=review_repo,
            actor_user_id=principal.actor_id,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
        )

    def _apply_merge(
        self,
        *,
        positions: Sequence[Position],
        products_by_position: Mapping[str, Sequence[ProductRecord]],
        plan: MergePlan,
        now: datetime,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        review_repo: ReviewActionRepository,
        actor_user_id: str | None,
        inventory_id: str,
        aisle_id: str,
    ) -> PositionMergeConfirmResult:
        assert plan.survivor_id is not None
        assert plan.merged_quantity is not None
        survivor_id = plan.survivor_id
        by_id = {p.id: p for p in positions}
        survivor = by_id[survivor_id]
        if survivor_id == survivor.merged_into_position_id:
            raise PositionMergeConflictError("Un resultado no puede fusionarse consigo mismo.")
        sources = [p for p in positions if p.id != survivor_id]
        source_ids = [survivor_id, *[p.id for p in sources]]

        before_sources = [
            {
                "position_id": s.position_id,
                "sku": s.sku,
                "quantity": s.quantity,
                "position_code": s.declared_position_code or s.position_code,
                "updated_at": s.updated_at.isoformat(),
            }
            for s in plan.sources
        ]

        survivor.detected_summary_json = apply_survivor_summary(
            survivor,
            source_ids=source_ids,
            merged_quantity=plan.merged_quantity,
        )
        survivor.updated_at = now
        survivor.needs_review = False
        position_repo.save(survivor)

        # Multi-product positions are blocked in plan; sole product is the only safe update.
        survivor_products = list(products_by_position.get(survivor_id) or ())
        if len(survivor_products) == 1:
            primary = survivor_products[0]
            primary.corrected_quantity = int(plan.merged_quantity)
            primary.qty_source = "manual_review"
            primary.updated_at = now
            product_record_repo.save(primary)
        elif len(survivor_products) > 1:
            raise PositionMergeConflictError(
                "La posición sobreviviente tiene múltiples ProductRecords; fusión bloqueada."
            )

        for source in sources:
            if source.id == survivor_id:
                raise PositionMergeConflictError("Un resultado no puede fusionarse consigo mismo.")
            source.merged_into_position_id = survivor_id
            source.merged_at = now
            source.review_resolution = PositionReviewResolution.MERGED
            source.needs_review = False
            source.updated_at = now
            position_repo.save(source)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=survivor_id,
            action_type=ReviewActionType.MERGE_POSITIONS,
            before_json={"sources": before_sources},
            after_json={
                "survivor_id": survivor_id,
                "source_ids": source_ids,
                "merged_quantity": plan.merged_quantity,
                "product_identity": plan.product_identity,
                "merged_position_code": plan.merged_position_code,
            },
            created_at=now,
            user_id=actor_user_id,
            job_id=storage_job_id_for_review_audit(survivor),
        )
        review_repo.save(review)

        logger.info(
            "event=position_merge_confirmed inventory_id=%s aisle_id=%s survivor_id=%s "
            "source_ids=%s merged_quantity=%s actor_user_id=%s",
            inventory_id,
            aisle_id,
            survivor_id,
            ",".join(source_ids),
            plan.merged_quantity,
            actor_user_id,
        )
        return PositionMergeConfirmResult(
            survivor_id=survivor_id,
            merged_quantity=int(plan.merged_quantity),
            source_ids=tuple(source_ids),
            already_merged=False,
        )
