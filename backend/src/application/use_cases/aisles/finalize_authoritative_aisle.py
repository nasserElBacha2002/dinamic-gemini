"""Finalize an aisle using local authoritative CODE_SCAN results (Phase 6).

Does not enqueue remote CODE_SCAN / OCR / fallback. Requires every photo asset to be
CONFIRMED_AND_APPLIED or EXCLUDED (backend readiness). Idempotent on finalization_id.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from src.application.errors import InventoryNotFoundError
from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.evaluate_authoritative_aisle_readiness import (
    EvaluateAuthoritativeAisleReadiness,
    position_source_asset_id,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.assets.entities import SourceAssetType
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
    AuthoritativeAisleReadinessStatus,
    AuthoritativeFinalizationItemStatus,
    AuthoritativeFinalizationStatus,
    AuthoritativeReadinessReason,
)

logger = logging.getLogger(__name__)

LOCK_LEASE_SECONDS = 90

AUTH_FINALIZATION_DISABLED = "AUTHORITATIVE_FINALIZATION_DISABLED"
AUTH_FINALIZATION_NOT_READY = "AUTHORITATIVE_FINALIZATION_NOT_READY"
AUTH_FINALIZATION_CONFLICT = "AUTHORITATIVE_FINALIZATION_CONFLICT"
AUTH_FINALIZATION_LOCK = "AUTHORITATIVE_FINALIZATION_LOCK"
AUTH_FINALIZATION_COUNT_MISMATCH = "AUTHORITATIVE_FINALIZATION_COUNT_MISMATCH"


class AuthoritativeFinalizationDisabledError(Exception):
    def __init__(self, message: str = "Authoritative aisle finalization is disabled") -> None:
        super().__init__(message)
        self.error_code = AUTH_FINALIZATION_DISABLED


class AuthoritativeFinalizationNotReadyError(Exception):
    def __init__(self, message: str, *, reasons: tuple[str, ...]) -> None:
        super().__init__(message)
        self.error_code = AUTH_FINALIZATION_NOT_READY
        self.reasons = reasons


class AuthoritativeFinalizationConflictError(Exception):
    def __init__(self, message: str, *, error_code: str = AUTH_FINALIZATION_CONFLICT) -> None:
        super().__init__(message)
        self.error_code = error_code


class AuthoritativeFinalizationLockError(Exception):
    def __init__(self, message: str = "Could not acquire aisle finalization lock") -> None:
        super().__init__(message)
        self.error_code = AUTH_FINALIZATION_LOCK


@dataclass(frozen=True)
class FinalizeAuthoritativeAisleCommand:
    inventory_id: str
    aisle_id: str
    finalization_id: str
    expected_asset_count: int
    client_session_id: str | None
    confirmed_by_user_id: str


@dataclass(frozen=True)
class FinalizeAuthoritativeAisleResult:
    finalization_id: str
    status: str
    aisle_status: str
    total_assets: int
    applied_assets: int
    excluded_assets: int
    position_count: int
    idempotent_replay: bool


class FinalizeAuthoritativeAisle:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        asset_repo: SourceAssetRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        readiness: EvaluateAuthoritativeAisleReadiness,
        status_reconciler: InventoryStatusReconciler,
        clock: Clock,
        position_repo: PositionRepository | None = None,
        enabled: bool,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._asset_repo = asset_repo
        self._auth_repo = authoritative_repo
        self._fin_repo = finalization_repo
        self._readiness = readiness
        self._status_reconciler = status_reconciler
        self._clock = clock
        self._position_repo = position_repo
        self._enabled = enabled

    def execute(self, command: FinalizeAuthoritativeAisleCommand) -> FinalizeAuthoritativeAisleResult:
        if not self._enabled:
            raise AuthoritativeFinalizationDisabledError()

        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory {command.inventory_id} not found")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )

        existing = self._fin_repo.get_by_id(command.finalization_id)
        if existing is not None:
            return self._replay_or_conflict(existing, command)

        current = self._fin_repo.get_current_for_aisle(command.aisle_id)
        if (
            current is not None
            and current.status == AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value
        ):
            # Already finalized under a different id — reject new close.
            raise AuthoritativeFinalizationConflictError(
                "Aisle already finalized by local authority",
                error_code=AUTH_FINALIZATION_CONFLICT,
            )

        now = self._clock.now()
        owner = f"fin:{command.finalization_id}"
        acquired = self._fin_repo.try_acquire_lock(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            owner_token=owner,
            lease_expires_at=now + timedelta(seconds=LOCK_LEASE_SECONDS),
            now=now,
        )
        if not acquired:
            raise AuthoritativeFinalizationLockError()

        try:
            readiness = self._readiness.execute(
                inventory_id=command.inventory_id, aisle_id=command.aisle_id
            )
            if readiness.status != AuthoritativeAisleReadinessStatus.READY or not readiness.can_finalize:
                raise AuthoritativeFinalizationNotReadyError(
                    "Aisle is not ready for authoritative finalization",
                    reasons=readiness.reasons,
                )

            if int(command.expected_asset_count) != int(readiness.total_images):
                raise AuthoritativeFinalizationConflictError(
                    "expected_asset_count does not match server total_images",
                    error_code=AUTH_FINALIZATION_COUNT_MISMATCH,
                )

            assets = [
                a
                for a in self._asset_repo.list_by_aisle(command.aisle_id)
                if a.type == SourceAssetType.PHOTO
            ]
            exclusions = list(
                self._fin_repo.list_current_exclusions(
                    inventory_id=command.inventory_id, aisle_id=command.aisle_id
                )
            )
            excluded_ids = {e.asset_id for e in exclusions}
            rows = list(
                self._auth_repo.list_current_for_aisle(
                    inventory_id=command.inventory_id, aisle_id=command.aisle_id
                )
            )
            by_asset = {r.asset_id: r for r in rows}

            position_by_asset: dict[str, str] = dict(readiness.position_ids_by_asset)
            if self._position_repo is not None and not position_by_asset:
                positions = list(self._position_repo.list_by_aisle(command.aisle_id))
                for p in positions:
                    aid = position_source_asset_id(p)
                    pid = getattr(p, "id", None)
                    if aid and pid and aid not in position_by_asset:
                        position_by_asset[str(aid)] = str(pid)

            items: list[AuthoritativeAisleFinalizationItem] = []
            hash_parts: list[str] = []

            for asset in assets:
                if asset.id in excluded_ids:
                    items.append(
                        AuthoritativeAisleFinalizationItem(
                            id=str(uuid.uuid4()),
                            finalization_id=command.finalization_id,
                            asset_id=asset.id,
                            authoritative_result_id=None,
                            position_id=None,
                            item_status=AuthoritativeFinalizationItemStatus.EXCLUDED.value,
                            created_at=now,
                        )
                    )
                    hash_parts.append(f"E:{asset.id}")
                    continue
                row = by_asset[asset.id]
                pos_id = position_by_asset.get(asset.id)
                if self._position_repo is not None and not pos_id:
                    raise AuthoritativeFinalizationNotReadyError(
                        "Applied authoritative result missing position",
                        reasons=(AuthoritativeReadinessReason.POSITION_MISSING.value,),
                    )
                items.append(
                    AuthoritativeAisleFinalizationItem(
                        id=str(uuid.uuid4()),
                        finalization_id=command.finalization_id,
                        asset_id=asset.id,
                        authoritative_result_id=row.id,
                        position_id=pos_id,
                        item_status=AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value,
                        created_at=now,
                    )
                )
                hash_parts.append(f"A:{asset.id}:{row.id}:{row.content_hash}:{pos_id or ''}")

            # Exclusions for assets no longer listed.
            for ex in exclusions:
                if any(i.asset_id == ex.asset_id for i in items):
                    continue
                items.append(
                    AuthoritativeAisleFinalizationItem(
                        id=str(uuid.uuid4()),
                        finalization_id=command.finalization_id,
                        asset_id=ex.asset_id,
                        authoritative_result_id=None,
                        position_id=None,
                        item_status=AuthoritativeFinalizationItemStatus.EXCLUDED.value,
                        created_at=now,
                    )
                )
                hash_parts.append(f"E:{ex.asset_id}")

            hash_parts.sort()
            content_hash = hashlib.sha256("|".join(hash_parts).encode("utf-8")).hexdigest()
            version = self._fin_repo.max_version_for_aisle(command.aisle_id) + 1
            applied_count = sum(
                1
                for i in items
                if i.item_status == AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value
            )
            excluded_count = sum(
                1
                for i in items
                if i.item_status == AuthoritativeFinalizationItemStatus.EXCLUDED.value
            )
            position_count = sum(1 for i in items if i.position_id)

            finalization = AuthoritativeAisleFinalization(
                id=command.finalization_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                capture_session_id=command.client_session_id,
                finalization_version=version,
                status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
                total_assets=readiness.total_images,
                applied_assets=applied_count,
                excluded_assets=excluded_count,
                position_count=position_count,
                expected_asset_count=command.expected_asset_count,
                content_hash=content_hash,
                confirmed_by=command.confirmed_by_user_id,
                confirmed_at=now,
                completed_at=now,
                is_current=True,
                row_version=1,
                created_at=now,
                updated_at=now,
            )
            self._fin_repo.save_finalization(
                finalization=finalization, items=items, supersede_current=True
            )

            aisle.mark_completed(now)
            self._aisle_repo.save(aisle)
            self._status_reconciler.reconcile(command.inventory_id)

            logger.info(
                "authoritative_aisle_finalization_completed finalization_id=%s aisle_id=%s "
                "total=%s applied=%s excluded=%s",
                finalization.id,
                command.aisle_id,
                finalization.total_assets,
                finalization.applied_assets,
                finalization.excluded_assets,
            )
            return FinalizeAuthoritativeAisleResult(
                finalization_id=finalization.id,
                status=finalization.status,
                aisle_status=aisle.status.value,
                total_assets=finalization.total_assets,
                applied_assets=finalization.applied_assets,
                excluded_assets=finalization.excluded_assets,
                position_count=finalization.position_count,
                idempotent_replay=False,
            )
        finally:
            self._fin_repo.release_lock(
                aisle_id=command.aisle_id, owner_token=owner, now=self._clock.now()
            )

    def _replay_or_conflict(
        self,
        existing: AuthoritativeAisleFinalization,
        command: FinalizeAuthoritativeAisleCommand,
    ) -> FinalizeAuthoritativeAisleResult:
        if existing.aisle_id != command.aisle_id or existing.inventory_id != command.inventory_id:
            raise AuthoritativeFinalizationConflictError(
                "finalization_id belongs to a different aisle/inventory"
            )
        if (
            command.expected_asset_count is not None
            and existing.expected_asset_count is not None
            and int(existing.expected_asset_count) != int(command.expected_asset_count)
        ):
            raise AuthoritativeFinalizationConflictError(
                "finalization_id replay with different expected_asset_count"
            )
        if command.client_session_id and existing.capture_session_id:
            if existing.capture_session_id != command.client_session_id:
                raise AuthoritativeFinalizationConflictError(
                    "finalization_id replay with different client_session_id"
                )
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        return FinalizeAuthoritativeAisleResult(
            finalization_id=existing.id,
            status=existing.status,
            aisle_status=aisle.status.value if aisle else "unknown",
            total_assets=existing.total_assets,
            applied_assets=existing.applied_assets,
            excluded_assets=existing.excluded_assets,
            position_count=existing.position_count,
            idempotent_replay=True,
        )
