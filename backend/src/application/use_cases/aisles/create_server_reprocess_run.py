"""Create a server reprocess run with immutable scope snapshot (Phase 7)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.ports.server_reprocess_repository import ServerReprocessRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.server_reprocess_position_snapshot import (
    ServerReprocessPositionSnapshotQuery,
)
from src.domain.assets.entities import SourceAsset
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.server_reprocess.entities import (
    ServerReprocessProcessingMode,
    ServerReprocessReviewStatus,
    ServerReprocessRun,
    ServerReprocessRunAsset,
    ServerReprocessRunStatus,
    ServerReprocessRunType,
    ServerReprocessScopeType,
)

logger = logging.getLogger(__name__)

SERVER_REPROCESS_DISABLED = "SERVER_REPROCESS_DISABLED"
SERVER_REPROCESS_INVALID_SCOPE = "SERVER_REPROCESS_INVALID_SCOPE"
SERVER_REPROCESS_UNSUPPORTED_MODE = "SERVER_REPROCESS_UNSUPPORTED_MODE"
SERVER_REPROCESS_REQUEST_CONFLICT = "SERVER_REPROCESS_REQUEST_CONFLICT"
SERVER_REPROCESS_EMPTY_SCOPE = "SERVER_REPROCESS_EMPTY_SCOPE"
SERVER_REPROCESS_LOCK = "SERVER_REPROCESS_LOCK"
SERVER_REPROCESS_ASSET_NOT_IN_AISLE = "SERVER_REPROCESS_ASSET_NOT_IN_AISLE"

LOCK_LEASE_SECONDS = 30


class ServerReprocessDisabledError(Exception):
    def __init__(self, message: str = "Server reprocess is disabled") -> None:
        super().__init__(message)
        self.error_code = SERVER_REPROCESS_DISABLED


class ServerReprocessInvalidScopeError(Exception):
    def __init__(self, message: str, *, error_code: str = SERVER_REPROCESS_INVALID_SCOPE) -> None:
        super().__init__(message)
        self.error_code = error_code


class ServerReprocessUnsupportedModeError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = SERVER_REPROCESS_UNSUPPORTED_MODE


class ServerReprocessRequestConflictError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = SERVER_REPROCESS_REQUEST_CONFLICT


class ServerReprocessLockError(Exception):
    def __init__(self, message: str = "Could not acquire aisle reprocess lock") -> None:
        super().__init__(message)
        self.error_code = SERVER_REPROCESS_LOCK


class _AssetRepo(Protocol):
    def list_by_aisle(self, aisle_id: str) -> list[SourceAsset]: ...


class _AuthRepo(Protocol):
    def get_current_for_asset(
        self, asset_id: str
    ) -> AuthoritativeLocalCodeScanResult | None: ...


class _PositionRepo(Protocol):
    def list_by_aisle(self, aisle_id: str) -> list[Any]: ...


@dataclass(frozen=True)
class CreateServerReprocessCommand:
    inventory_id: str
    aisle_id: str
    request_id: str
    scope_type: str
    asset_ids: tuple[str, ...]
    processing_mode: str
    reason: str
    requested_by: str
    source_session_id: str | None = None
    company_id: str | None = None
    pipeline_version: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    supplier_profile_id: str | None = None


@dataclass(frozen=True)
class CreateServerReprocessResult:
    run: ServerReprocessRun
    replayed: bool
    initial_server_processing: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CreateServerReprocessRun:
    """Snapshot scope + prior authority; never mutates current results."""

    def __init__(
        self,
        *,
        enabled: bool,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        asset_repo: _AssetRepo,
        reprocess_repo: ServerReprocessRepository,
        authoritative_repo: _AuthRepo | None = None,
        position_repo: _PositionRepo | None = None,
        allowed_modes: frozenset[str] | None = None,
        clock: Any = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._repo = reprocess_repo
        self._auth_repo = authoritative_repo
        self._position_repo = position_repo
        self._allowed_modes = allowed_modes or frozenset(
            m.value for m in ServerReprocessProcessingMode
        )
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return _utcnow()

    def execute(self, command: CreateServerReprocessCommand) -> CreateServerReprocessResult:
        if not self._enabled:
            raise ServerReprocessDisabledError()

        request_id = (command.request_id or "").strip()
        if not request_id:
            raise ServerReprocessInvalidScopeError(
                "request_id is required", error_code=SERVER_REPROCESS_INVALID_SCOPE
            )

        existing = self._repo.get_run_by_request_id(request_id)
        if existing is not None:
            if not self._same_request_payload(existing, command):
                raise ServerReprocessRequestConflictError(
                    "request_id already used with a different payload"
                )
            return CreateServerReprocessResult(
                run=existing,
                replayed=True,
                initial_server_processing=(
                    existing.run_type == ServerReprocessRunType.INITIAL_SERVER_PROCESSING.value
                ),
            )

        if self._inventory_repo.get_by_id(command.inventory_id) is None:
            raise InventoryNotFoundError(command.inventory_id)
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
        )

        mode = (command.processing_mode or "").strip().upper()
        if mode not in self._allowed_modes:
            raise ServerReprocessUnsupportedModeError(f"Unsupported processing_mode: {mode}")

        try:
            scope_type = ServerReprocessScopeType((command.scope_type or "").strip().upper())
        except ValueError as exc:
            raise ServerReprocessInvalidScopeError(
                f"Invalid scope type: {command.scope_type}"
            ) from exc

        aisle_assets = list(self._asset_repo.list_by_aisle(command.aisle_id))
        selected = self._resolve_scope(
            scope_type=scope_type,
            requested_ids=list(command.asset_ids),
            aisle_assets=aisle_assets,
            aisle_id=command.aisle_id,
        )
        if not selected:
            raise ServerReprocessInvalidScopeError(
                "Resolved scope is empty", error_code=SERVER_REPROCESS_EMPTY_SCOPE
            )

        positions_by_asset = ServerReprocessPositionSnapshotQuery(
            position_repo=self._position_repo
        ).map_by_asset(command.aisle_id)

        prior_count = 0
        snapshot_assets: list[dict[str, Any]] = []
        run_assets: list[ServerReprocessRunAsset] = []
        now = self._now()
        run_id = str(uuid.uuid4())

        for asset in selected:
            auth = (
                self._auth_repo.get_current_for_asset(asset.id)
                if self._auth_repo is not None
                else None
            )
            pos = positions_by_asset.get(asset.id)
            prev_result_id = auth.id if auth is not None else (pos.active_result_id if pos else None)
            prev_position_id = pos.position_id if pos is not None else None
            prev_code: str | None = None
            prev_qty: float | None = None
            prev_resolved = False
            if auth is not None:
                prev_code = (auth.internal_code or "").strip() or None
                prev_qty = float(auth.quantity) if auth.quantity is not None else None
                prev_resolved = bool(prev_code) and auth.applied_at is not None
                prior_count += 1
            elif pos is not None:
                prev_code = pos.internal_code
                prev_qty = pos.quantity
                prev_resolved = bool(prev_code)
                if prev_resolved:
                    prior_count += 1

            asset_hash = hashlib.sha256(
                f"{asset.id}:{getattr(asset, 'storage_path', '')}".encode()
            ).hexdigest()[:32]
            snapshot_assets.append(
                {
                    "asset_id": asset.id,
                    "asset_hash": asset_hash,
                    "previous_result_id": prev_result_id,
                    "previous_position_id": prev_position_id,
                    "previous_internal_code": prev_code,
                    "previous_quantity": prev_qty,
                    "previous_resolved": prev_resolved,
                }
            )
            run_assets.append(
                ServerReprocessRunAsset(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    asset_id=asset.id,
                    asset_hash=asset_hash,
                    previous_result_id=prev_result_id,
                    previous_position_id=prev_position_id,
                    previous_internal_code=prev_code,
                    previous_quantity=prev_qty,
                    previous_resolved=prev_resolved,
                    created_at=now,
                )
            )

        has_prior = prior_count > 0
        run_type = (
            ServerReprocessRunType.SERVER_REPROCESS.value
            if has_prior
            else ServerReprocessRunType.INITIAL_SERVER_PROCESSING.value
        )
        scope_json = {
            "type": scope_type.value,
            "asset_ids": [a.id for a in selected],
        }
        snapshot_json = {
            "asset_ids": [a.id for a in selected],
            "assets": snapshot_assets,
            "processing_mode": mode,
            "supplier_profile_id": command.supplier_profile_id,
            "prompt_version": command.prompt_version,
            "pipeline_version": command.pipeline_version,
            "requested_by": command.requested_by,
            "aisle_status": getattr(getattr(aisle, "status", None), "value", str(getattr(aisle, "status", ""))),
        }

        owner = str(uuid.uuid4())
        expires = now + timedelta(seconds=LOCK_LEASE_SECONDS)
        if not self._repo.try_acquire_lock(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            owner_token=owner,
            expires_at=expires,
        ):
            raise ServerReprocessLockError()

        try:
            run = ServerReprocessRun(
                id=run_id,
                request_id=request_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                source_session_id=command.source_session_id,
                company_id=command.company_id,
                run_type=run_type,
                strategy=None,
                scope_type=scope_type.value,
                scope_json=scope_json,
                snapshot_json=snapshot_json,
                processing_mode=mode,
                reason=(command.reason or "USER_REQUESTED_REPROCESS").strip()
                or "USER_REQUESTED_REPROCESS",
                status=ServerReprocessRunStatus.REQUESTED.value,
                review_status=ServerReprocessReviewStatus.NOT_REVIEWED.value,
                requested_by=command.requested_by,
                requested_at=now,
                started_at=None,
                completed_at=None,
                canceled_at=None,
                failed_at=None,
                failure_code=None,
                failure_message=None,
                pipeline_version=command.pipeline_version,
                model_version=command.model_version,
                prompt_version=command.prompt_version,
                supplier_profile_id=command.supplier_profile_id,
                linked_job_id=None,
                has_prior_authority=has_prior,
                row_version=1,
                created_at=now,
                updated_at=now,
            )
            saved = self._repo.save_run(run=run, assets=run_assets)
            logger.info(
                "server_reprocess_requested run_id=%s request_id=%s aisle_id=%s "
                "scope=%s mode=%s assets=%s prior=%s",
                saved.id,
                saved.request_id,
                saved.aisle_id,
                saved.scope_type,
                saved.processing_mode,
                len(run_assets),
                has_prior,
            )
            return CreateServerReprocessResult(
                run=saved,
                replayed=False,
                initial_server_processing=not has_prior,
            )
        finally:
            self._repo.release_lock(aisle_id=command.aisle_id, owner_token=owner)

    def _same_request_payload(
        self, existing: ServerReprocessRun, command: CreateServerReprocessCommand
    ) -> bool:
        scope_type = (command.scope_type or "").strip().upper()
        mode = (command.processing_mode or "").strip().upper()
        ids = sorted(a.strip() for a in command.asset_ids if a and a.strip())
        existing_ids = sorted(existing.scope_json.get("asset_ids") or [])
        return (
            existing.inventory_id == command.inventory_id
            and existing.aisle_id == command.aisle_id
            and existing.scope_type == scope_type
            and existing.processing_mode == mode
            and (
                scope_type != ServerReprocessScopeType.SELECTED_ASSETS.value
                or existing_ids == ids
            )
        )

    def _resolve_scope(
        self,
        *,
        scope_type: ServerReprocessScopeType,
        requested_ids: list[str],
        aisle_assets: list[SourceAsset],
        aisle_id: str,
    ) -> list[SourceAsset]:
        by_id = {a.id: a for a in aisle_assets}
        if scope_type == ServerReprocessScopeType.FULL_AISLE:
            return list(aisle_assets)

        if scope_type == ServerReprocessScopeType.SELECTED_ASSETS:
            if not requested_ids:
                raise ServerReprocessInvalidScopeError(
                    "SELECTED_ASSETS requires asset_ids"
                )
            selected: list[SourceAsset] = []
            for raw in requested_ids:
                aid = (raw or "").strip()
                asset = by_id.get(aid)
                if asset is None:
                    raise ServerReprocessInvalidScopeError(
                        f"Asset {aid} not in aisle {aisle_id}",
                        error_code=SERVER_REPROCESS_ASSET_NOT_IN_AISLE,
                    )
                selected.append(asset)
            return selected

        # Filter scopes need prior authority / position signals
        snaps = ServerReprocessPositionSnapshotQuery(
            position_repo=self._position_repo
        ).map_by_asset(aisle_id)

        selected = []
        for asset in aisle_assets:
            auth = (
                self._auth_repo.get_current_for_asset(asset.id)
                if self._auth_repo is not None
                else None
            )
            pos = snaps.get(asset.id)
            if scope_type == ServerReprocessScopeType.FAILED_ONLY:
                failed = False
                if auth is not None and not (auth.internal_code or "").strip():
                    failed = True
                if pos is not None and pos.status == "deleted":
                    failed = True
                if auth is None and pos is None:
                    failed = True
                if failed:
                    selected.append(asset)
            elif scope_type == ServerReprocessScopeType.UNRECOGNIZED_ONLY:
                code = None
                if auth is not None:
                    code = (auth.internal_code or "").strip() or None
                elif pos is not None:
                    code = pos.internal_code
                if not code:
                    selected.append(asset)
            elif scope_type == ServerReprocessScopeType.PENDING_REVIEW_ONLY:
                if pos is not None and bool(pos.needs_review):
                    selected.append(asset)
                elif auth is not None and auth.applied_at is None:
                    selected.append(asset)
        return selected
