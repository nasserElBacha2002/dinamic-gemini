"""Upload media into capture session staging — Sprint 2 (no SourceAsset, no materializer finalize)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    CaptureSessionDuplicateItemContentError,
    CaptureSessionNotAcceptingUploadsError,
    CaptureSessionNotFoundError,
    EmptyUploadError,
    UnsupportedAssetTypeError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.capture_staging_time import (
    CaptureStagingTimeMetadataExtractor,
    ExtractedCaptureStagingTime,
)
from src.application.ports.clock import Clock
from src.application.ports.services import ArtifactStorage
from src.application.services.aisle_source_asset_materializer import (
    validate_staging_media_upload_file,
)
from src.application.services.upload_file_count_validation import (
    assert_upload_file_count_within_limit,
)
from src.application.services.upload_request_limits import UploadRequestLimitPolicy
from src.application.services.upload_stream_io import measure_fileobj_size, sha256_fileobj
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
class PreflightUploadResult:
    """Outcome of validating one staging upload file without buffering its bytes in memory."""

    digest: str
    size_bytes: int


@dataclass(frozen=True)
class StagingUploadFileError:
    filename: str
    code: str
    detail: str
    #: Zero-based index into the request ``files`` sequence (stable client mapping).
    file_index: int
    client_file_id: str | None = None


@dataclass(frozen=True)
class StagingUploadBatchResult:
    """Outcome of a staging upload POST: persisted rows plus per-file validation failures."""

    items: tuple[CaptureSessionItem, ...]
    errors: tuple[StagingUploadFileError, ...]


@dataclass
class _StagingBatchAccum:
    """Mutable per-request state for staging upload (B8.2)."""

    errors: list[StagingUploadFileError]
    created: list[CaptureSessionItem]
    batch_digests: set[str]
    session_dirty: bool


@dataclass(frozen=True)
class _StagingIngestUnit:
    """One file in a staging batch (B8.2 PLR0913)."""

    session: CaptureSession
    session_id: str
    inventory_id: str
    now: datetime
    file_index: int
    uf: UploadedFile


@dataclass(frozen=True)
class _PersistStagingFailureParams:
    item_id: str
    session_id: str
    rel_key: str
    now: datetime
    extracted: ExtractedCaptureStagingTime
    uf: UploadedFile


@dataclass(frozen=True)
class _ItemSaveFailureBundle:
    session_id: str
    rel_key: str
    digest: str
    fname: str
    file_index: int
    item_id: str
    now: datetime
    extracted: ExtractedCaptureStagingTime
    uf: UploadedFile


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
        max_upload_bytes: int,
        time_metadata_extractor: CaptureStagingTimeMetadataExtractor,
        upload_policy: UploadRequestLimitPolicy | None = None,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._staging_prefix = _normalize_prefix(staging_prefix)
        self._max_upload_bytes = max(1, int(max_upload_bytes))
        self._time_extractor = time_metadata_extractor
        self._policy = upload_policy or UploadRequestLimitPolicy(
            max_file_size_bytes=self._max_upload_bytes
        )

    def _require_session_for_staging_upload(
        self, session_id: str, inventory_id: str, aisle_id: str | None
    ) -> CaptureSession:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory and aisle."
            )
        if aisle_id is not None and session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory and aisle."
            )
        if not _session_accepts_uploads(session):
            raise CaptureSessionNotAcceptingUploadsError(
                "This capture session does not accept new staging uploads."
            )
        return session

    @staticmethod
    def _error_unsupported_type(
        fname: str, file_index: int, detail: str, client_file_id: str | None = None
    ) -> StagingUploadFileError:
        return StagingUploadFileError(
            filename=fname,
            code=_CODE_UNSUPPORTED_ASSET_TYPE,
            detail=detail,
            file_index=file_index,
            client_file_id=client_file_id,
        )

    @staticmethod
    def _error_zero_byte(
        fname: str, file_index: int, client_file_id: str | None = None
    ) -> StagingUploadFileError:
        return StagingUploadFileError(
            filename=fname,
            code=_CODE_ZERO_BYTE_FILE,
            detail=_DETAIL_ZERO_BYTE_FILE,
            file_index=file_index,
            client_file_id=client_file_id,
        )

    @staticmethod
    def _error_too_large(
        fname: str, file_index: int, client_file_id: str | None = None
    ) -> StagingUploadFileError:
        return StagingUploadFileError(
            filename=fname,
            code=_CODE_CAPTURE_SESSION_STAGING_FILE_TOO_LARGE,
            detail=_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE,
            file_index=file_index,
            client_file_id=client_file_id,
        )

    @staticmethod
    def _error_duplicate_content(
        fname: str, file_index: int, client_file_id: str | None = None
    ) -> StagingUploadFileError:
        return StagingUploadFileError(
            filename=fname,
            code=_CODE_CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
            detail=_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
            file_index=file_index,
            client_file_id=client_file_id,
        )

    def _preflight_one_upload_file(
        self,
        uf: UploadedFile,
        fname: str,
        file_index: int,
        *,
        session_hashes: set[str],
        batch_digests: set[str],
    ) -> tuple[PreflightUploadResult | None, StagingUploadFileError | None]:
        """Return (result, None) when OK; (None, error) on validation failure.

        Streams the file (chunked hash + seek-based size) instead of buffering it fully in
        memory; ``uf.file_obj`` is left seekable and untouched on return (position restored).
        """
        try:
            validate_staging_media_upload_file(uf)
        except UnsupportedAssetTypeError as exc:
            return None, self._error_unsupported_type(
                fname, file_index, str(exc), uf.client_file_id
            )
        size = measure_fileobj_size(uf.file_obj)
        if size == 0:
            return None, self._error_zero_byte(fname, file_index, uf.client_file_id)
        if size > self._max_upload_bytes:
            return None, self._error_too_large(fname, file_index, uf.client_file_id)
        digest = sha256_fileobj(uf.file_obj)
        if digest in batch_digests or digest in session_hashes:
            return None, self._error_duplicate_content(fname, file_index, uf.client_file_id)
        return PreflightUploadResult(digest=digest, size_bytes=size), None

    def _persist_staging_row_after_storage_failure(
        self, p: _PersistStagingFailureParams
    ) -> CaptureSessionItem:
        err_item = CaptureSessionItem(
            id=p.item_id,
            session_id=p.session_id,
            staging_storage_key=p.rel_key,
            import_status=CaptureSessionItemImportStatus.IMPORT_FAILED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=p.now,
            content_hash=None,
            last_error_code="STORAGE_WRITE_FAILED",
            last_error_detail="Staging storage write failed",
            original_filename=p.uf.original_filename or None,
            effective_capture_time=p.extracted.effective_capture_time,
            time_source=p.extracted.time_source,
            time_confidence=p.extracted.time_confidence,
        )
        self._item_repo.save(err_item)
        return err_item

    def _handle_item_save_exception(
        self,
        save_exc: Exception,
        b: _ItemSaveFailureBundle,
        acc: _StagingBatchAccum,
    ) -> None:
        if isinstance(save_exc, CaptureSessionDuplicateItemContentError):
            logger.warning(
                "capture staging upload: duplicate content_hash on save session_id=%s key=%s",
                b.session_id,
                b.rel_key,
            )
            try:
                self._artifact_storage.delete_file(b.rel_key)
            except Exception as cleanup_e:
                logger.warning(
                    "capture staging upload: cleanup delete failed key=%s: %s",
                    b.rel_key,
                    cleanup_e,
                )
            acc.batch_digests.discard(b.digest)
            acc.errors.append(
                self._error_duplicate_content(b.fname, b.file_index, b.uf.client_file_id)
            )
            return
        try:
            self._artifact_storage.delete_file(b.rel_key)
        except Exception as cleanup_e:
            logger.warning(
                "capture staging upload: rollback delete failed key=%s: %s",
                b.rel_key,
                cleanup_e,
            )
        fail = CaptureSessionItem(
            id=b.item_id,
            session_id=b.session_id,
            staging_storage_key=b.rel_key,
            import_status=CaptureSessionItemImportStatus.IMPORT_FAILED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=b.now,
            content_hash=b.digest,
            last_error_code="ITEM_PERSIST_FAILED",
            last_error_detail="Failed to persist capture session item",
            original_filename=b.uf.original_filename or None,
            effective_capture_time=b.extracted.effective_capture_time,
            time_source=b.extracted.time_source,
            time_confidence=b.extracted.time_confidence,
        )
        self._item_repo.save(fail)
        acc.created.append(fail)
        logger.exception(
            "capture staging upload: item persist failed session_id=%s item_id=%s",
            b.session_id,
            b.item_id,
        )

    def _ingest_one_staging_file(
        self,
        u: _StagingIngestUnit,
        acc: _StagingBatchAccum,
        *,
        session_hashes: set[str],
    ) -> None:
        session = u.session
        session_id = u.session_id
        inventory_id = u.inventory_id
        now = u.now
        file_index = u.file_index
        uf = u.uf
        fname = _wire_filename(uf)
        preflight, err = self._preflight_one_upload_file(
            uf,
            fname,
            file_index,
            session_hashes=session_hashes,
            batch_digests=acc.batch_digests,
        )
        if err is not None:
            acc.errors.append(err)
            return
        if preflight is None:
            return
        digest = preflight.digest
        acc.batch_digests.add(digest)
        extracted = self._time_extractor.extract(
            file_obj=uf.file_obj,
            media_content_type=uf.content_type or "application/octet-stream",
            ingest_clock=now,
            source_mtime_utc=uf.last_modified_at,
        )
        item_id = str(uuid4())
        safe = _safe_filename(uf.original_filename)
        rel_key = f"{self._staging_prefix}/{inventory_id}/{session_id}/{item_id}_{safe}"
        try:
            uf.file_obj.seek(0)
            self._artifact_storage.save_file(
                rel_key, uf.file_obj, uf.content_type or "application/octet-stream"
            )
        except Exception:
            logger.exception(
                "capture staging upload: storage write failed session_id=%s item_id=%s key=%s",
                session_id,
                item_id,
                rel_key,
            )
            row = self._persist_staging_row_after_storage_failure(
                _PersistStagingFailureParams(
                    item_id=item_id,
                    session_id=session_id,
                    rel_key=rel_key,
                    now=now,
                    extracted=extracted,
                    uf=uf,
                )
            )
            acc.created.append(row)
            return

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
            self._handle_item_save_exception(
                save_exc,
                _ItemSaveFailureBundle(
                    session_id=session_id,
                    rel_key=rel_key,
                    digest=digest,
                    fname=fname,
                    file_index=file_index,
                    item_id=item_id,
                    now=now,
                    extracted=extracted,
                    uf=uf,
                ),
                acc,
            )
            return

        acc.created.append(item)
        if session.status == CaptureSessionStatus.DRAFT:
            session.status = CaptureSessionStatus.IMPORTING
            session.updated_at = now
            acc.session_dirty = True

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
        assert_upload_file_count_within_limit(
            len(files), max_files=self._policy.max_files_per_request
        )
        session = self._require_session_for_staging_upload(session_id, inventory_id, aisle_id)
        session_hashes = self._item_repo.list_all_content_hashes_for_session(session_id)
        now = self._clock.now()
        acc = _StagingBatchAccum([], [], set(), False)
        for file_index, uf in enumerate(files):
            self._ingest_one_staging_file(
                _StagingIngestUnit(
                    session=session,
                    session_id=session_id,
                    inventory_id=inventory_id,
                    now=now,
                    file_index=file_index,
                    uf=uf,
                ),
                acc,
                session_hashes=session_hashes,
            )
        if acc.session_dirty:
            self._session_repo.save(session)
        return StagingUploadBatchResult(items=tuple(acc.created), errors=tuple(acc.errors))
