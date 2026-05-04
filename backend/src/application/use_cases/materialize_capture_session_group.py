"""G5 — materialize capture items for an assigned temporal group into aisle SourceAssets."""

from __future__ import annotations

import logging
import mimetypes
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

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
from src.application.services.capture_flow_observability import (
    LOG_OP_G5_MATERIALIZE_ALL_GROUPS,
    LOG_OP_G5_MATERIALIZE_GROUP,
    RESULT_FAILED,
    RESULT_PARTIAL,
    RESULT_SUCCESS,
    emit_capture_flow_event,
    get_capture_flow_metrics,
)
from src.application.services.capture_group_item_integrity import validate_group_items_coherent
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.capture_session_group_assignment_guard import (
    ensure_group_aisle_assignment_allowed,
)
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
        ensure_group_aisle_assignment_allowed(
            session, group_repo=self._group_repo, session_id=session_id
        )

        group = self._group_repo.get_by_id_and_session(group_id, session_id)
        if group is None:
            raise CaptureSessionGroupNotFoundError(
                "Capture session group not found for this session."
            )

        if group.assignment_status not in (
            CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_EXISTING,
            CaptureSessionGroupAisleAssignmentStatus.ASSIGNED_NEW,
        ):
            raise CaptureSessionGroupNotAssignedForMaterializationError("")
        aisle_id = (group.assigned_aisle_id or "").strip()
        if not aisle_id:
            raise CaptureSessionGroupNotAssignedForMaterializationError("")

        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        now = self._clock.now()
        operation_id = str(uuid4())
        diag: dict[str, int] = {}
        created, skipped, failed, imported_n, _ = self._materialize_items_for_group(
            session_id=session_id,
            group_id=group_id,
            aisle_id=aisle.id,
            inventory_id=inventory_id,
            now=now,
            materialization_operation_id=operation_id,
            materialize_diag=diag,
        )
        result_status = RESULT_PARTIAL if failed > 0 else RESULT_SUCCESS
        metrics = get_capture_flow_metrics()
        metrics.record_materialization(
            created=created,
            skipped=skipped,
            failed=failed,
            imported_item_count=imported_n,
        )
        emit_capture_flow_event(
            logger=logger,
            inventory_id=inventory_id,
            session_id=session_id,
            operation=LOG_OP_G5_MATERIALIZE_GROUP,
            result_status=result_status,
            group_id=group_id,
            aisle_id=aisle_id,
            counts={"created": created, "skipped": skipped, "failed": failed},
            extra={
                "materialization_operation_id": operation_id,
                "materialize_diag": dict(diag),
            },
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
        ensure_group_aisle_assignment_allowed(
            session, group_repo=self._group_repo, session_id=session_id
        )

        summaries = list(self._group_repo.list_summaries(session_id))
        total = len(summaries)
        skipped_groups = 0
        materialized_groups = 0
        total_created = total_skipped = total_failed = 0
        now = self._clock.now()
        metrics = get_capture_flow_metrics()
        bulk_group_failures = 0

        for s in summaries:
            st = (s.assignment_status or "").strip().lower()
            if (
                st == CaptureSessionGroupAisleAssignmentStatus.UNASSIGNED.value
                or not (s.assigned_aisle_id or "").strip()
            ):
                skipped_groups += 1
                continue
            aisle_id = (s.assigned_aisle_id or "").strip()
            operation_id = str(uuid4())
            diag: dict[str, int] = {}
            try:
                aisle = require_aisle_scoped_to_inventory(
                    self._aisle_repo,
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    detail_style="strict",
                )
                c, sk, f, imported_n, _d = self._materialize_items_for_group(
                    session_id=session_id,
                    group_id=s.group_id,
                    aisle_id=aisle.id,
                    inventory_id=inventory_id,
                    now=now,
                    materialization_operation_id=operation_id,
                    materialize_diag=diag,
                )
                materialized_groups += 1
                total_created += c
                total_skipped += sk
                total_failed += f
                metrics.record_materialization(
                    created=c,
                    skipped=sk,
                    failed=f,
                    imported_item_count=imported_n,
                )
                emit_capture_flow_event(
                    logger=logger,
                    inventory_id=inventory_id,
                    session_id=session_id,
                    operation=LOG_OP_G5_MATERIALIZE_GROUP,
                    result_status=RESULT_PARTIAL if f > 0 else RESULT_SUCCESS,
                    group_id=s.group_id,
                    aisle_id=aisle_id,
                    counts={"created": c, "skipped": sk, "failed": f},
                    extra={
                        "materialization_operation_id": operation_id,
                        "materialize_diag": dict(diag),
                        "bulk": True,
                    },
                )
            except Exception:
                bulk_group_failures += 1
                logger.exception(
                    "G5 bulk materialize group failed session_id=%s group_id=%s aisle_id=%s",
                    session_id,
                    s.group_id,
                    aisle_id,
                )
                metrics.record_materialization(
                    created=0,
                    skipped=0,
                    failed=0,
                    imported_item_count=0,
                    failed_whole_group=True,
                )
                emit_capture_flow_event(
                    logger=logger,
                    inventory_id=inventory_id,
                    session_id=session_id,
                    operation=LOG_OP_G5_MATERIALIZE_GROUP,
                    result_status=RESULT_FAILED,
                    group_id=s.group_id,
                    aisle_id=aisle_id,
                    counts={"created": 0, "skipped": 0, "failed": 1},
                    extra={
                        "materialization_operation_id": operation_id,
                        "bulk": True,
                        "bulk_group_exception": True,
                    },
                )
                total_failed += 1

        emit_capture_flow_event(
            logger=logger,
            inventory_id=inventory_id,
            session_id=session_id,
            operation=LOG_OP_G5_MATERIALIZE_ALL_GROUPS,
            result_status=RESULT_PARTIAL if bulk_group_failures or total_failed else RESULT_SUCCESS,
            counts={
                "total_groups": total,
                "materialized_groups": materialized_groups,
                "skipped_groups": skipped_groups,
                "total_assets_created": total_created,
                "total_assets_skipped": total_skipped,
                "total_assets_failed": total_failed,
                "bulk_group_failures": bulk_group_failures,
            },
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
        materialization_operation_id: str,
        materialize_diag: MutableMapping[str, int] | None = None,
    ) -> tuple[int, int, int, int, Mapping[str, int]]:
        items = list(self._item_repo.list_by_session_and_group_id(session_id, group_id))
        validate_group_items_coherent(items, session_id=session_id, group_id=group_id)
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
        mat_iso = now.isoformat()
        diag = materialize_diag if materialize_diag is not None else {}

        def _bump(key: str) -> None:
            diag[key] = diag.get(key, 0) + 1

        for item in imported:
            try:
                link_id = (item.linked_source_asset_id or "").strip()
                if link_id:
                    linked_asset = self._asset_repo.get_by_id(link_id)
                    if linked_asset is not None:
                        skipped += 1
                        _bump("skipped_item_already_linked_valid_asset")
                        continue
                    _bump("cleared_stale_linked_source_asset_id")

                existing = self._asset_repo.get_by_capture_session_item_id(item.id)
                if existing is not None:
                    item.linked_source_asset_id = existing.id
                    item.updated_at = now
                    try:
                        self._item_repo.save(item)
                    except Exception:
                        logger.exception(
                            "G5 item partially failed: existing asset present but item link update failed "
                            "session_id=%s group_id=%s item_id=%s",
                            session_id,
                            group_id,
                            item.id,
                        )
                        failed += 1
                    else:
                        skipped += 1
                        _bump("repaired_item_link_from_existing_row")
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
                        materialization_operation_id=materialization_operation_id,
                        materialized_at_iso=mat_iso,
                    ),
                    capture_session_item_id=item.id,
                )
                any_new_asset = True
                created += 1
                item.linked_source_asset_id = asset.id
                item.updated_at = now
                try:
                    self._item_repo.save(item)
                except Exception:
                    logger.exception(
                        "G5 item partially failed: asset created but item update failed session_id=%s group_id=%s item_id=%s",
                        session_id,
                        group_id,
                        item.id,
                    )
                    failed += 1
            except Exception:
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
                raise CaptureSessionMaterializationFailedError(
                    "Aisle disappeared during group materialization."
                )
            self._materializer.finalize_aisle_after_source_assets_changed(
                aisle=aisle_entity,
                inventory_id=inventory_id,
                now=now,
            )

        return created, skipped, failed, len(imported), diag

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

    def _build_source_asset_metadata(
        self,
        *,
        session_id: str,
        group_id: str,
        item: CaptureSessionItem,
        materialization_operation_id: str,
        materialized_at_iso: str,
    ) -> dict[str, object]:
        return {
            "capture_session_id": session_id,
            "capture_session_group_id": group_id,
            "capture_session_item_id": item.id,
            "materialized_at": materialized_at_iso,
            "materialization_operation_id": materialization_operation_id,
            "effective_capture_time": item.effective_capture_time.isoformat()
            if item.effective_capture_time
            else None,
            "time_source": item.time_source.value if item.time_source else None,
            "time_confidence": item.time_confidence,
            "original_filename": item.original_filename,
            "staging_storage_key": item.staging_storage_key,
            "assignment_reason": item.assignment_reason,
            "preview_target_position_id": item.preview_target_position_id,
        }
