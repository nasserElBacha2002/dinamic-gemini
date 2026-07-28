"""Apply aisle revision and rollback (Phase 8) — always creates new versions.

Apply is all-or-nothing: the mutation planner builds an immutable plan; a Unit of Work
executes every write on a single connection/transaction. Mid-flight failures roll back
completely — the revision is never left half-published.

Downstream notification is intentionally *not* an outbox event: the only outbox in the system
(``ArtifactPublicationOutboxStore``) is keyed by job id and artifact kind, so it cannot carry an
aisle-level domain event, and introducing a general event outbox is out of scope here. Instead the
committed rows are the audit trail (``aisle_revisions`` plus the new authoritative finalization),
and inventory rollup is refreshed post-commit through ``InventoryStatusReconciler``. If an
``AISLE_REVISION_APPLIED`` event is needed later, publish it from the reconcile hook below so it
stays after the commit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from src.application.ports.aisle_revision_repository import AisleRevisionRepository
from src.application.ports.aisle_revision_unit_of_work import (
    AisleRevisionRepositories,
    AisleRevisionUnitOfWork,
)
from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
    AuthoritativeVersionConflictError,
)
from src.application.ports.repositories import PositionRepository
from src.application.services.aisle_revision_mutation_planner import (
    PLAN_ERROR_POSITION_MISSING,
    PLAN_ERROR_POSITION_SCOPE_MISMATCH,
    PLAN_ERROR_POSITION_VERSION_CONFLICT,
    PLAN_ERROR_REVISION_STALE,
    AisleRevisionMutationPlan,
    AisleRevisionMutationPlanner,
    AisleRevisionPlanError,
    AisleRevisionPlanInput,
    ExclusionCreateOp,
    PositionDeactivateOp,
    PositionVersionOp,
    ResultVersionOp,
)
from src.application.services.aisle_revision_snapshot import parse_revision_snapshot
from src.application.services.historical_finalization_snapshot_reader import (
    HistoricalFinalizationSnapshotReader,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.manage_aisle_revisions import (
    AisleRevisionConflictError,
    AisleRevisionDisabledError,
    AisleRevisionLockError,
    AisleRevisionNotFoundError,
    CreateAisleRevision,
    CreateAisleRevisionCommand,
    UpdateAisleRevisionItem,
    UpdateAisleRevisionItemCommand,
)
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItemStatus,
    AisleRevisionStatus,
    AisleRevisionType,
    revision_is_editable,
)
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleFinalization,
    AuthoritativeFinalizationStatus,
)
from src.domain.positions.entities import PositionStatus

logger = logging.getLogger(__name__)

_LOCK_LEASE = timedelta(seconds=90)


class AisleRevisionStaleError(Exception):
    error_code = "REVISION_STALE"

    def __init__(self, message: str = "El pasillo cambió desde que comenzaste esta revisión.") -> None:
        super().__init__(message)


class AisleRevisionApplyConflictError(Exception):
    def __init__(self, message: str, *, error_code: str = "AISLE_REVISION_APPLY_CONFLICT") -> None:
        super().__init__(message)
        self.error_code = error_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApplyAisleRevisionCommand:
    inventory_id: str
    aisle_id: str
    revision_id: str
    apply_id: str
    expected_base_finalization_id: str
    applied_by: str


@dataclass(frozen=True)
class CreateRollbackCommand:
    inventory_id: str
    aisle_id: str
    rollback_id: str
    target_finalization_id: str
    reason: str
    requested_by: str
    apply_immediately: bool = True


def _map_plan_error(exc: AisleRevisionPlanError) -> Exception:
    if exc.error_code == PLAN_ERROR_REVISION_STALE:
        return AisleRevisionStaleError(str(exc))
    if exc.error_code in (
        PLAN_ERROR_POSITION_MISSING,
        PLAN_ERROR_POSITION_VERSION_CONFLICT,
        PLAN_ERROR_POSITION_SCOPE_MISMATCH,
    ):
        return AisleRevisionApplyConflictError(str(exc), error_code=exc.error_code)
    return AisleRevisionApplyConflictError(str(exc), error_code=exc.error_code)


class ApplyAisleRevision:
    """Publish a revision as a new finalization version inside one Unit of Work."""

    def __init__(
        self,
        *,
        enabled: bool,
        uow_factory: Callable[[], AisleRevisionUnitOfWork],
        revision_repo: AisleRevisionRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        position_repo: PositionRepository,
        inventory_status_reconciler: InventoryStatusReconciler | None = None,
        planner: AisleRevisionMutationPlanner | None = None,
        clock: Any = None,
    ) -> None:
        self._enabled = enabled
        self._uow_factory = uow_factory
        self._revision_repo = revision_repo
        self._finalization_repo = finalization_repo
        self._authoritative_repo = authoritative_repo
        self._position_repo = position_repo
        self._reconciler = inventory_status_reconciler
        self._planner = planner or AisleRevisionMutationPlanner()
        self._clock = clock

    @property
    def authoritative_repo(self) -> AuthoritativeLocalCodeScanRepository:
        """Public access for callers that need result lookups (e.g. diagnostics)."""
        return self._authoritative_repo

    def _now(self) -> datetime:
        if self._clock is not None and hasattr(self._clock, "now"):
            return cast(datetime, self._clock.now())
        return _utcnow()

    def execute(self, command: ApplyAisleRevisionCommand) -> AisleRevision:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        apply_id = (command.apply_id or "").strip()
        if not apply_id:
            raise AisleRevisionApplyConflictError(
                "apply_id is required", error_code="AISLE_REVISION_INVALID"
            )
        applied_by = (command.applied_by or "").strip()
        if not applied_by:
            raise AisleRevisionApplyConflictError(
                "applied_by (authenticated user id) is required",
                error_code="AISLE_REVISION_ACTOR_REQUIRED",
            )

        revision = self._revision_repo.get_revision(command.revision_id)
        if (
            revision is None
            or revision.inventory_id != command.inventory_id
            or revision.aisle_id != command.aisle_id
        ):
            raise AisleRevisionNotFoundError(f"Revision not found: {command.revision_id}")

        items = list(self._revision_repo.list_items(revision.id))
        content_hash = self._planner.apply_content_hash(revision=revision, items=items)

        # Idempotent replay: same apply_id + same content hash → return completed revision.
        if revision.status == AisleRevisionStatus.COMPLETED.value and revision.apply_id == apply_id:
            if revision.apply_content_hash and revision.apply_content_hash != content_hash:
                raise AisleRevisionApplyConflictError(
                    "apply_id reused with a different mutation payload",
                    error_code="AISLE_REVISION_APPLY_CONFLICT",
                )
            if revision.new_finalization_id:
                return revision

        if revision.apply_id and revision.apply_id != apply_id:
            raise AisleRevisionApplyConflictError(
                "apply_id conflict for revision",
                error_code="AISLE_REVISION_APPLY_CONFLICT",
            )

        # APPLYING without COMPLETED means a prior attempt died mid-flight; allow retry
        # (SQL UoW never leaves APPLYING visible after rollback).
        if not revision_is_editable(revision.status) and revision.status != (
            AisleRevisionStatus.APPLYING.value
        ):
            raise AisleRevisionApplyConflictError(
                f"Revision status {revision.status} cannot be applied",
                error_code="AISLE_REVISION_NOT_EDITABLE",
            )

        try:
            plan_input = self._materialize_plan_input(
                revision=revision,
                items=items,
                expected_base_finalization_id=command.expected_base_finalization_id,
                applied_by=applied_by,
                now=self._now(),
            )
            plan = self._planner.plan(plan_input)
        except AisleRevisionPlanError as exc:
            raise _map_plan_error(exc) from exc

        now = self._now()
        owner = f"rev-apply-{apply_id[:8]}"
        completed: AisleRevision | None = None

        try:
            with self._uow_factory() as uow:
                repos = uow.repositories
                if not repos.revision_repo.try_acquire_lock(
                    inventory_id=command.inventory_id,
                    aisle_id=command.aisle_id,
                    owner_token=owner,
                    lease_expires_at=now + _LOCK_LEASE,
                    now=now,
                ):
                    raise AisleRevisionLockError("Could not acquire aisle revision lock")
                try:
                    # Re-check stale under the transactional lock.
                    current = repos.finalization_repo.get_current_for_aisle(command.aisle_id)
                    if current is None or current.id != revision.base_finalization_id:
                        raise AisleRevisionStaleError()

                    completed = self._execute_plan(
                        repos=repos,
                        revision=revision,
                        plan=plan,
                        apply_id=apply_id,
                        content_hash=content_hash,
                        current=current,
                        applied_by=applied_by,
                        now=now,
                    )
                    uow.commit()
                finally:
                    repos.revision_repo.release_lock(
                        aisle_id=command.aisle_id, owner_token=owner, now=self._now()
                    )
        except AisleRevisionStaleError:
            raise
        except AisleRevisionLockError:
            raise
        except AisleRevisionApplyConflictError:
            raise
        except AuthoritativeVersionConflictError as exc:
            raise AisleRevisionStaleError("Concurrent authoritative version conflict") from exc
        except Exception:
            logger.exception(
                "aisle_revision_apply_failed revision_id=%s (transaction rolled back)",
                command.revision_id,
            )
            raise

        if self._reconciler is not None and completed is not None:
            try:
                self._reconciler.reconcile(command.inventory_id)
            except Exception:
                logger.exception(
                    "aisle_revision_inventory_reconcile_failed inventory_id=%s",
                    command.inventory_id,
                )

        assert completed is not None
        logger.info(
            "aisle_revision_completed revision_id=%s new_finalization_id=%s changed=%s",
            revision.id,
            completed.new_finalization_id,
            plan.changed_count,
        )
        return completed

    def _materialize_plan_input(
        self,
        *,
        revision: AisleRevision,
        items: Sequence,
        expected_base_finalization_id: str,
        applied_by: str,
        now: datetime,
    ) -> AisleRevisionPlanInput:
        current = self._finalization_repo.get_current_for_aisle(revision.aisle_id)
        snapshot = parse_revision_snapshot(revision.snapshot_json)
        asset_ids = [i.asset_id for i in items]
        current_result_by_asset = {
            aid: self._authoritative_repo.get_current_for_asset(aid) for aid in asset_ids
        }
        position_ids = [i.base_position_id for i in items if i.base_position_id]
        position_by_id = {
            pid: self._position_repo.get_by_id(pid) for pid in position_ids
        }
        current_pv_by_id = {
            pid: self._revision_repo.get_current_position_version(pid) for pid in position_ids
        }
        max_pv_by_id = {
            pid: self._revision_repo.max_position_version(pid) for pid in position_ids
        }
        current_exclusion_by_asset = {
            aid: self._finalization_repo.get_current_exclusion(
                inventory_id=revision.inventory_id,
                aisle_id=revision.aisle_id,
                asset_id=aid,
            )
            for aid in asset_ids
        }
        return AisleRevisionPlanInput(
            revision=revision,
            items=items,
            snapshot=snapshot,
            expected_base_finalization_id=expected_base_finalization_id,
            current_finalization=current,
            next_finalization_version=self._finalization_repo.max_version_for_aisle(
                revision.aisle_id
            )
            + 1,
            current_result_by_asset=current_result_by_asset,
            position_by_id=position_by_id,
            current_position_version_by_id=current_pv_by_id,
            max_position_version_by_id=max_pv_by_id,
            current_exclusion_by_asset=current_exclusion_by_asset,
            applied_by=applied_by,
            now=now,
        )

    def _execute_plan(
        self,
        *,
        repos: AisleRevisionRepositories,
        revision: AisleRevision,
        plan: AisleRevisionMutationPlan,
        apply_id: str,
        content_hash: str,
        current: AuthoritativeAisleFinalization,
        applied_by: str,
        now: datetime,
    ) -> AisleRevision:
        for asset_id in plan.exclusions_to_supersede:
            repos.finalization_repo.supersede_exclusion(
                inventory_id=revision.inventory_id,
                aisle_id=revision.aisle_id,
                asset_id=asset_id,
                now=now,
            )

        for exclusion_op in plan.exclusions_to_create:
            if not isinstance(exclusion_op, ExclusionCreateOp):
                continue
            repos.finalization_repo.upsert_exclusion(exclusion_op.exclusion)

        for result_version_op in plan.results_to_version:
            if not isinstance(result_version_op, ResultVersionOp):
                continue
            created = repos.authoritative_repo.create_authoritative_version(
                new_result=result_version_op.new_result,
                expected_current_id=result_version_op.expected_current_id,
                expected_row_version=result_version_op.expected_row_version,
            )
            repos.authoritative_repo.mark_applied_if_version(
                result_id=created.id,
                job_id=f"revision:{revision.id}",
                applied_at=now,
                expected_row_version=created.row_version,
            )

        for position_deactivate_op in plan.positions_to_deactivate:
            if not isinstance(position_deactivate_op, PositionDeactivateOp):
                continue
            pos = repos.position_repo.get_by_id(position_deactivate_op.position_id)
            if pos is not None and pos.status != PositionStatus.DELETED:
                repos.position_repo.save(
                    replace(
                        pos,
                        status=PositionStatus.DELETED,
                        updated_at=now,
                    )
                )

        for position_version_op in plan.positions_to_version:
            if not isinstance(position_version_op, PositionVersionOp):
                continue
            pos = repos.position_repo.get_by_id(position_version_op.position_id)
            if pos is None:
                raise AisleRevisionApplyConflictError(
                    f"Position {position_version_op.position_id} missing during apply",
                    error_code=PLAN_ERROR_POSITION_MISSING,
                )
            repos.position_repo.save(
                replace(
                    pos,
                    status=PositionStatus.CORRECTED,
                    corrected_summary_json=dict(position_version_op.corrected_summary),
                    updated_at=now,
                )
            )
            repos.revision_repo.save_position_version(
                position_version_op.position_version, supersede_current=True
            )

        new_fin = AuthoritativeAisleFinalization(
            id=plan.new_finalization_id,
            inventory_id=revision.inventory_id,
            aisle_id=revision.aisle_id,
            capture_session_id=current.capture_session_id,
            finalization_version=plan.new_finalization_version,
            status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
            total_assets=plan.total_assets,
            applied_assets=plan.applied_count,
            excluded_assets=plan.excluded_count,
            position_count=sum(1 for fi in plan.finalization_items if fi.position_id),
            expected_asset_count=plan.total_assets,
            content_hash=content_hash,
            confirmed_by=applied_by,
            confirmed_at=now,
            completed_at=now,
            is_current=True,
            row_version=1,
            created_at=now,
            updated_at=now,
            supersedes_finalization_id=current.id,
            revision_id=revision.id,
        )
        repos.finalization_repo.save_finalization(
            finalization=new_fin,
            items=list(plan.finalization_items),
            supersede_current=True,
        )

        completed = AisleRevision(
            **{
                **revision.__dict__,
                "status": AisleRevisionStatus.COMPLETED.value,
                "apply_id": apply_id,
                "apply_content_hash": content_hash,
                "new_finalization_id": plan.new_finalization_id,
                "completed_at": now,
                "updated_at": now,
                "row_version": revision.row_version + 1,
            }
        )
        return repos.revision_repo.save_revision(completed)


class CreateRollbackRevision:
    """Create ROLLBACK revision from a prior finalization snapshot and optionally apply."""

    def __init__(
        self,
        *,
        enabled: bool,
        create_revision: CreateAisleRevision,
        apply_revision: ApplyAisleRevision,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        revision_repo: AisleRevisionRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        update_item: UpdateAisleRevisionItem,
        snapshot_reader: HistoricalFinalizationSnapshotReader | None = None,
    ) -> None:
        self._enabled = enabled
        self._create = create_revision
        self._apply = apply_revision
        self._finalization_repo = finalization_repo
        self._revision_repo = revision_repo
        self._authoritative_repo = authoritative_repo
        self._update_item = update_item
        self._snapshot_reader = snapshot_reader or HistoricalFinalizationSnapshotReader(
            finalization_repo=finalization_repo,
            authoritative_repo=authoritative_repo,
            position_repo=None,
        )

    def execute(self, command: CreateRollbackCommand) -> AisleRevision:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        if not (command.requested_by or "").strip():
            raise AisleRevisionApplyConflictError(
                "requested_by (authenticated user id) is required",
                error_code="AISLE_REVISION_ACTOR_REQUIRED",
            )

        target = self._finalization_repo.get_by_id(command.target_finalization_id)
        if target is None or target.aisle_id != command.aisle_id:
            raise AisleRevisionConflictError(
                "target_finalization_id not found for aisle",
                error_code="AISLE_REVISION_INVALID_TARGET",
            )
        current = self._finalization_repo.get_current_for_aisle(command.aisle_id)
        if current is None:
            raise AisleRevisionConflictError(
                "No current finalization",
                error_code="AISLE_NOT_FINALIZED",
            )
        if target.id == current.id:
            raise AisleRevisionConflictError(
                "Already at target finalization",
                error_code="AISLE_REVISION_INVALID_TARGET",
            )

        revision, _replayed = self._create.execute(
            CreateAisleRevisionCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                revision_id=command.rollback_id,
                revision_type=AisleRevisionType.ROLLBACK.value,
                reason=command.reason,
                requested_by=command.requested_by,
                target_finalization_id=command.target_finalization_id,
            )
        )

        historical = self._snapshot_reader.read(
            finalization_id=target.id,
            aisle_id=command.aisle_id,
        )
        for entry in historical.entries:
            if entry.excluded:
                self._update_item.execute(
                    UpdateAisleRevisionItemCommand(
                        inventory_id=command.inventory_id,
                        aisle_id=command.aisle_id,
                        revision_id=revision.id,
                        asset_id=entry.asset_id,
                        actor_id=command.requested_by,
                        exclusion_action="EXCLUDE",
                        reason=command.reason,
                    )
                )
                continue
            if not entry.internal_code:
                continue
            item = self._revision_repo.get_item(
                revision_id=revision.id, asset_id=entry.asset_id
            )
            if item is None:
                continue
            now = _utcnow()
            updated = item.__class__(
                **{
                    **item.__dict__,
                    "proposed_internal_code": entry.internal_code,
                    "proposed_quantity": entry.quantity,
                    "proposed_exclusion_state": "KEEP",
                    "proposal_source": "ROLLBACK_SOURCE",
                    "proposal_reference_id": target.id,
                    "change_reason": command.reason,
                    "item_status": AisleRevisionItemStatus.ROLLED_BACK.value,
                    "updated_at": now,
                }
            )
            self._revision_repo.save_item(updated)

        if not command.apply_immediately:
            return self._revision_repo.get_revision(revision.id) or revision

        return self._apply.execute(
            ApplyAisleRevisionCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                revision_id=revision.id,
                apply_id=f"apply-{command.rollback_id}",
                expected_base_finalization_id=revision.base_finalization_id,
                applied_by=command.requested_by,
            )
        )
