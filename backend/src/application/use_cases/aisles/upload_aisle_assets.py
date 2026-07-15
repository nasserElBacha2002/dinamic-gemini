"""
UploadAisleAssets use case — v3.0 Épica 4.

Uploads one or more files (photos/videos) to an aisle with per-file atomicity and partial
success. Persists SourceAsset records and marks the aisle as assets_uploaded when at least
one file succeeds.

Materialization is delegated to
:class:`src.application.services.aisle_source_asset_materializer.AisleSourceAssetMaterializer`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import (
    AisleInactiveError,
    DuplicateUploadIdempotencyKeyError,
    EmptyUploadError,
    UnsupportedAssetTypeError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.upload_request_limits import (
    UploadFileTooLargeError,
    UploadRequestLimitPolicy,
    assert_file_size,
)
from src.domain.assets.entities import SourceAsset

logger = logging.getLogger(__name__)

_CODE_UNSUPPORTED_ASSET_TYPE = "UNSUPPORTED_ASSET_TYPE"
_CODE_ZERO_BYTE_FILE = "ZERO_BYTE_FILE"
_CODE_UPLOAD_FILE_TOO_LARGE = "UPLOAD_FILE_TOO_LARGE"
_CODE_PERSIST_FAILED = "ASSET_PERSIST_FAILED"

_DETAIL_ZERO_BYTE_FILE = "Empty or zero-byte files are not allowed"
_DETAIL_UPLOAD_FILE_TOO_LARGE = "File exceeds maximum upload size"
_DETAIL_UNSUPPORTED_ASSET_TYPE = "Unsupported asset type"
_DETAIL_ASSET_PERSIST_FAILED = "Failed to persist aisle source asset"


@dataclass(frozen=True)
class AisleAssetUploadFileError:
    filename: str
    code: str
    detail: str
    file_index: int
    client_file_id: str | None = None


@dataclass(frozen=True)
class AisleAssetUploadBatchResult:
    upload_batch_id: str | None
    assets: list[SourceAsset]
    errors: list[AisleAssetUploadFileError]


# Public re-export: existing imports use ``upload_aisle_assets.UploadedFile``.
__all__ = [
    "AisleAssetUploadBatchResult",
    "AisleAssetUploadFileError",
    "UploadAisleAssetsUseCase",
    "UploadedFile",
]


class UploadAisleAssetsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
        status_reconciler: InventoryStatusReconciler,
        *,
        upload_policy: UploadRequestLimitPolicy | None = None,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._status_reconciler = status_reconciler
        self._policy = upload_policy or UploadRequestLimitPolicy()
        self._materializer = AisleSourceAssetMaterializer(
            aisle_repo=aisle_repo,
            asset_repo=asset_repo,
            artifact_storage=artifact_storage,
            status_reconciler=status_reconciler,
        )

    @staticmethod
    def _wire_filename(uf: UploadedFile) -> str:
        return (uf.original_filename or "file").strip() or "file"

    @staticmethod
    def _resolve_batch_id(files: Sequence[UploadedFile], explicit: str | None) -> str | None:
        if explicit and explicit.strip():
            return explicit.strip()
        for uf in files:
            if uf.upload_batch_id and uf.upload_batch_id.strip():
                return uf.upload_batch_id.strip()
        return None

    def _try_idempotent_existing(
        self,
        *,
        aisle_id: str,
        uf: UploadedFile,
        batch_id: str | None,
    ) -> SourceAsset | None:
        client_id = (uf.client_file_id or "").strip()
        resolved_batch = (batch_id or uf.upload_batch_id or "").strip()
        if not client_id or not resolved_batch:
            return None
        return self._asset_repo.get_by_upload_idempotency_key(
            aisle_id,
            resolved_batch,
            client_id,
        )

    def _ingest_one_file(
        self,
        *,
        aisle_id: str,
        uf: UploadedFile,
        now,
        file_index: int,
        batch_id: str | None,
    ) -> tuple[SourceAsset | None, AisleAssetUploadFileError | None]:
        fname = self._wire_filename(uf)
        existing = self._try_idempotent_existing(aisle_id=aisle_id, uf=uf, batch_id=batch_id)
        if existing is not None:
            return existing, None
        try:
            if uf.size_bytes is not None:
                assert_file_size(uf.size_bytes, self._policy)
            pos = uf.file_obj.tell()
            uf.file_obj.seek(0, 2)
            end = uf.file_obj.tell()
            uf.file_obj.seek(pos)
            if end == 0:
                return None, AisleAssetUploadFileError(
                    filename=fname,
                    code=_CODE_ZERO_BYTE_FILE,
                    detail=_DETAIL_ZERO_BYTE_FILE,
                    file_index=file_index,
                    client_file_id=uf.client_file_id,
                )
            if isinstance(end, int) and end > 0 and uf.size_bytes is None:
                assert_file_size(end, self._policy)
        except UploadFileTooLargeError as exc:
            logger.info(
                "Aisle asset upload file too large aisle_id=%s file_index=%d filename=%s: %s",
                aisle_id,
                file_index,
                fname,
                exc,
            )
            return None, AisleAssetUploadFileError(
                filename=fname,
                code=_CODE_UPLOAD_FILE_TOO_LARGE,
                detail=_DETAIL_UPLOAD_FILE_TOO_LARGE,
                file_index=file_index,
                client_file_id=uf.client_file_id,
            )
        delete_key: str | None = None
        try:
            asset, delete_key = self._materializer.persist_uploaded_file_as_source_asset(
                aisle_id=aisle_id,
                uploaded=uf,
                now=now,
                metadata_json=None,
                upload_batch_id=batch_id or uf.upload_batch_id,
                upload_client_file_id=uf.client_file_id,
            )
            return asset, None
        except UnsupportedAssetTypeError as exc:
            logger.info(
                "Aisle asset unsupported type aisle_id=%s file_index=%d filename=%s: %s",
                aisle_id,
                file_index,
                fname,
                exc,
            )
            return None, AisleAssetUploadFileError(
                filename=fname,
                code=_CODE_UNSUPPORTED_ASSET_TYPE,
                detail=_DETAIL_UNSUPPORTED_ASSET_TYPE,
                file_index=file_index,
                client_file_id=uf.client_file_id,
            )
        except DuplicateUploadIdempotencyKeyError as exc:
            # Concurrent request for the same (aisle, batch, client_file_id) already won the
            # insert race. persist_uploaded_file_as_source_asset() already deleted the blob we
            # just wrote (its own except-block runs on *any* asset_repo.save() failure, including
            # this one) before re-raising, so there is nothing left to clean up here — just
            # resolve and return the winner's row as this file's success result.
            logger.info(
                "Duplicate upload idempotency key for aisle_id=%s file_index=%d filename=%s: %s",
                aisle_id,
                file_index,
                fname,
                exc,
            )
            existing = self._try_idempotent_existing(aisle_id=aisle_id, uf=uf, batch_id=batch_id)
            if existing is not None:
                return existing, None
            logger.error(
                "Duplicate upload idempotency key but no existing row found aisle_id=%s "
                "file_index=%d filename=%s",
                aisle_id,
                file_index,
                fname,
            )
            return None, AisleAssetUploadFileError(
                filename=fname,
                code=_CODE_PERSIST_FAILED,
                detail=_DETAIL_ASSET_PERSIST_FAILED,
                file_index=file_index,
                client_file_id=uf.client_file_id,
            )
        except Exception:
            if delete_key:
                try:
                    self._artifact_storage.delete_file(delete_key)
                except Exception as cleanup_e:
                    logger.warning(
                        "Aisle asset upload cleanup delete failed key=%s: %s",
                        delete_key,
                        cleanup_e,
                    )
            logger.exception(
                "Aisle asset upload failed aisle_id=%s file_index=%d filename=%s",
                aisle_id,
                file_index,
                fname,
            )
            return None, AisleAssetUploadFileError(
                filename=fname,
                code=_CODE_PERSIST_FAILED,
                detail=_DETAIL_ASSET_PERSIST_FAILED,
                file_index=file_index,
                client_file_id=uf.client_file_id,
            )

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        files: Sequence[UploadedFile],
        *,
        upload_batch_id: str | None = None,
    ) -> AisleAssetUploadBatchResult:
        if not files:
            raise EmptyUploadError("At least one file is required")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        if not aisle.is_active:
            raise AisleInactiveError(
                f"Aisle {aisle_id} is inactive; reactivate before uploading assets."
            )
        now = self._clock.now()
        batch_id = self._resolve_batch_id(files, upload_batch_id)
        created: list[SourceAsset] = []
        errors: list[AisleAssetUploadFileError] = []
        n_files = len(files)
        logger.info("Uploading %d file(s) to aisle %s", n_files, aisle_id)
        for file_index, uf in enumerate(files):
            asset, err = self._ingest_one_file(
                aisle_id=aisle_id,
                uf=uf,
                now=now,
                file_index=file_index,
                batch_id=batch_id,
            )
            if err is not None:
                errors.append(err)
                continue
            if asset is not None:
                created.append(asset)
        if created:
            try:
                self._materializer.finalize_aisle_after_source_assets_changed(
                    aisle=aisle,
                    inventory_id=inventory_id,
                    now=now,
                )
            except Exception:
                # Assets are already persisted; a reconciliation failure (e.g. status rollup)
                # must not turn a partially-successful upload into a hard error for the client.
                logger.exception(
                    "Aisle finalize-after-upload failed aisle_id=%s inventory_id=%s "
                    "(uploaded %d asset(s) will still be reported as successful)",
                    aisle_id,
                    inventory_id,
                    len(created),
                )
        return AisleAssetUploadBatchResult(
            upload_batch_id=batch_id,
            assets=created,
            errors=errors,
        )
