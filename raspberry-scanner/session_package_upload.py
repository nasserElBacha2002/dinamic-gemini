"""Phase 3: upload Phase 2 ZIP via existing v3 preview/confirm endpoints."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from capture_session_store import CaptureSessionState, CaptureSessionStore
from inventory_backend_client import (
    InventoryBackendClient,
    InventoryBackendClientError,
    PackageApiResponse,
    inventory_backend_client_from_environment,
)
from package_upload_store import PackageUploadRecord, PackageUploadStore, UploadState
from session_package_export import (
    SessionPackageExportContext,
    SessionPackageExportError,
    SessionPackageExportResult,
    export_finished_session_package,
)

PREVIEW_READY_STATUS = "PREVIEWED"
CONFIRM_SUCCESS_STATUS = "CONFIRMED"
DEFAULT_CONFLICT_POLICY = "SKIP"

_LOCK_GUARD = threading.Lock()
_SESSION_LOCKS: dict[str, threading.Lock] = {}


def _session_operation_lock(capture_session_id: str) -> threading.Lock:
    with _LOCK_GUARD:
        lock = _SESSION_LOCKS.get(capture_session_id)
        if lock is None:
            lock = threading.Lock()
            _SESSION_LOCKS[capture_session_id] = lock
        return lock


class PackageUploadError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class SessionPackageExportOutcome:
    export_id: str
    zip_path: Path
    capture_session_id: str
    reused_existing_zip: bool
    upload_state: UploadState


@dataclass(frozen=True)
class SessionPackageUploadOutcome:
    export_id: str
    package_id: str
    capture_session_id: str
    inventory_id: str
    status: str
    preview_skipped: bool
    confirm_duplicate: bool
    upload_state: UploadState


class PackageBackendClient(Protocol):
    def preview_local_inventory_package(
        self,
        *,
        inventory_id: str,
        zip_bytes: bytes,
        file_name: str,
    ) -> PackageApiResponse: ...

    def confirm_local_inventory_package(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str = "SKIP",
    ) -> PackageApiResponse: ...


def device_id_from_environment() -> str:
    return (os.environ.get("DINAMIC_DEVICE_ID") or "raspberry-scanner").strip()


def export_context_for_session(session: CaptureSessionState) -> SessionPackageExportContext:
    from session_package_export import _session_inventory_context

    inventory_id, aisle_id = _session_inventory_context(session)
    return SessionPackageExportContext(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        device_id=device_id_from_environment(),
    )


def export_context_from_environment() -> SessionPackageExportContext:
    """Deprecated for export/upload; kept for tests that only need device defaults."""
    inventory_id = (os.environ.get("DINAMIC_INVENTORY_ID") or "").strip()
    aisle_id = (os.environ.get("DINAMIC_AISLE_ID") or "").strip()
    if inventory_id and aisle_id:
        return SessionPackageExportContext(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            device_id=device_id_from_environment(),
        )
    raise PackageUploadError(
        "SESSION_INVENTORY_CONTEXT_REQUIRED",
        "resolve export context from the capture session or DINAMIC_INVENTORY_CONTEXT_PATH",
    )


def package_export_directory_from_environment(
    export_directory: Path,
) -> Path:
    raw = os.environ.get("DINAMIC_PACKAGE_EXPORT_DIRECTORY")
    if raw and raw.strip():
        return Path(raw.strip())
    return export_directory / "packages"


def package_upload_store_from_environment(export_directory: Path) -> PackageUploadStore:
    root = export_directory.parent / "package-uploads"
    raw = os.environ.get("DINAMIC_PACKAGE_UPLOAD_STATE_DIRECTORY")
    if raw and raw.strip():
        root = Path(raw.strip())
    return PackageUploadStore(root)


def ensure_session_package_exported(
    *,
    session_store: CaptureSessionStore,
    photos_root: Path,
    output_directory: Path,
    capture_session_id: str,
    context: SessionPackageExportContext,
    upload_store: PackageUploadStore,
) -> SessionPackageExportOutcome:
    with _session_operation_lock(capture_session_id):
        record = upload_store.load(capture_session_id)
        if record is not None:
            zip_path = Path(record.zip_path)
            if zip_path.is_file():
                return SessionPackageExportOutcome(
                    export_id=record.export_id,
                    zip_path=zip_path,
                    capture_session_id=capture_session_id,
                    reused_existing_zip=True,
                    upload_state=record.state,
                )
            if record.state in {"PREVIEWED", "CONFIRMED"}:
                raise PackageUploadError(
                    "EXPORT_RECOVERY_LOCKED",
                    "ZIP missing after preview/confirm; cannot rebuild export identity",
                )
            export_id = record.export_id
            exported_at = record.exported_at
            expected_csv = record.csv_checksum_sha256
            expected_package = record.package_checksum_sha256
        else:
            export_id = None
            exported_at = None
            expected_csv = None
            expected_package = None

        try:
            result = export_finished_session_package(
                session_store=session_store,
                photos_root=photos_root,
                output_directory=output_directory,
                capture_session_id=capture_session_id,
                context=context,
                export_id=export_id,
                exported_at=exported_at,
                expected_csv_checksum_sha256=expected_csv,
                expected_package_checksum_sha256=expected_package,
            )
        except SessionPackageExportError as exc:
            raise PackageUploadError(exc.code, str(exc)) from exc

        _persist_export_record(
            upload_store,
            result=result,
            context=context,
            previous=record,
        )
        return SessionPackageExportOutcome(
            export_id=result.export_id,
            zip_path=result.zip_path,
            capture_session_id=result.capture_session_id,
            reused_existing_zip=False,
            upload_state="EXPORTED",
        )


def upload_session_package(
    *,
    capture_session_id: str,
    inventory_id: str,
    upload_store: PackageUploadStore,
    backend_client: PackageBackendClient,
    conflict_policy: str = DEFAULT_CONFLICT_POLICY,
) -> SessionPackageUploadOutcome:
    with _session_operation_lock(capture_session_id):
        return _upload_session_package_locked(
            capture_session_id=capture_session_id,
            inventory_id=inventory_id,
            upload_store=upload_store,
            backend_client=backend_client,
            conflict_policy=conflict_policy,
        )


def _upload_session_package_locked(
    *,
    capture_session_id: str,
    inventory_id: str,
    upload_store: PackageUploadStore,
    backend_client: PackageBackendClient,
    conflict_policy: str,
) -> SessionPackageUploadOutcome:
    record = upload_store.load(capture_session_id)
    if record is None:
        raise PackageUploadError(
            "PACKAGE_NOT_EXPORTED",
            "export the session package before upload",
        )
    if record.inventory_id != inventory_id:
        raise PackageUploadError(
            "INVENTORY_ID_MISMATCH",
            "configured inventory_id does not match exported package",
        )

    if record.state == "CONFIRMED" and record.package_id:
        return SessionPackageUploadOutcome(
            export_id=record.export_id,
            package_id=record.package_id,
            capture_session_id=capture_session_id,
            inventory_id=record.inventory_id,
            status=CONFIRM_SUCCESS_STATUS,
            preview_skipped=True,
            confirm_duplicate=True,
            upload_state="CONFIRMED",
        )

    zip_path = Path(record.zip_path)
    if not zip_path.is_file():
        raise PackageUploadError(
            "PACKAGE_ZIP_MISSING",
            f"exported ZIP not found at {zip_path}",
        )

    preview_skipped = record.state == "PREVIEWED"
    preview_response: PackageApiResponse | None = None

    if not preview_skipped:
        try:
            zip_bytes = zip_path.read_bytes()
            preview_response = backend_client.preview_local_inventory_package(
                inventory_id=inventory_id,
                zip_bytes=zip_bytes,
                file_name=zip_path.name,
            )
        except InventoryBackendClientError as exc:
            _mark_failed(upload_store, record, exc.code, str(exc))
            raise PackageUploadError(exc.code, str(exc)) from exc

        try:
            _validate_preview_response(
                preview_response,
                expected_export_id=record.export_id,
                expected_inventory_id=inventory_id,
            )
        except PackageUploadError as exc:
            _mark_failed(upload_store, record, exc.code, str(exc))
            raise

        record = _mark_previewed(upload_store, record, preview_response)

    try:
        confirm_response = backend_client.confirm_local_inventory_package(
            inventory_id=inventory_id,
            export_id=record.export_id,
            conflict_policy=conflict_policy,
        )
    except InventoryBackendClientError as exc:
        _mark_failed(upload_store, record, exc.code, str(exc))
        raise PackageUploadError(exc.code, str(exc)) from exc

    try:
        _validate_confirm_response(
            confirm_response,
            expected_export_id=record.export_id,
            expected_inventory_id=inventory_id,
        )
    except PackageUploadError as exc:
        _mark_failed(upload_store, record, exc.code, str(exc))
        raise

    record = _mark_confirmed(upload_store, record, confirm_response)
    return SessionPackageUploadOutcome(
        export_id=record.export_id,
        package_id=confirm_response.package_id,
        capture_session_id=capture_session_id,
        inventory_id=inventory_id,
        status=confirm_response.status,
        preview_skipped=preview_skipped,
        confirm_duplicate=confirm_response.duplicate,
        upload_state="CONFIRMED",
    )


def build_backend_client_from_environment() -> InventoryBackendClient:
    config = inventory_backend_client_from_environment()
    return InventoryBackendClient(config)


def _persist_export_record(
    upload_store: PackageUploadStore,
    *,
    result: SessionPackageExportResult,
    context: SessionPackageExportContext,
    previous: PackageUploadRecord | None,
) -> None:
    state: UploadState = "EXPORTED"
    package_id = None
    previewed_at = None
    confirmed_at = None
    if previous is not None and previous.state in {"CONFIRMED", "PREVIEWED"}:
        state = previous.state
        package_id = previous.package_id
        previewed_at = previous.previewed_at
        confirmed_at = previous.confirmed_at
    upload_store.save(
        PackageUploadRecord(
            capture_session_id=result.capture_session_id,
            export_id=result.export_id,
            inventory_id=context.inventory_id,
            aisle_id=context.aisle_id,
            zip_path=str(result.zip_path),
            state=state,
            package_id=package_id,
            error=None,
            previewed_at=previewed_at,
            confirmed_at=confirmed_at,
            exported_at=result.exported_at,
            csv_checksum_sha256=result.csv_checksum_sha256,
            package_checksum_sha256=result.package_checksum_sha256,
        )
    )


def _validate_preview_response(
    response: PackageApiResponse,
    *,
    expected_export_id: str,
    expected_inventory_id: str,
) -> None:
    if response.inventory_id != expected_inventory_id:
        raise PackageUploadError(
            "PREVIEW_INVENTORY_MISMATCH",
            "preview response inventory_id does not match request",
        )
    if response.export_id != expected_export_id:
        raise PackageUploadError(
            "PREVIEW_EXPORT_ID_MISMATCH",
            "preview response export_id does not match local package",
        )
    if response.status != PREVIEW_READY_STATUS:
        raise PackageUploadError(
            "PREVIEW_NOT_READY",
            f"preview status {response.status!r} is not ready for confirm",
        )


def _validate_confirm_response(
    response: PackageApiResponse,
    *,
    expected_export_id: str,
    expected_inventory_id: str,
) -> None:
    if response.inventory_id != expected_inventory_id:
        raise PackageUploadError(
            "CONFIRM_INVENTORY_MISMATCH",
            "confirm response inventory_id does not match request",
        )
    if response.export_id != expected_export_id:
        raise PackageUploadError(
            "CONFIRM_EXPORT_ID_MISMATCH",
            "confirm response export_id does not match local package",
        )
    if response.status != CONFIRM_SUCCESS_STATUS:
        raise PackageUploadError(
            "CONFIRM_NOT_COMPLETE",
            f"confirm status {response.status!r} is not confirmed",
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mark_previewed(
    upload_store: PackageUploadStore,
    record: PackageUploadRecord,
    preview: PackageApiResponse,
) -> PackageUploadRecord:
    updated = PackageUploadRecord(
        capture_session_id=record.capture_session_id,
        export_id=record.export_id,
        inventory_id=record.inventory_id,
        aisle_id=record.aisle_id,
        zip_path=record.zip_path,
        state="PREVIEWED",
        package_id=preview.package_id,
        error=None,
        previewed_at=_utc_now_iso(),
        confirmed_at=record.confirmed_at,
        exported_at=record.exported_at,
        csv_checksum_sha256=record.csv_checksum_sha256,
        package_checksum_sha256=record.package_checksum_sha256,
    )
    upload_store.save(updated)
    return updated


def _mark_confirmed(
    upload_store: PackageUploadStore,
    record: PackageUploadRecord,
    confirm: PackageApiResponse,
) -> PackageUploadRecord:
    updated = PackageUploadRecord(
        capture_session_id=record.capture_session_id,
        export_id=record.export_id,
        inventory_id=record.inventory_id,
        aisle_id=record.aisle_id,
        zip_path=record.zip_path,
        state="CONFIRMED",
        package_id=confirm.package_id,
        error=None,
        previewed_at=record.previewed_at or _utc_now_iso(),
        confirmed_at=_utc_now_iso(),
        exported_at=record.exported_at,
        csv_checksum_sha256=record.csv_checksum_sha256,
        package_checksum_sha256=record.package_checksum_sha256,
    )
    upload_store.save(updated)
    return updated


def _mark_failed(
    upload_store: PackageUploadStore,
    record: PackageUploadRecord,
    code: str,
    message: str,
) -> None:
    current = upload_store.load(record.capture_session_id)
    if current is not None and current.state == "CONFIRMED":
        return
    upload_store.save(
        PackageUploadRecord(
            capture_session_id=record.capture_session_id,
            export_id=record.export_id,
            inventory_id=record.inventory_id,
            aisle_id=record.aisle_id,
            zip_path=record.zip_path,
            state="FAILED",
            package_id=record.package_id,
            error=f"{code}: {message}",
            previewed_at=record.previewed_at,
            confirmed_at=record.confirmed_at,
            exported_at=record.exported_at,
            csv_checksum_sha256=record.csv_checksum_sha256,
            package_checksum_sha256=record.package_checksum_sha256,
        )
    )
