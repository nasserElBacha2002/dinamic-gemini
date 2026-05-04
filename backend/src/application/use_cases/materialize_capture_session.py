"""Materialize capture-session staged media into SourceAsset rows (Phase 4 bridge)."""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionAlreadyMaterializedError,
    CaptureSessionConfirmLedgerDuplicateError,
    CaptureSessionInvalidIdempotencyKeyError,
    CaptureSessionMaterializationFailedError,
    CaptureSessionMaterializationNotAllowedError,
    CaptureSessionNotFoundError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionConfirmIdempotencyRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_source_asset_materializer import (
    AisleSourceAssetMaterializer,
    validate_staging_media_upload_file,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.assets.entities import SourceAsset
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionConfirmationLedgerEntry,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaterializeCaptureSessionResult:
    session: CaptureSession
    created_asset_ids: tuple[str, ...]
    replayed: bool


@dataclass(frozen=True)
class _MaterializeCommitContext:
    """Internal bundle for the materialize transaction (B8.2 PLR0913)."""

    session: CaptureSession
    session_id: str
    idem: str
    inventory_id: str
    aisle_id: str
    eligible: list[CaptureSessionItem]
    prev_status: CaptureSessionStatus


class MaterializeCaptureSessionUseCase:
    """Idempotent Phase 4 materialization from staging items to SourceAsset rows.

    State gate: only ``ASSIGNMENT_PROPOSED`` can materialize.
    Item gate: only ``IMPORTED`` + ``PROPOSED`` rows are eligible.
    Phase-4 meaning of ``CONFIRMING``: the session is already materialized to ``SourceAsset``
    and locked for additional preview/materialization attempts while future phases define
    final confirmation semantics.
    """

    def __init__(  # noqa: PLR0913 — DI wiring (B8.2)
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        confirm_repo: CaptureSessionConfirmIdempotencyRepository,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        artifact_storage: ArtifactStorage,
        status_reconciler: InventoryStatusReconciler,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._confirm_repo = confirm_repo
        self._asset_repo = asset_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._materializer = AisleSourceAssetMaterializer(
            aisle_repo=aisle_repo,
            asset_repo=asset_repo,
            artifact_storage=artifact_storage,
            status_reconciler=status_reconciler,
        )
        self._aisle_repo = aisle_repo

    def _normalize_idempotency_key(self, idempotency_key: str) -> str:
        idem = (idempotency_key or "").strip()
        if not idem:
            raise CaptureSessionInvalidIdempotencyKeyError("idempotency_key is required")
        return idem

    def _load_session_or_raise(
        self, session_id: str, inventory_id: str, aisle_id: str
    ) -> CaptureSession:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None or session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory and aisle."
            )
        return session

    def _maybe_replay_idempotent(
        self, session: CaptureSession, session_id: str, idem: str
    ) -> MaterializeCaptureSessionResult | None:
        prev = self._confirm_repo.get_by_session_and_key(session_id, idem)
        if prev is None:
            return None
        created_asset_ids = tuple((prev.outcome_json or {}).get("created_asset_ids", []))
        return MaterializeCaptureSessionResult(
            session=session, created_asset_ids=created_asset_ids, replayed=True
        )

    def _validate_session_and_items_for_materialize(
        self, session: CaptureSession, session_id: str
    ) -> list[CaptureSessionItem]:
        if session.status == CaptureSessionStatus.CONFIRMING:
            raise CaptureSessionAlreadyMaterializedError(
                "This capture session is already materialized (confirming)."
            )
        if session.status != CaptureSessionStatus.ASSIGNMENT_PROPOSED:
            raise CaptureSessionMaterializationNotAllowedError(
                "Materialization requires session status assignment_proposed."
            )

        items = list(self._item_repo.list_by_session(session_id))
        eligible = [
            i
            for i in items
            if i.import_status == CaptureSessionItemImportStatus.IMPORTED
            and i.assignment_status == CaptureSessionItemAssignmentStatus.PROPOSED
        ]
        if not eligible:
            raise CaptureSessionMaterializationNotAllowedError(
                "Materialization requires at least one imported and proposed item."
            )
        if any(i.linked_source_asset_id for i in items):
            raise CaptureSessionAlreadyMaterializedError(
                "One or more items already link to SourceAsset rows for this session."
            )
        invalid_imported = [
            i
            for i in items
            if i.import_status == CaptureSessionItemImportStatus.IMPORTED
            and i.assignment_status != CaptureSessionItemAssignmentStatus.PROPOSED
        ]
        if invalid_imported:
            raise CaptureSessionMaterializationNotAllowedError(
                "Materialization requires all imported items to be in proposed assignment status."
            )
        return eligible

    def _run_materialize_commit(self, ctx: _MaterializeCommitContext) -> MaterializeCaptureSessionResult:
        session = ctx.session
        session_id = ctx.session_id
        idem = ctx.idem
        inventory_id = ctx.inventory_id
        aisle_id = ctx.aisle_id
        eligible = ctx.eligible
        prev_status = ctx.prev_status
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        now = self._clock.now()
        created_assets: list[SourceAsset] = []
        created_delete_keys: list[str] = []
        linked_items: list[CaptureSessionItem] = []
        try:
            for item in eligible:
                uploaded = self._read_staging_item_as_uploaded_file(item)
                asset, delete_key = self._materializer.persist_uploaded_file_as_source_asset(
                    aisle_id=aisle_id,
                    uploaded=uploaded,
                    now=now,
                    metadata_json=self._build_source_asset_metadata(
                        session_id=session_id, item=item
                    ),
                )
                created_assets.append(asset)
                created_delete_keys.append(delete_key)
                item.linked_source_asset_id = asset.id
                item.updated_at = now
                self._item_repo.save(item)
                linked_items.append(item)
            # Phase 4: CONFIRMING means "materialized + locked", not final business confirmation.
            session.status = CaptureSessionStatus.CONFIRMING
            session.updated_at = now
            self._session_repo.save(session)
            self._materializer.finalize_aisle_after_source_assets_changed(
                aisle=aisle,
                inventory_id=inventory_id,
                now=now,
            )
            entry = CaptureSessionConfirmationLedgerEntry(
                id=str(uuid4()),
                session_id=session_id,
                idempotency_key=idem,
                created_at=now,
                outcome_json={
                    "created_asset_ids": [a.id for a in created_assets],
                    "created_assets_count": len(created_assets),
                    "session_status": session.status.value,
                },
            )
            self._confirm_repo.insert(entry)
        except CaptureSessionMaterializationNotAllowedError:
            raise
        except CaptureSessionAlreadyMaterializedError:
            raise
        except CaptureSessionConfirmLedgerDuplicateError:
            replay = self._confirm_repo.get_by_session_and_key(session_id, idem)
            ids = tuple((replay.outcome_json or {}).get("created_asset_ids", [])) if replay else ()
            return MaterializeCaptureSessionResult(
                session=session, created_asset_ids=ids, replayed=True
            )
        except Exception as exc:
            self._rollback_item_links(linked_items, now=now)
            self._rollback_created_assets(created_assets, created_delete_keys)
            session.status = prev_status
            session.updated_at = now
            try:
                self._session_repo.save(session)
            except Exception:  # noqa: BLE001 — best-effort rollback; REVISAR_NO_TOCAR B8.2
                logger.warning(
                    "Materialization rollback failed resetting session status session_id=%s",
                    session_id,
                )
            logger.exception(
                "Capture materialization failed session_id=%s created_assets=%d",
                session_id,
                len(created_assets),
            )
            raise CaptureSessionMaterializationFailedError(
                "Failed to materialize capture session items to SourceAsset."
            ) from exc
        return MaterializeCaptureSessionResult(
            session=session,
            created_asset_ids=tuple(a.id for a in created_assets),
            replayed=False,
        )

    def execute(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        session_id: str,
        idempotency_key: str,
    ) -> MaterializeCaptureSessionResult:
        idem = self._normalize_idempotency_key(idempotency_key)
        session = self._load_session_or_raise(session_id, inventory_id, aisle_id)
        replay = self._maybe_replay_idempotent(session, session_id, idem)
        if replay is not None:
            return replay
        eligible = self._validate_session_and_items_for_materialize(session, session_id)
        prev_status = session.status
        return self._run_materialize_commit(
            _MaterializeCommitContext(
                session=session,
                session_id=session_id,
                idem=idem,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                eligible=eligible,
                prev_status=prev_status,
            )
        )

    def _read_staging_item_as_uploaded_file(self, item: CaptureSessionItem) -> UploadedFile:
        key = (item.staging_storage_key or "").strip()
        get_object = getattr(self._artifact_storage, "get_object", None)
        if not callable(get_object):
            raise CaptureSessionMaterializationFailedError(
                "Artifact storage does not support reading staging objects for materialization."
            )
        downloaded = get_object(key)
        raw = getattr(downloaded, "content", None)
        if not isinstance(raw, (bytes, bytearray)) or len(raw) == 0:
            raise CaptureSessionMaterializationFailedError(
                "Staging object is missing or empty for materialization."
            )
        filename = (item.original_filename or Path(key).name or "file").strip()
        content_type = (getattr(downloaded, "content_type", None) or "").strip()
        if not content_type or content_type == "application/octet-stream":
            guessed = mimetypes.guess_type(filename)[0]
            content_type = guessed or "application/octet-stream"
        uploaded = UploadedFile(
            original_filename=filename,
            file_obj=BytesIO(bytes(raw)),
            content_type=content_type,
        )
        validate_staging_media_upload_file(uploaded)
        uploaded.file_obj.seek(0)
        return uploaded

    def _rollback_created_assets(
        self, created_assets: Sequence[SourceAsset], delete_keys: Sequence[str]
    ) -> None:
        for asset in reversed(created_assets):
            try:
                self._asset_repo.delete_by_id(asset.id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Materialization rollback failed deleting asset row asset_id=%s", asset.id
                )
        for key in reversed(delete_keys):
            try:
                self._artifact_storage.delete_file(key)
            except Exception:  # noqa: BLE001
                logger.warning("Materialization rollback failed deleting file key=%s", key)

    def _rollback_item_links(
        self, linked_items: Sequence[CaptureSessionItem], *, now: datetime
    ) -> None:
        for item in reversed(linked_items):
            try:
                item.linked_source_asset_id = None
                item.updated_at = now
                self._item_repo.save(item)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Materialization rollback failed resetting item link item_id=%s", item.id
                )

    def _build_source_asset_metadata(
        self, *, session_id: str, item: CaptureSessionItem
    ) -> dict[str, object]:
        return {
            "capture_session_id": session_id,
            "capture_session_item_id": item.id,
            "effective_capture_time": item.effective_capture_time.isoformat()
            if item.effective_capture_time
            else None,
            "time_source": item.time_source.value if item.time_source else None,
            "assignment_reason": item.assignment_reason,
            "preview_target_position_id": item.preview_target_position_id,
        }
