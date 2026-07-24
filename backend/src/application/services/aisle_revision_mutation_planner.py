"""Pure mutation planner for aisle revision apply (Phase 8 corrections).

The planner reads a fully materialized view of current state and returns an immutable plan of
the writes required to publish a new authoritative finalization. It performs **no** I/O, so the
apply use case can validate everything (staleness, position compare-and-swap, fail-closed
guards) before opening a transaction, and the plan itself is unit-testable in isolation.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.application.services.aisle_revision_snapshot import (
    RevisionSnapshot,
    canonical_apply_content_hash,
)
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItem,
    AisleRevisionItemStatus,
    PositionVersion,
)
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
    AuthoritativeExclusionReason,
    AuthoritativeFinalizationItemStatus,
)
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
    AuthoritativeResultSource,
)
from src.domain.positions.entities import Position, PositionStatus

PLAN_ERROR_REVISION_STALE = "REVISION_STALE"
PLAN_ERROR_POSITION_MISSING = "POSITION_MISSING"
PLAN_ERROR_POSITION_VERSION_CONFLICT = "POSITION_VERSION_CONFLICT"
PLAN_ERROR_POSITION_SCOPE_MISMATCH = "POSITION_SCOPE_MISMATCH"
PLAN_ERROR_INVALID = "AISLE_REVISION_INVALID"
PLAN_ERROR_EMPTY = "AISLE_REVISION_EMPTY"

#: Item statuses that publish a new authoritative result version when content differs.
_REVISING_STATUSES = frozenset(
    {
        AisleRevisionItemStatus.MODIFIED.value,
        AisleRevisionItemStatus.ADOPT_REMOTE.value,
        AisleRevisionItemStatus.ROLLED_BACK.value,
        AisleRevisionItemStatus.RESTORED.value,
    }
)

#: Placeholder version: the repository derives the authoritative next version under lock.
RESULT_VERSION_ASSIGNED_BY_REPOSITORY = 0


class AisleRevisionPlanError(Exception):
    """Deterministic, auditable planning failure carrying a stable error code."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _sha(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResultVersionOp:
    """Create a new authoritative result version, superseding ``expected_current_id``."""

    asset_id: str
    revision_item_id: str
    new_result: AuthoritativeLocalCodeScanResult
    expected_current_id: str | None
    expected_row_version: int | None


@dataclass(frozen=True)
class PositionVersionOp:
    """Append a position version and refresh the position's corrected summary in place."""

    position_id: str
    asset_id: str
    revision_item_id: str
    position_version: PositionVersion
    corrected_summary: Mapping[str, Any]


@dataclass(frozen=True)
class PositionDeactivateOp:
    """Deactivate a position because its asset was excluded (history rows stay untouched)."""

    position_id: str
    asset_id: str
    revision_item_id: str
    reason: str


@dataclass(frozen=True)
class ExclusionCreateOp:
    asset_id: str
    exclusion: AuthoritativeAisleExcludedAsset


@dataclass(frozen=True)
class AisleRevisionPlanInput:
    """Materialized current state required to plan an apply. All reads happen before planning."""

    revision: AisleRevision
    items: Sequence[AisleRevisionItem]
    snapshot: RevisionSnapshot
    expected_base_finalization_id: str
    current_finalization: AuthoritativeAisleFinalization | None
    next_finalization_version: int
    current_result_by_asset: Mapping[str, AuthoritativeLocalCodeScanResult | None]
    position_by_id: Mapping[str, Position | None]
    current_position_version_by_id: Mapping[str, PositionVersion | None]
    max_position_version_by_id: Mapping[str, int]
    current_exclusion_by_asset: Mapping[str, AuthoritativeAisleExcludedAsset | None]
    applied_by: str
    now: datetime


@dataclass(frozen=True)
class AisleRevisionMutationPlan:
    new_finalization_id: str
    new_finalization_version: int
    apply_content_hash: str
    results_to_version: tuple[ResultVersionOp, ...]
    positions_to_version: tuple[PositionVersionOp, ...]
    positions_to_deactivate: tuple[PositionDeactivateOp, ...]
    exclusions_to_create: tuple[ExclusionCreateOp, ...]
    exclusions_to_supersede: tuple[str, ...]
    finalization_items: tuple[AuthoritativeAisleFinalizationItem, ...]
    applied_count: int
    excluded_count: int
    changed_count: int
    total_assets: int


class AisleRevisionMutationPlanner:
    """Turns a revision plus current state into an immutable set of write operations."""

    def __init__(self, *, id_factory: Callable[[], str] | None = None) -> None:
        self._new_id = id_factory or (lambda: str(uuid.uuid4()))

    @staticmethod
    def apply_content_hash(
        *, revision: AisleRevision, items: Sequence[AisleRevisionItem]
    ) -> str:
        """Canonical hash of the mutation payload; stable across retries of the same apply."""
        return canonical_apply_content_hash(
            revision_id=revision.id,
            base_finalization_id=revision.base_finalization_id,
            items=[
                {
                    "asset_id": item.asset_id,
                    "item_status": item.item_status,
                    "internal_code": item.proposed_internal_code,
                    "quantity": item.proposed_quantity,
                    "exclusion_state": item.proposed_exclusion_state,
                    "proposal_source": item.proposal_source,
                    "proposal_reference_id": item.proposal_reference_id,
                    "base_result_id": item.base_result_id,
                    "base_position_id": item.base_position_id,
                }
                for item in items
            ],
        )

    def plan(self, data: AisleRevisionPlanInput) -> AisleRevisionMutationPlan:
        revision = data.revision
        items = sorted(data.items, key=lambda i: i.asset_id)
        self._require_fresh_base(data)
        self._require_non_empty(items)

        snapshot_by_asset = {a.asset_id: a for a in data.snapshot.assets}
        new_finalization_id = self._new_id()

        results: list[ResultVersionOp] = []
        position_versions: list[PositionVersionOp] = []
        deactivations: list[PositionDeactivateOp] = []
        exclusion_creates: list[ExclusionCreateOp] = []
        exclusion_supersedes: list[str] = []
        finalization_items: list[AuthoritativeAisleFinalizationItem] = []
        applied_count = 0
        excluded_count = 0

        for item in items:
            base_snap = snapshot_by_asset.get(item.asset_id)
            self._require_fresh_result(item, data)

            if item.item_status == AisleRevisionItemStatus.EXCLUDED.value:
                excluded_count += 1
                was_excluded = bool(base_snap and base_snap.excluded)
                prior = data.current_exclusion_by_asset.get(item.asset_id)
                if not was_excluded or prior is None:
                    if prior is not None:
                        exclusion_supersedes.append(item.asset_id)
                    exclusion_creates.append(
                        ExclusionCreateOp(
                            asset_id=item.asset_id,
                            exclusion=AuthoritativeAisleExcludedAsset(
                                id=self._new_id(),
                                inventory_id=revision.inventory_id,
                                aisle_id=revision.aisle_id,
                                asset_id=item.asset_id,
                                reason=AuthoritativeExclusionReason.USER_EXCLUDED.value,
                                excluded_by=data.applied_by,
                                excluded_at=data.now,
                                is_current=True,
                                created_at=data.now,
                                updated_at=data.now,
                            ),
                        )
                    )
                if item.base_position_id:
                    position = self._require_position(item, item.base_position_id, data)
                    if position.status != PositionStatus.DELETED:
                        deactivations.append(
                            PositionDeactivateOp(
                                position_id=item.base_position_id,
                                asset_id=item.asset_id,
                                revision_item_id=item.id,
                                reason=item.change_reason or revision.reason,
                            )
                        )
                finalization_items.append(
                    AuthoritativeAisleFinalizationItem(
                        id=self._new_id(),
                        finalization_id=new_finalization_id,
                        asset_id=item.asset_id,
                        authoritative_result_id=item.base_result_id,
                        position_id=None,
                        item_status=AuthoritativeFinalizationItemStatus.EXCLUDED.value,
                        created_at=data.now,
                    )
                )
                continue

            if item.item_status == AisleRevisionItemStatus.RESTORED.value:
                if data.current_exclusion_by_asset.get(item.asset_id) is not None:
                    exclusion_supersedes.append(item.asset_id)

            # A confirmed-and-applied item must always resolve to a live position.
            position_id = item.base_position_id
            if not position_id:
                raise AisleRevisionPlanError(
                    f"Asset {item.asset_id} has no position; cannot publish as applied",
                    error_code=PLAN_ERROR_POSITION_MISSING,
                )
            self._require_position(item, position_id, data)

            code = (item.proposed_internal_code or "").strip()
            result_id = item.base_result_id
            if self._needs_new_result(item, base_snap, code):
                if not code:
                    raise AisleRevisionPlanError(
                        f"Missing internal_code for asset {item.asset_id}",
                        error_code=PLAN_ERROR_INVALID,
                    )
                op = self._plan_result_version(item=item, code=code, data=data)
                results.append(op)
                result_id = op.new_result.id
                position_versions.append(
                    self._plan_position_version(
                        item=item,
                        position_id=position_id,
                        code=code,
                        result_id=result_id,
                        data=data,
                    )
                )

            applied_count += 1
            finalization_items.append(
                AuthoritativeAisleFinalizationItem(
                    id=self._new_id(),
                    finalization_id=new_finalization_id,
                    asset_id=item.asset_id,
                    authoritative_result_id=result_id,
                    position_id=position_id,
                    item_status=(
                        AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value
                    ),
                    created_at=data.now,
                )
            )

        return AisleRevisionMutationPlan(
            new_finalization_id=new_finalization_id,
            new_finalization_version=data.next_finalization_version,
            apply_content_hash=self.apply_content_hash(revision=revision, items=items),
            results_to_version=tuple(results),
            positions_to_version=tuple(position_versions),
            positions_to_deactivate=tuple(deactivations),
            exclusions_to_create=tuple(exclusion_creates),
            exclusions_to_supersede=tuple(dict.fromkeys(exclusion_supersedes)),
            finalization_items=tuple(finalization_items),
            applied_count=applied_count,
            excluded_count=excluded_count,
            changed_count=sum(
                1
                for i in items
                if i.item_status != AisleRevisionItemStatus.UNCHANGED.value
            ),
            total_assets=len(items),
        )

    def _require_fresh_base(self, data: AisleRevisionPlanInput) -> None:
        revision = data.revision
        if revision.base_finalization_id != data.expected_base_finalization_id:
            raise AisleRevisionPlanError(
                "El pasillo cambió desde que comenzaste esta revisión.",
                error_code=PLAN_ERROR_REVISION_STALE,
            )
        current = data.current_finalization
        if current is None or current.id != revision.base_finalization_id:
            raise AisleRevisionPlanError(
                "Base finalization is no longer current",
                error_code=PLAN_ERROR_REVISION_STALE,
            )

    def _require_non_empty(self, items: Sequence[AisleRevisionItem]) -> None:
        changed = [
            i for i in items if i.item_status != AisleRevisionItemStatus.UNCHANGED.value
        ]
        if not changed:
            raise AisleRevisionPlanError(
                "Cannot apply empty revision", error_code=PLAN_ERROR_EMPTY
            )
        remaining = [
            i for i in items if i.item_status != AisleRevisionItemStatus.EXCLUDED.value
        ]
        if not remaining:
            raise AisleRevisionPlanError(
                "Cannot exclude all assets from aisle", error_code=PLAN_ERROR_INVALID
            )

    def _require_fresh_result(
        self, item: AisleRevisionItem, data: AisleRevisionPlanInput
    ) -> None:
        if not item.base_result_id:
            return
        current = data.current_result_by_asset.get(item.asset_id)
        if current is None or current.id != item.base_result_id:
            raise AisleRevisionPlanError(
                f"Result for asset {item.asset_id} changed since revision started",
                error_code=PLAN_ERROR_REVISION_STALE,
            )

    def _require_position(
        self,
        item: AisleRevisionItem,
        position_id: str,
        data: AisleRevisionPlanInput,
    ) -> Position:
        position = data.position_by_id.get(position_id)
        if position is None:
            raise AisleRevisionPlanError(
                f"Position {position_id} not found for asset {item.asset_id}",
                error_code=PLAN_ERROR_POSITION_MISSING,
            )
        if position.aisle_id != data.revision.aisle_id:
            raise AisleRevisionPlanError(
                f"Position {position_id} belongs to aisle {position.aisle_id}, "
                f"not {data.revision.aisle_id}",
                error_code=PLAN_ERROR_POSITION_SCOPE_MISMATCH,
            )
        self._require_position_cas(item, position, position_id, data)
        return position

    def _require_position_cas(
        self,
        item: AisleRevisionItem,
        position: Position,
        position_id: str,
        data: AisleRevisionPlanInput,
    ) -> None:
        expected_version_id = item.base_position_version_id
        if expected_version_id:
            current = data.current_position_version_by_id.get(position_id)
            if current is None or current.id != expected_version_id:
                raise AisleRevisionPlanError(
                    f"Position {position_id} changed since revision started",
                    error_code=PLAN_ERROR_POSITION_VERSION_CONFLICT,
                )
        expected_row_version = item.base_position_row_version
        if expected_row_version is not None:
            actual = getattr(position, "row_version", None)
            if actual is not None and int(actual) != int(expected_row_version):
                raise AisleRevisionPlanError(
                    f"Position {position_id} row_version changed since revision started",
                    error_code=PLAN_ERROR_POSITION_VERSION_CONFLICT,
                )

    def _needs_new_result(
        self,
        item: AisleRevisionItem,
        base_snap: Any,
        code: str,
    ) -> bool:
        if item.item_status not in _REVISING_STATUSES:
            return False
        if item.item_status == AisleRevisionItemStatus.RESTORED.value:
            return True
        if base_snap is None:
            return True
        return code != (base_snap.base_internal_code or "") or (
            item.proposed_quantity != base_snap.base_quantity
        )

    def _plan_result_version(
        self,
        *,
        item: AisleRevisionItem,
        code: str,
        data: AisleRevisionPlanInput,
    ) -> ResultVersionOp:
        revision = data.revision
        previous = data.current_result_by_asset.get(item.asset_id)
        quantity = item.proposed_quantity
        content_hash = _sha(item.asset_id, code, str(quantity), revision.id, item.id)
        new_result = AuthoritativeLocalCodeScanResult(
            id=self._new_id(),
            asset_id=item.asset_id,
            inventory_id=revision.inventory_id,
            aisle_id=revision.aisle_id,
            client_file_id=previous.client_file_id if previous else item.asset_id,
            result_version=RESULT_VERSION_ASSIGNED_BY_REPOSITORY,
            supersedes_result_id=previous.id if previous else None,
            is_current=True,
            internal_code=code,
            quantity=quantity,
            quantity_status=(
                AuthoritativeQuantityStatus.PRESENT.value
                if quantity is not None
                else AuthoritativeQuantityStatus.MISSING.value
            ),
            source=AuthoritativeResultSource.LOCAL_MANUAL_CORRECTION.value,
            detected_internal_code=previous.detected_internal_code if previous else None,
            detected_quantity=previous.detected_quantity if previous else None,
            detected_symbology=previous.detected_symbology if previous else None,
            parser_version=previous.parser_version if previous else "revision",
            detector_version=previous.detector_version if previous else "revision",
            prepared_asset_sha256=(
                previous.prepared_asset_sha256 if previous else content_hash
            ),
            content_hash=content_hash,
            confirmed_by=data.applied_by,
            client_confirmed_at=None,
            server_confirmed_at=data.now,
            server_received_at=data.now,
            confirmed_at=data.now,
            applied_job_id=f"revision:{revision.id}",
            applied_at=data.now,
            row_version=1,
            schema_version=previous.schema_version if previous else "1",
            created_at=data.now,
            updated_at=data.now,
        )
        return ResultVersionOp(
            asset_id=item.asset_id,
            revision_item_id=item.id,
            new_result=new_result,
            expected_current_id=previous.id if previous else None,
            expected_row_version=previous.row_version if previous else None,
        )

    def _plan_position_version(
        self,
        *,
        item: AisleRevisionItem,
        position_id: str,
        code: str,
        result_id: str,
        data: AisleRevisionPlanInput,
    ) -> PositionVersionOp:
        revision = data.revision
        quantity = item.proposed_quantity
        previous = data.current_position_version_by_id.get(position_id)
        next_version = int(data.max_position_version_by_id.get(position_id, 0)) + 1
        position_version = PositionVersion(
            id=self._new_id(),
            position_id=position_id,
            version=next_version,
            aisle_id=revision.aisle_id,
            asset_id=item.asset_id,
            internal_code=code,
            quantity=quantity,
            result_id=result_id,
            is_current=True,
            supersedes_position_version_id=previous.id if previous else None,
            revision_id=revision.id,
            revision_item_id=item.id,
            created_by=data.applied_by,
            created_at=data.now,
            content_hash=_sha(position_id, code, str(quantity), str(next_version)),
        )
        return PositionVersionOp(
            position_id=position_id,
            asset_id=item.asset_id,
            revision_item_id=item.id,
            position_version=position_version,
            corrected_summary={
                "internal_code": code,
                "quantity": quantity,
                "source_asset_id": item.asset_id,
                "authoritative_result_id": result_id,
                "revision_id": revision.id,
                "revision_item_id": item.id,
            },
        )
