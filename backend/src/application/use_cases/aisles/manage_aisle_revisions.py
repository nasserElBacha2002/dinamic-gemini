"""Create / update / cancel / list / diff aisle revisions (Phase 8)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.application.ports.aisle_revision_repository import AisleRevisionRepository
from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_revision_snapshot import (
    RevisionSnapshot,
    RevisionSnapshotAsset,
    calculate_revision_diff,
    canonical_revision_content_hash,
    parse_revision_snapshot,
)
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionDiffEntry,
    AisleRevisionItem,
    AisleRevisionItemStatus,
    AisleRevisionProposalSource,
    AisleRevisionStatus,
    AisleRevisionType,
    revision_is_editable,
)
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeFinalizationStatus,
)
from src.domain.assets.entities import SourceAssetType

logger = logging.getLogger(__name__)

_LOCK_LEASE = timedelta(seconds=30)


class AisleRevisionDisabledError(Exception):
    error_code = "AISLE_REVISIONS_DISABLED"


class AisleRevisionNotFoundError(Exception):
    error_code = "AISLE_REVISION_NOT_FOUND"


class AisleRevisionConflictError(Exception):
    def __init__(self, message: str, *, error_code: str = "AISLE_REVISION_CONFLICT") -> None:
        super().__init__(message)
        self.error_code = error_code


class AisleRevisionNotEditableError(Exception):
    error_code = "AISLE_REVISION_NOT_EDITABLE"


class AisleNotFinalizedError(Exception):
    error_code = "AISLE_NOT_FINALIZED"


class AisleRevisionLockError(Exception):
    error_code = "AISLE_REVISION_LOCK"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _position_asset_id(position) -> str | None:
    summary = getattr(position, "detected_summary_json", None) or {}
    if not isinstance(summary, dict):
        return None
    aid = summary.get("source_asset_id") or summary.get("source_image_id")
    return str(aid) if aid else None


def _position_code_qty(position) -> tuple[str | None, int | None]:
    corrected = getattr(position, "corrected_summary_json", None) or {}
    detected = getattr(position, "detected_summary_json", None) or {}
    src = corrected if isinstance(corrected, dict) and corrected else detected
    if not isinstance(src, dict):
        return None, None
    code = src.get("internal_code") or src.get("code")
    qty = src.get("quantity")
    try:
        qty_i = int(qty) if qty is not None else None
    except (TypeError, ValueError):
        qty_i = None
    return (str(code) if code else None), qty_i


@dataclass(frozen=True)
class CreateAisleRevisionCommand:
    inventory_id: str
    aisle_id: str
    revision_id: str
    revision_type: str
    reason: str
    requested_by: str
    target_finalization_id: str | None = None  # for ROLLBACK prep via create


@dataclass(frozen=True)
class UpdateAisleRevisionItemCommand:
    inventory_id: str
    aisle_id: str
    revision_id: str
    asset_id: str
    actor_id: str
    internal_code: str | None = None
    quantity: int | None = None
    exclusion_action: str | None = None  # EXCLUDE | RESTORE | None
    reason: str | None = None
    proposal_source: str | None = None
    proposal_reference_id: str | None = None


class CreateAisleRevision:
    def __init__(
        self,
        *,
        enabled: bool,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        position_repo: PositionRepository,
        revision_repo: AisleRevisionRepository,
        clock=None,
    ) -> None:
        self._enabled = enabled
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._finalization_repo = finalization_repo
        self._authoritative_repo = authoritative_repo
        self._position_repo = position_repo
        self._revision_repo = revision_repo
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None and hasattr(self._clock, "now"):
            return self._clock.now()
        return _utcnow()

    def execute(self, command: CreateAisleRevisionCommand) -> tuple[AisleRevision, bool]:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        revision_id = (command.revision_id or "").strip()
        if not revision_id:
            raise AisleRevisionConflictError(
                "revision_id is required", error_code="AISLE_REVISION_INVALID"
            )
        reason = (command.reason or "").strip()
        if not reason:
            raise AisleRevisionConflictError(
                "reason is required", error_code="AISLE_REVISION_INVALID"
            )
        revision_type = (command.revision_type or "").strip()
        if revision_type not in {t.value for t in AisleRevisionType}:
            raise AisleRevisionConflictError(
                f"Unsupported revision_type: {revision_type}",
                error_code="AISLE_REVISION_INVALID_TYPE",
            )

        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            from src.application.errors import InventoryNotFoundError

            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")

        existing = self._revision_repo.get_revision(revision_id)
        if existing is not None:
            expected_hash = canonical_revision_content_hash(
                revision_id=revision_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                base_finalization_id=existing.base_finalization_id,
                revision_type=revision_type,
                reason=reason,
                snapshot_json=existing.snapshot_json,
            )
            if (
                existing.inventory_id == command.inventory_id
                and existing.aisle_id == command.aisle_id
                and existing.revision_type == revision_type
                and existing.reason == reason
                and existing.content_hash == expected_hash
            ):
                return existing, True
            raise AisleRevisionConflictError(
                "revision_id already used with different content",
                error_code="AISLE_REVISION_REQUEST_CONFLICT",
            )

        open_rev = self._revision_repo.get_open_revision_for_aisle(command.aisle_id)
        if open_rev is not None:
            raise AisleRevisionConflictError(
                f"Aisle already has open revision {open_rev.id}",
                error_code="AISLE_REVISION_OPEN_EXISTS",
            )

        current = self._finalization_repo.get_current_for_aisle(command.aisle_id)
        if current is None or current.status != (
            AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value
        ):
            raise AisleNotFinalizedError(
                "Aisle must have a completed authoritative finalization before revision"
            )

        if command.target_finalization_id:
            target = self._finalization_repo.get_by_id(command.target_finalization_id)
            if target is None or target.aisle_id != command.aisle_id:
                raise AisleRevisionConflictError(
                    "target_finalization_id not found for aisle",
                    error_code="AISLE_REVISION_INVALID_TARGET",
                )

        now = self._now()
        owner = f"rev-create-{revision_id[:8]}"
        if not self._revision_repo.try_acquire_lock(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            owner_token=owner,
            lease_expires_at=now + _LOCK_LEASE,
            now=now,
        ):
            raise AisleRevisionLockError("Could not acquire aisle revision lock")
        try:
            snapshot = self._build_snapshot(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                finalization=current,
            )
            snapshot_json = snapshot.to_json()
            content_hash = canonical_revision_content_hash(
                revision_id=revision_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                base_finalization_id=current.id,
                revision_type=revision_type,
                reason=reason,
                snapshot_json=snapshot_json,
            )
            items = [
                AisleRevisionItem(
                    id=_new_id(),
                    revision_id=revision_id,
                    asset_id=a.asset_id,
                    base_result_id=a.base_result_id,
                    base_position_id=a.base_position_id,
                    proposed_internal_code=a.base_internal_code,
                    proposed_quantity=a.base_quantity,
                    proposed_exclusion_state="KEEP" if not a.excluded else "EXCLUDE",
                    proposal_source=AisleRevisionProposalSource.UNCHANGED.value,
                    proposal_reference_id=None,
                    change_reason=None,
                    item_status=(
                        AisleRevisionItemStatus.EXCLUDED.value
                        if a.excluded
                        else AisleRevisionItemStatus.UNCHANGED.value
                    ),
                    created_at=now,
                    updated_at=now,
                )
                for a in snapshot.assets
            ]
            revision = AisleRevision(
                id=revision_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                base_finalization_id=current.id,
                new_finalization_id=None,
                revision_type=revision_type,
                status=AisleRevisionStatus.OPEN.value,
                reason=reason,
                requested_by=command.requested_by,
                requested_at=now,
                started_at=now,
                completed_at=None,
                canceled_at=None,
                failed_at=None,
                failure_code=None,
                failure_message=None,
                apply_id=None,
                snapshot_json=snapshot_json,
                content_hash=content_hash,
                row_version=1,
                created_at=now,
                updated_at=now,
            )
            saved = self._revision_repo.save_revision(revision, items=items)
            logger.info(
                "aisle_revision_created revision_id=%s aisle_id=%s type=%s assets=%s",
                revision_id,
                command.aisle_id,
                revision_type,
                len(items),
            )
            return saved, False
        finally:
            self._revision_repo.release_lock(
                aisle_id=command.aisle_id, owner_token=owner, now=self._now()
            )

    def _build_snapshot(self, *, inventory_id: str, aisle_id: str, finalization) -> RevisionSnapshot:
        fin_items = list(self._finalization_repo.list_items(finalization.id))
        exclusions = list(
            self._finalization_repo.list_current_exclusions(
                inventory_id=inventory_id, aisle_id=aisle_id
            )
        )
        excl_by_asset = {e.asset_id: e for e in exclusions if e.is_current}
        results = {
            r.asset_id: r
            for r in self._authoritative_repo.list_current_for_aisle(
                inventory_id=inventory_id, aisle_id=aisle_id
            )
        }
        positions = list(self._position_repo.list_by_aisle(aisle_id))
        pos_by_asset: dict[str, object] = {}
        for p in positions:
            aid = _position_asset_id(p)
            if aid:
                pos_by_asset.setdefault(aid, p)

        assets = [
            a
            for a in self._asset_repo.list_by_aisle(aisle_id)
            if a.type == SourceAssetType.PHOTO
        ]
        # Prefer finalization item order; fall back to all photos.
        asset_ids_ordered: list[str] = []
        seen: set[str] = set()
        for fi in fin_items:
            if fi.asset_id not in seen:
                asset_ids_ordered.append(fi.asset_id)
                seen.add(fi.asset_id)
        for a in assets:
            if a.id not in seen:
                asset_ids_ordered.append(a.id)
                seen.add(a.id)

        fi_by_asset = {fi.asset_id: fi for fi in fin_items}
        snap_assets: list[RevisionSnapshotAsset] = []
        base_result_ids: list[str] = []
        base_position_ids: list[str] = []
        for aid in asset_ids_ordered:
            fi = fi_by_asset.get(aid)
            result = results.get(aid)
            position = pos_by_asset.get(aid)
            code, qty = (None, None)
            if result is not None:
                code, qty = result.internal_code, result.quantity
            elif position is not None:
                code, qty = _position_code_qty(position)
            base_result_id = (
                fi.authoritative_result_id
                if fi and fi.authoritative_result_id
                else (result.id if result else None)
            )
            base_position_id = (
                fi.position_id
                if fi and fi.position_id
                else (getattr(position, "id", None) if position else None)
            )
            if base_result_id:
                base_result_ids.append(base_result_id)
            if base_position_id:
                base_position_ids.append(base_position_id)
            snap_assets.append(
                RevisionSnapshotAsset(
                    asset_id=aid,
                    base_result_id=base_result_id,
                    base_position_id=base_position_id,
                    base_internal_code=code,
                    base_quantity=qty,
                    excluded=aid in excl_by_asset
                    or (
                        fi is not None
                        and fi.item_status == "EXCLUDED"
                    ),
                )
            )
        return RevisionSnapshot(
            base_finalization_id=finalization.id,
            base_finalization_version=int(finalization.finalization_version),
            base_result_ids=tuple(base_result_ids),
            base_position_ids=tuple(base_position_ids),
            base_exclusion_ids=tuple(e.id for e in exclusions if e.is_current),
            asset_ids=tuple(asset_ids_ordered),
            assets=tuple(snap_assets),
        )


class UpdateAisleRevisionItem:
    def __init__(self, *, enabled: bool, revision_repo: AisleRevisionRepository) -> None:
        self._enabled = enabled
        self._revision_repo = revision_repo

    def execute(self, command: UpdateAisleRevisionItemCommand) -> AisleRevisionItem:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        revision = self._revision_repo.get_revision(command.revision_id)
        if revision is None:
            raise AisleRevisionNotFoundError(f"Revision not found: {command.revision_id}")
        if (
            revision.inventory_id != command.inventory_id
            or revision.aisle_id != command.aisle_id
        ):
            raise AisleRevisionNotFoundError("Revision not in aisle scope")
        if not revision_is_editable(revision.status):
            raise AisleRevisionNotEditableError(
                f"Revision status {revision.status} is not editable"
            )
        item = self._revision_repo.get_item(
            revision_id=command.revision_id, asset_id=command.asset_id
        )
        if item is None:
            raise AisleRevisionConflictError(
                "Asset not in revision snapshot",
                error_code="AISLE_REVISION_ASSET_NOT_IN_SCOPE",
            )

        now = _utcnow()
        exclusion = (command.exclusion_action or "").strip().upper() or None
        if exclusion == "EXCLUDE":
            if not (command.reason or "").strip():
                raise AisleRevisionConflictError(
                    "Exclusion reason is required",
                    error_code="AISLE_REVISION_INVALID",
                )
            updated = AisleRevisionItem(
                **{
                    **item.__dict__,
                    "proposed_exclusion_state": "EXCLUDE",
                    "proposal_source": AisleRevisionProposalSource.EXCLUSION_CHANGE.value,
                    "change_reason": (command.reason or "").strip(),
                    "item_status": AisleRevisionItemStatus.EXCLUDED.value,
                    "updated_at": now,
                }
            )
        elif exclusion == "RESTORE":
            if not item.base_result_id:
                raise AisleRevisionConflictError(
                    "Cannot restore without base result",
                    error_code="AISLE_REVISION_INVALID",
                )
            updated = AisleRevisionItem(
                **{
                    **item.__dict__,
                    "proposed_exclusion_state": "RESTORE",
                    "proposal_source": AisleRevisionProposalSource.EXCLUSION_CHANGE.value,
                    "change_reason": (command.reason or "").strip() or "RESTORE",
                    "item_status": AisleRevisionItemStatus.RESTORED.value,
                    "updated_at": now,
                }
            )
        else:
            code = (command.internal_code or "").strip()
            if not code:
                raise AisleRevisionConflictError(
                    "internal_code is required for manual correction",
                    error_code="AISLE_REVISION_INVALID",
                )
            qty = command.quantity
            if qty is not None and qty < 0:
                raise AisleRevisionConflictError(
                    "quantity must be >= 0",
                    error_code="AISLE_REVISION_INVALID",
                )
            source = (
                command.proposal_source
                or AisleRevisionProposalSource.MANUAL.value
            )
            status = (
                AisleRevisionItemStatus.ADOPT_REMOTE.value
                if source == AisleRevisionProposalSource.SERVER_REPROCESS_PROPOSAL.value
                else AisleRevisionItemStatus.MODIFIED.value
            )
            updated = AisleRevisionItem(
                **{
                    **item.__dict__,
                    "proposed_internal_code": code,
                    "proposed_quantity": qty,
                    "proposed_exclusion_state": "KEEP",
                    "proposal_source": source,
                    "proposal_reference_id": command.proposal_reference_id,
                    "change_reason": (command.reason or "").strip() or None,
                    "item_status": status,
                    "updated_at": now,
                }
            )
        saved = self._revision_repo.save_item(updated)
        logger.info(
            "aisle_revision_item_changed revision_id=%s asset_id=%s status=%s",
            command.revision_id,
            command.asset_id,
            saved.item_status,
        )
        return saved


class CancelAisleRevision:
    def __init__(self, *, enabled: bool, revision_repo: AisleRevisionRepository) -> None:
        self._enabled = enabled
        self._revision_repo = revision_repo

    def execute(
        self, *, inventory_id: str, aisle_id: str, revision_id: str
    ) -> AisleRevision:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        revision = self._revision_repo.get_revision(revision_id)
        if revision is None or revision.inventory_id != inventory_id or revision.aisle_id != aisle_id:
            raise AisleRevisionNotFoundError(f"Revision not found: {revision_id}")
        if not revision_is_editable(revision.status):
            raise AisleRevisionNotEditableError(
                f"Revision status {revision.status} cannot be canceled"
            )
        now = _utcnow()
        canceled = AisleRevision(
            **{
                **revision.__dict__,
                "status": AisleRevisionStatus.CANCELED.value,
                "canceled_at": now,
                "updated_at": now,
                "row_version": revision.row_version + 1,
            }
        )
        return self._revision_repo.save_revision(canceled)


class ListAisleHistory:
    def __init__(
        self,
        *,
        enabled: bool,
        revision_repo: AisleRevisionRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
    ) -> None:
        self._enabled = enabled
        self._revision_repo = revision_repo
        self._finalization_repo = finalization_repo

    def execute(
        self, *, inventory_id: str, aisle_id: str, limit: int = 50
    ) -> list[dict]:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        revisions = self._revision_repo.list_revisions_for_aisle(
            aisle_id=aisle_id, limit=limit
        )
        out: list[dict] = []
        for rev in revisions:
            if rev.inventory_id != inventory_id:
                continue
            items = self._revision_repo.list_items(rev.id)
            changed = sum(
                1
                for i in items
                if i.item_status != AisleRevisionItemStatus.UNCHANGED.value
            )
            out.append(
                {
                    "revision_id": rev.id,
                    "revision_type": rev.revision_type,
                    "status": rev.status,
                    "reason": rev.reason,
                    "requested_by": rev.requested_by,
                    "requested_at": rev.requested_at,
                    "completed_at": rev.completed_at,
                    "base_finalization_id": rev.base_finalization_id,
                    "new_finalization_id": rev.new_finalization_id,
                    "changed_asset_count": changed,
                    "total_assets": len(items),
                }
            )
        return out


class GetAisleRevisionDiff:
    def __init__(self, *, enabled: bool, revision_repo: AisleRevisionRepository) -> None:
        self._enabled = enabled
        self._revision_repo = revision_repo

    def execute(
        self, *, inventory_id: str, aisle_id: str, revision_id: str
    ) -> tuple[AisleRevision, Sequence[AisleRevisionDiffEntry]]:
        if not self._enabled:
            raise AisleRevisionDisabledError("Aisle revisions are disabled")
        revision = self._revision_repo.get_revision(revision_id)
        if revision is None or revision.inventory_id != inventory_id or revision.aisle_id != aisle_id:
            raise AisleRevisionNotFoundError(f"Revision not found: {revision_id}")
        snapshot = parse_revision_snapshot(revision.snapshot_json)
        items = self._revision_repo.list_items(revision_id)
        return revision, calculate_revision_diff(snapshot=snapshot, items=items)
