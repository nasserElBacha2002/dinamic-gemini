"""
GetPositionDetail use case — v3.0 Épica 6.

Returns a position with its product records and evidences.
Fails if inventory/aisle/position do not exist or do not match.

Phase 2: resolves result context (explicit job / operational / legacy) and scopes consolidation fetch;
includes run metadata for dataset-safe clients.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from src.application.errors import AisleNotFoundError, PositionResultContextMismatchError
from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.services.position_sku_consolidation import consolidate_positions_by_sku
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.review_validation import resolve_position
from src.domain.evidence.entities import Evidence
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionDetailRunContext:
    job_id: Optional[str]
    """Storage job on the position row (``None`` = legacy)."""
    result_context_source: str
    resolved_job_id: Optional[str]
    """Slice used for this response (same semantics as list/merge)."""
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_key: Optional[str] = None
    prompt_version: Optional[str] = None


@dataclass
class PositionDetailResult:
    position: Position
    products: Sequence[ProductRecord]
    evidences: Sequence[Evidence]
    review_actions: Sequence[ReviewAction]
    run_context: PositionDetailRunContext


class GetPositionDetailUseCase:
    """Return the operator-facing current review entity for a requested position id.

    By default, detail follows the same consolidated representative semantics as the aisle positions
    list (SKU merge). With ``exact_position=True``, returns the requested storage row and its
    evidence — used for photo-accurate review alongside ``consolidate_by_sku=false`` lists.

    Phase 2 (strict context): After resolving the aisle result slice (explicit ``job_id`` →
    operational job → legacy null-job rows), the position row's ``job_id`` must match that slice.
    If it does not (e.g. viewing a position from another run while defaults point elsewhere),
    :class:`PositionResultContextMismatchError` is raised — the API must not return data from the
    wrong run. Clients should pass ``job_id`` matching the position's run or adjust the operational
    pointer when product workflow allows.
    """

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        review_repo: ReviewActionRepository,
        job_repo: JobRepository,
        result_context_resolver: ResultContextResolver,
        *,
        positions_aisle_raw_cap: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._review_repo = review_repo
        self._job_repo = job_repo
        self._resolver = result_context_resolver
        self._raw_cap = max(1, int(positions_aisle_raw_cap))

    @staticmethod
    def _is_group_member(position: Position, requested_position_id: str) -> bool:
        summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
        aggregated = summary.get("aggregated_from_ids")
        if not isinstance(aggregated, list):
            return False
        return requested_position_id in aggregated

    def _resolve_operator_facing_position(
        self, position: Position, job_id_for_slice: Optional[str]
    ) -> Position:
        # Same resolved slice as list API; capped raw fetch — not an unscoped full-aisle scan.
        raw_positions = list(
            self._position_repo.list_by_aisle_query(
                position.aisle_id,
                PositionListQuery(
                    page=1,
                    page_size=self._raw_cap,
                    sort_by="created_at",
                    sort_dir="asc",
                    job_id=job_id_for_slice,
                ),
            )
        )
        consolidated = consolidate_positions_by_sku(raw_positions)
        for candidate in consolidated:
            if candidate.id == position.id or self._is_group_member(candidate, position.id):
                logger.debug(
                    "position_detail representative resolved requested_position_id=%s resolved_position_id=%s aisle_id=%s",
                    position.id,
                    candidate.id,
                    position.aisle_id,
                )
                return candidate
        logger.warning(
            "position_detail representative fallback requested_position_id=%s aisle_id=%s raw_cap=%s",
            position.id,
            position.aisle_id,
            self._raw_cap,
        )
        return position

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
        *,
        explicit_job_id: Optional[str] = None,
        exact_position: bool = False,
    ) -> PositionDetailResult:
        """Load position detail scoped to the resolved result context.

        Raises ``PositionResultContextMismatchError`` when ``position.job_id`` does not equal the
        resolved slice's job id (including ``None`` for legacy rows). This is intentional: 409
        conflict over wrong-run access, not a silent fallback to another dataset.
        """
        position = resolve_position(
            self._inventory_repo,
            self._aisle_repo,
            self._position_repo,
            inventory_id,
            aisle_id,
            position_id,
        )
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        ctx = self._resolver.resolve(aisle=aisle, explicit_job_id=explicit_job_id)
        if ctx.job_id_for_slice != position.job_id:
            raise PositionResultContextMismatchError(
                f"Position {position_id} is not in the resolved result context for this aisle "
                f"(resolved_job_id={ctx.job_id_for_slice!r}, position.job_id={position.job_id!r})"
            )

        operator_position = (
            position
            if exact_position
            else self._resolve_operator_facing_position(position, ctx.job_id_for_slice)
        )
        products = self._product_record_repo.list_by_position(operator_position.id)
        evidences = self._evidence_repo.list_by_entity("position", operator_position.id)
        review_actions = self._review_repo.list_by_position(operator_position.id)

        job = (
            self._job_repo.get_by_id(operator_position.job_id)
            if operator_position.job_id
            else None
        )
        run_context = PositionDetailRunContext(
            job_id=operator_position.job_id,
            result_context_source=ctx.source,
            resolved_job_id=ctx.job_id_for_slice,
            provider_name=job.provider_name if job else None,
            model_name=job.model_name if job else None,
            prompt_key=job.prompt_key if job else None,
            prompt_version=job.prompt_version if job else None,
        )
        return PositionDetailResult(
            position=operator_position,
            products=products,
            evidences=evidences,
            review_actions=review_actions,
            run_context=run_context,
        )
