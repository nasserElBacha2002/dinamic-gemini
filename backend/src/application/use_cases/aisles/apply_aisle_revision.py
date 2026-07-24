"""Apply aisle revision and rollback (Phase 8) — always creates new versions."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.ports.aisle_revision_repository import AisleRevisionRepository
from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
    AuthoritativeVersionConflictError,
)
from src.application.ports.repositories import PositionRepository
from src.application.services.aisle_revision_snapshot import parse_revision_snapshot
from src.application.use_cases.aisles.manage_aisle_revisions import (
    AisleRevisionConflictError,
    AisleRevisionDisabledError,
    AisleRevisionLockError,
    AisleRevisionNotFoundError,
    CreateAisleRevision,
    CreateAisleRevisionCommand,
)
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItemStatus,
    AisleRevisionStatus,
    AisleRevisionType,
    PositionVersion,
    revision_is_editable,
)
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
    AuthoritativeExclusionReason,
    AuthoritativeFinalizationItemStatus,
    AuthoritativeFinalizationStatus,
)
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
    AuthoritativeResultSource,
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


def _new_id() -> str:
    return str(uuid.uuid4())


def _sha(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


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


class ApplyAisleRevision:
    def __init__(
        self,
        *,
        enabled: bool,
        revision_repo: AisleRevisionRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        position_repo: PositionRepository,
        clock=None,
    ) -> None:
        self._enabled = enabled
        self._revision_repo = revision_repo
        self._finalization_repo = finalization_repo
        self._authoritative_repo = authoritative_repo
        self._position_repo = position_repo
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None and hasattr(self._clock, "now"):
            return self._clock.now()
        return _utcnow()

    def execute(self, command: ApplyAisleRevisionCommand) -> AisleRevision:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        apply_id = (command.apply_id or "").strip()
        if not apply_id:
            raise AisleRevisionApplyConflictError(
                "apply_id is required", error_code="AISLE_REVISION_INVALID"
            )

        revision = self._revision_repo.get_revision(command.revision_id)
        if (
            revision is None
            or revision.inventory_id != command.inventory_id
            or revision.aisle_id != command.aisle_id
        ):
            raise AisleRevisionNotFoundError(f"Revision not found: {command.revision_id}")

        # Idempotent replay
        if (
            revision.status == AisleRevisionStatus.COMPLETED.value
            and revision.apply_id == apply_id
            and revision.new_finalization_id
        ):
            return revision

        if revision.apply_id and revision.apply_id != apply_id:
            raise AisleRevisionApplyConflictError(
                "apply_id conflict for revision",
                error_code="AISLE_REVISION_APPLY_CONFLICT",
            )

        if not revision_is_editable(revision.status) and revision.status != (
            AisleRevisionStatus.APPLYING.value
        ):
            raise AisleRevisionApplyConflictError(
                f"Revision status {revision.status} cannot be applied",
                error_code="AISLE_REVISION_NOT_EDITABLE",
            )

        if revision.base_finalization_id != command.expected_base_finalization_id:
            raise AisleRevisionStaleError()

        current = self._finalization_repo.get_current_for_aisle(command.aisle_id)
        if current is None or current.id != revision.base_finalization_id:
            raise AisleRevisionStaleError()

        items = list(self._revision_repo.list_items(revision.id))
        changed = [
            i
            for i in items
            if i.item_status != AisleRevisionItemStatus.UNCHANGED.value
        ]
        if not changed:
            raise AisleRevisionApplyConflictError(
                "Cannot apply empty revision",
                error_code="AISLE_REVISION_EMPTY",
            )

        # Fail-closed: cannot exclude every asset
        remaining = [
            i
            for i in items
            if i.item_status != AisleRevisionItemStatus.EXCLUDED.value
        ]
        if not remaining:
            raise AisleRevisionApplyConflictError(
                "Cannot exclude all assets from aisle",
                error_code="AISLE_REVISION_INVALID",
            )

        now = self._now()
        owner = f"rev-apply-{apply_id[:8]}"
        if not self._revision_repo.try_acquire_lock(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            owner_token=owner,
            lease_expires_at=now + _LOCK_LEASE,
            now=now,
        ):
            raise AisleRevisionLockError("Could not acquire aisle revision lock")

        try:
            applying = AisleRevision(
                **{
                    **revision.__dict__,
                    "status": AisleRevisionStatus.APPLYING.value,
                    "apply_id": apply_id,
                    "updated_at": now,
                    "row_version": revision.row_version + 1,
                }
            )
            self._revision_repo.save_revision(applying)

            # Re-check stale under lock
            current = self._finalization_repo.get_current_for_aisle(command.aisle_id)
            if current is None or current.id != revision.base_finalization_id:
                conflicted = AisleRevision(
                    **{
                        **applying.__dict__,
                        "status": AisleRevisionStatus.CONFLICTED.value,
                        "failed_at": now,
                        "failure_code": "REVISION_STALE",
                        "failure_message": "Base finalization no longer current",
                        "updated_at": now,
                        "row_version": applying.row_version + 1,
                    }
                )
                self._revision_repo.save_revision(conflicted)
                raise AisleRevisionStaleError()

            snapshot = parse_revision_snapshot(revision.snapshot_json)
            new_result_by_asset: dict[str, AuthoritativeLocalCodeScanResult] = {}
            new_position_by_asset: dict[str, str] = {}
            fin_items: list[AuthoritativeAisleFinalizationItem] = []
            applied_count = 0
            excluded_count = 0

            for item in items:
                base_snap = next(
                    (a for a in snapshot.assets if a.asset_id == item.asset_id), None
                )
                # Stale result check
                if item.base_result_id:
                    cur_res = self._authoritative_repo.get_current_for_asset(item.asset_id)
                    if cur_res is None or cur_res.id != item.base_result_id:
                        raise AisleRevisionStaleError(
                            f"Result for asset {item.asset_id} changed since revision started"
                        )

                if item.item_status == AisleRevisionItemStatus.EXCLUDED.value:
                    excluded_count += 1
                    self._finalization_repo.upsert_exclusion(
                        AuthoritativeAisleExcludedAsset(
                            id=_new_id(),
                            inventory_id=command.inventory_id,
                            aisle_id=command.aisle_id,
                            asset_id=item.asset_id,
                            reason=AuthoritativeExclusionReason.USER_EXCLUDED.value,
                            excluded_by=command.applied_by,
                            excluded_at=now,
                            is_current=True,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    fin_items.append(
                        AuthoritativeAisleFinalizationItem(
                            id=_new_id(),
                            finalization_id="",  # filled after id known
                            asset_id=item.asset_id,
                            authoritative_result_id=item.base_result_id,
                            position_id=item.base_position_id,
                            item_status=AuthoritativeFinalizationItemStatus.EXCLUDED.value,
                            created_at=now,
                        )
                    )
                    continue

                code = (item.proposed_internal_code or "").strip()
                qty = item.proposed_quantity
                needs_new_result = item.item_status in (
                    AisleRevisionItemStatus.MODIFIED.value,
                    AisleRevisionItemStatus.ADOPT_REMOTE.value,
                    AisleRevisionItemStatus.ROLLED_BACK.value,
                    AisleRevisionItemStatus.RESTORED.value,
                ) and (
                    base_snap is None
                    or code != (base_snap.base_internal_code or "")
                    or qty != base_snap.base_quantity
                    or item.item_status == AisleRevisionItemStatus.RESTORED.value
                )

                result_id = item.base_result_id
                position_id = item.base_position_id

                if needs_new_result:
                    if not code:
                        raise AisleRevisionApplyConflictError(
                            f"Missing code for asset {item.asset_id}",
                            error_code="AISLE_REVISION_INVALID",
                        )
                    prev = self._authoritative_repo.get_current_for_asset(item.asset_id)
                    content_hash = _sha(
                        item.asset_id,
                        code,
                        str(qty),
                        revision.id,
                        item.id,
                    )
                    new_result = AuthoritativeLocalCodeScanResult(
                        id=_new_id(),
                        asset_id=item.asset_id,
                        inventory_id=command.inventory_id,
                        aisle_id=command.aisle_id,
                        client_file_id=prev.client_file_id if prev else item.asset_id,
                        result_version=1,
                        supersedes_result_id=prev.id if prev else None,
                        is_current=True,
                        internal_code=code,
                        quantity=qty,
                        quantity_status=(
                            AuthoritativeQuantityStatus.PRESENT.value
                            if qty is not None
                            else AuthoritativeQuantityStatus.MISSING.value
                        ),
                        source=AuthoritativeResultSource.LOCAL_MANUAL_CORRECTION.value,
                        detected_internal_code=prev.detected_internal_code if prev else None,
                        detected_quantity=prev.detected_quantity if prev else None,
                        detected_symbology=prev.detected_symbology if prev else None,
                        parser_version=prev.parser_version if prev else "revision",
                        detector_version=prev.detector_version if prev else "revision",
                        prepared_asset_sha256=(
                            prev.prepared_asset_sha256 if prev else content_hash
                        ),
                        content_hash=content_hash,
                        confirmed_by=command.applied_by,
                        client_confirmed_at=None,
                        server_confirmed_at=now,
                        server_received_at=now,
                        confirmed_at=now,
                        applied_job_id=f"revision:{revision.id}",
                        applied_at=now,
                        row_version=1,
                        schema_version=prev.schema_version if prev else "1",
                        created_at=now,
                        updated_at=now,
                    )
                    try:
                        created = self._authoritative_repo.create_authoritative_version(
                            new_result=new_result,
                            expected_current_id=prev.id if prev else None,
                            expected_row_version=prev.row_version if prev else None,
                        )
                    except AuthoritativeVersionConflictError as exc:
                        raise AisleRevisionStaleError(
                            "Concurrent authoritative version conflict"
                        ) from exc
                    # Ensure applied markers (memory may leave them; SQL create clears them)
                    marked = self._authoritative_repo.mark_applied_if_version(
                        result_id=created.id,
                        job_id=f"revision:{revision.id}",
                        applied_at=now,
                        expected_row_version=created.row_version,
                    )
                    created = marked or created
                    new_result_by_asset[item.asset_id] = created
                    result_id = created.id

                    # Position version + in-place update (position_id preserved when present)
                    if position_id:
                        pos = self._position_repo.get_by_id(position_id)
                        if pos is not None:
                            corrected: dict[str, Any] = {
                                "internal_code": code,
                                "quantity": qty,
                                "source_asset_id": item.asset_id,
                                "authoritative_result_id": result_id,
                                "revision_id": revision.id,
                                "revision_item_id": item.id,
                            }
                            updated_pos = replace(
                                pos,
                                status=PositionStatus.CORRECTED,
                                corrected_summary_json=corrected,
                                updated_at=now,
                            )
                            self._position_repo.save(updated_pos)

                            prev_pv = self._revision_repo.get_current_position_version(
                                position_id
                            )
                            next_ver = self._revision_repo.max_position_version(position_id) + 1
                            pv = PositionVersion(
                                id=_new_id(),
                                position_id=position_id,
                                version=next_ver,
                                aisle_id=command.aisle_id,
                                asset_id=item.asset_id,
                                internal_code=code,
                                quantity=qty,
                                result_id=result_id,
                                is_current=True,
                                supersedes_position_version_id=(
                                    prev_pv.id if prev_pv else None
                                ),
                                revision_id=revision.id,
                                revision_item_id=item.id,
                                created_by=command.applied_by,
                                created_at=now,
                                content_hash=_sha(position_id, code, str(qty), str(next_ver)),
                            )
                            self._revision_repo.save_position_version(
                                pv, supersede_current=True
                            )
                            new_position_by_asset[item.asset_id] = position_id

                applied_count += 1
                fin_items.append(
                    AuthoritativeAisleFinalizationItem(
                        id=_new_id(),
                        finalization_id="",
                        asset_id=item.asset_id,
                        authoritative_result_id=result_id,
                        position_id=position_id,
                        item_status=AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value,
                        created_at=now,
                    )
                )

            new_fin_id = _new_id()
            fin_items = [
                AuthoritativeAisleFinalizationItem(
                    **{**fi.__dict__, "finalization_id": new_fin_id}
                )
                for fi in fin_items
            ]
            content_payload = {
                "revision_id": revision.id,
                "apply_id": apply_id,
                "base_finalization_id": revision.base_finalization_id,
                "items": [
                    {
                        "asset_id": fi.asset_id,
                        "result_id": fi.authoritative_result_id,
                        "position_id": fi.position_id,
                        "status": fi.item_status,
                    }
                    for fi in fin_items
                ],
            }
            content_hash = hashlib.sha256(
                json.dumps(content_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            new_version = self._finalization_repo.max_version_for_aisle(command.aisle_id) + 1
            new_fin = AuthoritativeAisleFinalization(
                id=new_fin_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                capture_session_id=current.capture_session_id,
                finalization_version=new_version,
                status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
                total_assets=len(items),
                applied_assets=applied_count,
                excluded_assets=excluded_count,
                position_count=sum(1 for fi in fin_items if fi.position_id),
                expected_asset_count=len(items),
                content_hash=content_hash,
                confirmed_by=command.applied_by,
                confirmed_at=now,
                completed_at=now,
                is_current=True,
                row_version=1,
                created_at=now,
                updated_at=now,
                supersedes_finalization_id=current.id,
                revision_id=revision.id,
            )

            self._finalization_repo.save_finalization(
                finalization=new_fin,
                items=fin_items,
                supersede_current=True,
            )

            completed = AisleRevision(
                **{
                    **applying.__dict__,
                    "status": AisleRevisionStatus.COMPLETED.value,
                    "new_finalization_id": new_fin_id,
                    "completed_at": now,
                    "updated_at": now,
                    "row_version": applying.row_version + 1,
                }
            )
            saved = self._revision_repo.save_revision(completed)
            logger.info(
                "aisle_revision_completed revision_id=%s new_finalization_id=%s "
                "changed=%s",
                revision.id,
                new_fin_id,
                len(changed),
            )
            return saved
        except AisleRevisionStaleError:
            raise
        except Exception:
            logger.exception(
                "aisle_revision_apply_failed revision_id=%s", command.revision_id
            )
            failed = AisleRevision(
                **{
                    **revision.__dict__,
                    "status": AisleRevisionStatus.FAILED.value,
                    "apply_id": apply_id,
                    "failed_at": self._now(),
                    "failure_code": "APPLY_FAILED",
                    "failure_message": "Apply failed; no partial publish intended",
                    "updated_at": self._now(),
                    "row_version": revision.row_version + 1,
                }
            )
            try:
                self._revision_repo.save_revision(failed)
            except Exception:
                logger.exception("failed to mark revision FAILED")
            raise
        finally:
            self._revision_repo.release_lock(
                aisle_id=command.aisle_id, owner_token=owner, now=self._now()
            )


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
        update_item,
    ) -> None:
        self._enabled = enabled
        self._create = create_revision
        self._apply = apply_revision
        self._finalization_repo = finalization_repo
        self._revision_repo = revision_repo
        self._update_item = update_item

    def execute(self, command: CreateRollbackCommand) -> AisleRevision:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")

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

        # Rebuild item proposals from target finalization items (not by reactivating history).
        from src.application.use_cases.aisles.manage_aisle_revisions import (
            UpdateAisleRevisionItemCommand,
        )

        target_items = list(self._finalization_repo.list_items(target.id))
        for ti in target_items:
            if ti.item_status == AuthoritativeFinalizationItemStatus.EXCLUDED.value:
                self._update_item.execute(
                    UpdateAisleRevisionItemCommand(
                        inventory_id=command.inventory_id,
                        aisle_id=command.aisle_id,
                        revision_id=revision.id,
                        asset_id=ti.asset_id,
                        actor_id=command.requested_by,
                        exclusion_action="EXCLUDE",
                        reason=command.reason,
                    )
                )
                continue
            code = None
            qty = None
            if ti.authoritative_result_id:
                res = self._apply._authoritative_repo.get_by_id(ti.authoritative_result_id)
                if res is not None:
                    code, qty = res.internal_code, res.quantity
            if not code:
                continue
            item = self._revision_repo.get_item(
                revision_id=revision.id, asset_id=ti.asset_id
            )
            if item is None:
                continue
            # Mark as rolled back proposal
            now = _utcnow()
            updated = item.__class__(
                **{
                    **item.__dict__,
                    "proposed_internal_code": code,
                    "proposed_quantity": qty,
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
