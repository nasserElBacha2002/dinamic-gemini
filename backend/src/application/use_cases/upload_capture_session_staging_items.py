"""Upload media into capture session staging — Sprint 2 (no SourceAsset, no materializer finalize)."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionDuplicateItemContentError,
    CaptureSessionNotAcceptingUploadsError,
    CaptureSessionNotFoundError,
    CaptureSessionUploadBatchTooLargeError,
    EmptyUploadError,
    UnsupportedAssetTypeError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.capture_staging_time import CaptureStagingTimeMetadataExtractor
from src.application.ports.clock import Clock
from src.application.ports.services import ArtifactStorage
from src.application.services.aisle_source_asset_materializer import (
    validate_staging_media_upload_file,
)
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)

logger = logging.getLogger(__name__)

# Wire codes aligned with ``src.api.errors.structured_api_http`` (per-file JSON errors).
_CODE_ZERO_BYTE_FILE = "ZERO_BYTE_FILE"
_CODE_UNSUPPORTED_ASSET_TYPE = "UNSUPPORTED_ASSET_TYPE"
_CODE_CAPTURE_SESSION_STAGING_FILE_TOO_LARGE = "CAPTURE_SESSION_STAGING_FILE_TOO_LARGE"
_CODE_CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT = "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"

# Human-facing detail strings aligned with ``src.api.constants.error_wire`` / mapper.
_DETAIL_ZERO_BYTE_FILE = "Empty or zero-byte files are not allowed"
_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE = "File exceeds maximum upload size for staging uploads"
_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT = "Duplicate file content in this capture session"


@dataclass(frozen=True)
class StagingUploadFileError:
    filename: str
    code: str
    detail: str
    #: Zero-based index into the request ``files`` sequence (stable client mapping).
    file_index: int


@dataclass(frozen=True)
class StagingUploadBatchResult:
    """Outcome of a staging upload POST: persisted rows plus per-file validation failures."""

    items: tuple[CaptureSessionItem, ...]
    errors: tuple[StagingUploadFileError, ...]


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


def _wire_filename(uf: UploadedFile) -> str:
    return (uf.original_filename or "file").strip() or "file"


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
        time_metadata_extractor: CaptureStagingTimeMetadataExtractor,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._staging_prefix = _normalize_prefix(staging_prefix)
        self._max_files = max(1, int(max_files_per_upload))
        self._max_upload_bytes = max(1, int(max_upload_bytes))
        self._time_extractor = time_metadata_extractor

    def execute(
        self,
        *,
        inventory_id: str,
        aisle_id: str | None,
        session_id: str,
        files: Sequence[UploadedFile],
    ) -> StagingUploadBatchResult:
        if not files:
            raise EmptyUploadError("At least one file is required")
        if len(files) > self._max_files:
            raise CaptureSessionUploadBatchTooLargeError(
                f"At most {self._max_files} file(s) allowed per staging upload request"
            )
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory and aisle.")
        if aisle_id is not None and session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory and aisle.")
        if not _session_accepts_uploads(session):
            raise CaptureSessionNotAcceptingUploadsError(
                "This capture session does not accept new staging uploads."
            )
        now = self._clock.now()
        errors: list[StagingUploadFileError] = []
        created: list[CaptureSessionItem] = []
        session_dirty = False
        batch_digests: set[str] = set()

        for file_index, uf in enumerate(files):
            fname = _wire_filename(uf)
            try:
                validate_staging_media_upload_file(uf)
            except UnsupportedAssetTypeError as exc:
                errors.append(
                    StagingUploadFileError(
                        filename=fname,
                        code=_CODE_UNSUPPORTED_ASSET_TYPE,
                        detail=str(exc),
                        file_index=file_index,
                    )
                )
                continue

            raw = uf.file_obj.read()
            if not raw:
                errors.append(
                    StagingUploadFileError(
                        filename=fname,
                        code=_CODE_ZERO_BYTE_FILE,
                        detail=_DETAIL_ZERO_BYTE_FILE,
                        file_index=file_index,
                    )
                )
                continue
            if len(raw) > self._max_upload_bytes:
                errors.append(
                    StagingUploadFileError(
                        filename=fname,
                        code=_CODE_CAPTURE_SESSION_STAGING_FILE_TOO_LARGE,
                        detail=_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE,
                        file_index=file_index,
                    )
                )
                continue

            digest = hashlib.sha256(raw).hexdigest()
            if digest in batch_digests:
                errors.append(
                    StagingUploadFileError(
                        filename=fname,
                        code=_CODE_CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
                        detail=_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
                        file_index=file_index,
                    )
                )
                continue
            if self._item_repo.has_item_with_content_hash(session_id, digest):
                errors.append(
                    StagingUploadFileError(
                        filename=fname,
                        code=_CODE_CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
                        detail=_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
                        file_index=file_index,
                    )
                )
                continue

            batch_digests.add(digest)
            extracted = self._time_extractor.extract(
                raw_bytes=raw,
                media_content_type=uf.content_type or "application/octet-stream",
                ingest_clock=now,
                source_mtime_utc=uf.last_modified_at,
            )
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
                    effective_capture_time=extracted.effective_capture_time,
                    time_source=extracted.time_source,
                    time_confidence=extracted.time_confidence,
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
                effective_capture_time=extracted.effective_capture_time,
                time_source=extracted.time_source,
                time_confidence=extracted.time_confidence,
                original_filename=uf.original_filename or None,
            )
            try:
                self._item_repo.save(item)
            except Exception as save_exc:
                if isinstance(save_exc, CaptureSessionDuplicateItemContentError):
                    logger.warning(
                        "capture staging upload: duplicate content_hash on save session_id=%s key=%s",
                        session_id,
                        rel_key,
                    )
                    try:
                        self._artifact_storage.delete_file(rel_key)
                    except Exception as cleanup_e:  # noqa: BLE001
                        logger.warning("capture staging upload: cleanup delete failed key=%s: %s", rel_key, cleanup_e)
                    batch_digests.discard(digest)
                    errors.append(
                        StagingUploadFileError(
                            filename=fname,
                            code=_CODE_CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
                            detail=_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
                            file_index=file_index,
                        )
                    )
                    continue
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
                    effective_capture_time=extracted.effective_capture_time,
                    time_source=extracted.time_source,
                    time_confidence=extracted.time_confidence,
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
        return StagingUploadBatchResult(items=tuple(created), errors=tuple(errors))
