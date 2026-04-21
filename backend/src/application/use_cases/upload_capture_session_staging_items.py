"""Upload media into capture session staging — Sprint 2 (no SourceAsset, no materializer finalize)."""

from __future__ import annotations

import hashlib
import logging
import re
from io import BytesIO
from typing import List, Sequence
from uuid import uuid4

import pyodbc

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionDuplicateItemContentError,
    CaptureSessionNotAcceptingUploadsError,
    CaptureSessionNotFoundError,
    CaptureSessionStagingFileTooLargeError,
    CaptureSessionUploadBatchTooLargeError,
    EmptyUploadError,
    ZeroByteFileError,
)
from src.application.ports.capture_repositories import CaptureSessionItemRepository, CaptureSessionRepository
from src.application.ports.clock import Clock
from src.application.ports.services import ArtifactStorage
from src.application.services.aisle_source_asset_materializer import validate_staging_media_upload_file
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    base = re.sub(r"[^\w.\-]", "_", (name or "file").strip())
    return base[:200] if base else "file"


def _normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip().strip("/")
    return p or "capture/staging"


def _session_accepts_uploads(session: CaptureSession) -> bool:
    if session.closed_at is not None:
        return False
    if session.status in (
        CaptureSessionStatus.CANCELLED,
        CaptureSessionStatus.FAILED,
        CaptureSessionStatus.CONFIRMED,
    ):
        return False
    return True


class UploadCaptureSessionStagingItemsUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
        staging_prefix: str,
        max_files_per_upload: int,
        max_upload_bytes: int,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._staging_prefix = _normalize_prefix(staging_prefix)
        self._max_files = max(1, int(max_files_per_upload))
        self._max_upload_bytes = max(1, int(max_upload_bytes))

    def execute(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        session_id: str,
        files: Sequence[UploadedFile],
    ) -> List[CaptureSessionItem]:
        if not files:
            raise EmptyUploadError("At least one file is required")
        if len(files) > self._max_files:
            raise CaptureSessionUploadBatchTooLargeError(
                f"At most {self._max_files} file(s) allowed per staging upload request"
            )
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None or session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory and aisle.")
        if not _session_accepts_uploads(session):
            raise CaptureSessionNotAcceptingUploadsError(
                "This capture session does not accept new staging uploads."
            )
        now = self._clock.now()
        prepared: list[tuple[UploadedFile, bytes, str]] = []
        for uf in files:
            validate_staging_media_upload_file(uf)
            raw = uf.file_obj.read()
            if not raw:
                raise ZeroByteFileError("Empty or zero-byte files are not allowed")
            if len(raw) > self._max_upload_bytes:
                raise CaptureSessionStagingFileTooLargeError(
                    f"File exceeds maximum upload size ({self._max_upload_bytes} bytes)"
                )
            digest = hashlib.sha256(raw).hexdigest()
            prepared.append((uf, raw, digest))
        digests = [p[2] for p in prepared]
        if len(set(digests)) != len(digests):
            raise CaptureSessionDuplicateItemContentError(
                "Duplicate file content in this capture session"
            )
        for _uf, raw, digest in prepared:
            if self._item_repo.has_item_with_content_hash(session_id, digest):
                raise CaptureSessionDuplicateItemContentError(
                    "Duplicate file content in this capture session"
                )
        created: List[CaptureSessionItem] = []
        session_dirty = False
        for uf, raw, digest in prepared:
            item_id = str(uuid4())
            safe = _safe_filename(uf.original_filename)
            rel_key = f"{self._staging_prefix}/{inventory_id}/{session_id}/{item_id}_{safe}"
            bio = BytesIO(raw)
            try:
                self._artifact_storage.save_file(rel_key, bio, uf.content_type or "application/octet-stream")
            except Exception:
                logger.exception(
                    "capture staging upload: storage write failed session_id=%s item_id=%s key=%s",
                    session_id,
                    item_id,
                    rel_key,
                )
                err_item = CaptureSessionItem(
                    id=item_id,
                    session_id=session_id,
                    staging_storage_key=rel_key,
                    import_status=CaptureSessionItemImportStatus.IMPORT_FAILED,
                    assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
                    updated_at=now,
                    content_hash=None,
                    last_error_code="STORAGE_WRITE_FAILED",
                    last_error_detail="Staging storage write failed",
                    original_filename=uf.original_filename or None,
                )
                self._item_repo.save(err_item)
                created.append(err_item)
                continue
            item = CaptureSessionItem(
                id=item_id,
                session_id=session_id,
                staging_storage_key=rel_key,
                import_status=CaptureSessionItemImportStatus.IMPORTED,
                assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
                updated_at=now,
                content_hash=digest,
                original_filename=uf.original_filename or None,
            )
            try:
                self._item_repo.save(item)
            except Exception as exc:
                if isinstance(exc, pyodbc.IntegrityError) or _is_unique_constraint_violation(exc):
                    logger.warning(
                        "capture staging upload: duplicate content_hash session_id=%s key=%s: %s",
                        session_id,
                        rel_key,
                        exc,
                    )
                    try:
                        self._artifact_storage.delete_file(rel_key)
                    except Exception as cleanup_e:  # noqa: BLE001
                        logger.warning("capture staging upload: rollback delete failed key=%s: %s", rel_key, cleanup_e)
                    raise CaptureSessionDuplicateItemContentError(
                        "Duplicate file content in this capture session"
                    ) from exc
                try:
                    self._artifact_storage.delete_file(rel_key)
                except Exception as cleanup_e:  # noqa: BLE001
                    logger.warning("capture staging upload: rollback delete failed key=%s: %s", rel_key, cleanup_e)
                fail = CaptureSessionItem(
                    id=item_id,
                    session_id=session_id,
                    staging_storage_key=rel_key,
                    import_status=CaptureSessionItemImportStatus.IMPORT_FAILED,
                    assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
                    updated_at=now,
                    content_hash=digest,
                    last_error_code="ITEM_PERSIST_FAILED",
                    last_error_detail="Failed to persist capture session item",
                    original_filename=uf.original_filename or None,
                )
                self._item_repo.save(fail)
                created.append(fail)
                logger.exception(
                    "capture staging upload: item persist failed session_id=%s item_id=%s", session_id, item_id
                )
                continue
            created.append(item)
            if session.status == CaptureSessionStatus.DRAFT:
                session.status = CaptureSessionStatus.IMPORTING
                session.updated_at = now
                session_dirty = True
        if session_dirty:
            self._session_repo.save(session)
        return created


def _is_unique_constraint_violation(exc: BaseException) -> bool:
    if isinstance(exc, pyodbc.IntegrityError):
        return True
    state = getattr(exc, "args", None)
    if state and str(state[0]) == "23000":
        return True
    return "UNIQUE KEY" in str(exc).upper() or "unique constraint" in str(exc).lower()
