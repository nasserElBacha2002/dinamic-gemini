"""G5 — materialize capture items for an assigned temporal group into aisle SourceAssets."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionGroupNotAssignedForMaterializationError,
    CaptureSessionGroupNotFoundError,
    CaptureSessionMaterializationFailedError,
    CaptureSessionNotFoundError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
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
from src.application.services.capture_session_group_assignment_guard import ensure_group_aisle_assignment_allowed
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.capture.entities import (
    CaptureSessionGroupAisleAssignmentStatus,
    CaptureSessionItem,
    CaptureSessionItemImportStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaterializeCaptureSessionGroupResult:
    group_id: str
    aisle_id: str
    created_assets: int
    skipped_assets: int
    failed_assets: int
    status: str = "materialized"


@dataclass(frozen=True)
class MaterializeAllCaptureSessionGroupsResult:
    total_groups: int
    materialized_groups: int
    skipped_groups: int
    total_assets_created: int
    total_assets_skipped: int
    total_assets_failed: int


class MaterializeCaptureSessionGroupUseCase:
    """Inventory-scoped materialization: staging bytes → ``SourceAsset`` on the group's aisle."""

    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        group_repo: CaptureSessionGroupRepository,
        item_repo: CaptureSessionItemRepository,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        artifact_storage: ArtifactStorage,
        status_reconciler: InventoryStatusReconciler,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._group_repo = group_repo
        self._item_repo = item_repo
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._materializer = AisleSourceAssetMaterializer(
            aisle_repo=aisle_repo,
            asset_repo=asset_repo,
            artifact_storage=artifact_storage,
            status_reconciler=status_reconciler,
        )

    def materialize_one(
        self,
        *,
        inventory_id: str,
        session_id: str,
        group_id: str,
    ) -> MaterializeCaptureSessionGroupResult:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory.")
        ensure_group_aisle_assignment_allowed(session, group_repo=self._group_repo, session_id=session_id)

        group = self._group_repo.get_by_id_and_session(group_id, session_id)
        if group is None:
            raise CaptureSessionGroupNotFoundError("Capture session group not found for this session.")

        if group.assignment_status not in (
            CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_NEW,
        ):
            raise CaptureSessionGroupNotAssignedForMaterializationError(
                "Group must be assigned to an aisle before materialization."
            )
        aisle_id = (group.assigned_aisle_id or "").strip()
        if not aisle_id:
            raise CaptureSessionGroupNotAssignedForMaterializationError(
                "Group must be assigned to an aisle before materialization."
            )

        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        now = self._clock.now()
        created, skipped, failed = self._materialize_items_for_group(
            session_id=session_id,
            group_id=group_id,
            aisle_id=aisle.id,
            inventory_id=inventory_id,
            now=now,
        )
        logger.info(
            "G5 materialize group session_id=%s group_id=%s aisle_id=%s created=%s skipped=%s failed=%s",
            session_id,
            group_id,
            aisle_id,
            created,
            skipped,
            failed,
        )
        return MaterializeCaptureSessionGroupResult(
            group_id=group_id,
            aisle_id=aisle_id,
            created_assets=created,
            skipped_assets=skipped,
            failed_assets=failed,
        )

    def materialize_all_assigned(
        self,
        *,
        inventory_id: str,
        session_id: str,
    ) -> MaterializeAllCaptureSessionGroupsResult:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory.")
        ensure_group_aisle_assignment_allowed(session, group_repo=self._group_repo, session_id=session_id)

        summaries = list(self._group_repo.list_summaries(session_id))
        total = len(summaries)
        skipped_groups = 0
        materialized_groups = 0
        total_created = total_skipped = total_failed = 0
        now = self._clock.now()

        for s in summaries:
            st = (s.assignment_status or "").strip().lower()
            if st == CaptureSessionGroupAisleAssignmentStatus.UNASSIGNED.value or not (s.assigned_aisle_id or "").strip():
                skipped_groups += 1
                continue
            aisle_id = (s.assigned_aisle_id or "").strip()
            aisle = require_aisle_scoped_to_inventory(
                self._aisle_repo,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                detail_style="strict",
            )
            c, sk, f = self._materialize_items_for_group(
                session_id=session_id,
                group_id=s.group_id,
                aisle_id=aisle.id,
                inventory_id=inventory_id,
                now=now,
            )
            materialized_groups += 1
            total_created += c
            total_skipped += sk
            total_failed += f
            logger.info(
                "G5 materialize group (bulk) session_id=%s group_id=%s aisle_id=%s created=%s skipped=%s failed=%s",
                session_id,
                s.group_id,
                aisle_id,
                c,
                sk,
                f,
            )

        return MaterializeAllCaptureSessionGroupsResult(
            total_groups=total,
            materialized_groups=materialized_groups,
            skipped_groups=skipped_groups,
            total_assets_created=total_created,
            total_assets_skipped=total_skipped,
            total_assets_failed=total_failed,
        )

    def _materialize_items_for_group(
        self,
        *,
        session_id: str,
        group_id: str,
        aisle_id: str,
        inventory_id: str,
        now: datetime,
    ) -> tuple[int, int, int]:
        items = list(self._item_repo.list_by_session_and_group_id(session_id, group_id))
        imported = [i for i in items if i.import_status == CaptureSessionItemImportStatus.IMPORTED]
        tz = now.tzinfo or timezone.utc
        imported.sort(
            key=lambda it: (
                it.effective_capture_time or datetime.min.replace(tzinfo=tz),
                it.id,
            )
        )

        created = skipped = failed = 0
        any_new_asset = False
        for item in imported:
            try:
                if (item.linked_source_asset_id or "").strip():
                    skipped += 1
                    continue
                existing = self._asset_repo.get_by_capture_session_item_id(item.id)
                if existing is not None:
                    item.linked_source_asset_id = existing.id
                    item.updated_at = now
                    self._item_repo.save(item)
                    skipped += 1
                    continue

                uploaded = self._read_staging_item_as_uploaded_file(item)
                asset, _delete_key = self._materializer.persist_uploaded_file_as_source_asset(
                    aisle_id=aisle_id,
                    uploaded=uploaded,
                    now=now,
                    metadata_json=self._build_source_asset_metadata(
                        session_id=session_id,
                        group_id=group_id,
                        item=item,
                    ),
                    capture_session_item_id=item.id,
                )
                item.linked_source_asset_id = asset.id
                item.updated_at = now
                self._item_repo.save(item)
                created += 1
                any_new_asset = True
            except Exception:  # noqa: BLE001
                logger.exception(
                    "G5 materialize item failed session_id=%s group_id=%s item_id=%s",
                    session_id,
                    group_id,
                    item.id,
                )
                failed += 1

        if any_new_asset:
            aisle_entity = self._aisle_repo.get_by_id(aisle_id)
            if aisle_entity is None:
                raise CaptureSessionMaterializationFailedError("Aisle disappeared during group materialization.")
            self._materializer.finalize_aisle_after_source_assets_changed(
                aisle=aisle_entity,
                inventory_id=inventory_id,
                now=now,
            )

        return created, skipped, failed

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
            raise CaptureSessionMaterializationFailedError("Staging object is missing or empty for materialization.")
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

    def _build_source_asset_metadata(
        self,
        *,
        session_id: str,
        group_id: str,
        item: CaptureSessionItem,
    ) -> dict[str, object]:
        return {
            "capture_session_id": session_id,
            "capture_session_group_id": group_id,
            "capture_session_item_id": item.id,
            "effective_capture_time": item.effective_capture_time.isoformat() if item.effective_capture_time else None,
            "time_source": item.time_source.value if item.time_source else None,
            "time_confidence": item.time_confidence,
            "original_filename": item.original_filename,
            "staging_storage_key": item.staging_storage_key,
            "assignment_reason": item.assignment_reason,
            "preview_target_position_id": item.preview_target_position_id,
        }
