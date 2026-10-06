"""Ephemeral aisle capture, photo evidence, and atomic Dinamic Scanner TXT export."""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import tempfile
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from camera import Camera, CameraError
from capture_session_store import (
    CaptureSessionState,
    CaptureSessionStore,
    PhotoCaptureRecord,
)
from inventory_context import InventoryContextError, resolve_inventory_aisle_for_capture
from recognition import RecognitionService
from scan_semantics import build_scan_semantics
from scanner_service import Reading

LOGGER = logging.getLogger(__name__)

_CAMERA_OPERATION_ERRORS = (CameraError, OSError, TimeoutError, ValueError)


class CaptureError(ValueError):
    """A local capture cannot start, record, or export safely."""


@dataclass(frozen=True)
class ExportRecord:
    sequence: int
    line: str


@dataclass(frozen=True)
class _PhotoCaptureJob:
    capture_photo_id: str
    sequence_number: int
    scanner_sequence: int
    export_line: str
    file_name: str
    session_id: str
    captured_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CaptureService:
    """Owns aisle capture; durable per-session state when a camera store is configured."""

    def __init__(
        self,
        recognition: RecognitionService,
        export_directory: Path,
        *,
        camera: Camera | None = None,
        session_store: CaptureSessionStore | None = None,
        photos_root: Path | None = None,
        bind_inventory_context: bool = True,
    ) -> None:
        self._recognition = recognition
        self._export_directory = export_directory
        self._camera = camera
        self._session_store = session_store
        self._photos_root = photos_root or (export_directory / "photos")
        self._bind_inventory_context = bind_inventory_context
        self._inventory_id: str | None = None
        self._aisle_id: str | None = None
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._accepting_records = True
        self._aisle_code: str | None = None
        self._selection: dict[str, object] | None = None
        self._records: list[ExportRecord] = []
        self._photo_records: list[PhotoCaptureRecord] = []
        self._capture_session_id: str | None = None
        self._next_sequence_number = 1
        self._accepted_count = 0
        self._physical_count = 0
        self._f2_accepted_count = 0
        self._rejected_count = 0
        self._not_exportable_count = 0
        self._listener_error: str | None = None
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._filename: str | None = None
        self._archived_filename: str | None = None
        self._error: str | None = None
        self._photo_queue: queue.Queue[_PhotoCaptureJob | None] | None = None
        self._photo_worker: threading.Thread | None = None
        self._pipeline_cond = threading.Condition()
        self._pipeline_inflight = 0
        self._pipeline_fatal_error: str | None = None
        if self._camera is not None and self._session_store is not None:
            self._photo_queue = queue.Queue()
            self._photo_worker = threading.Thread(
                target=self._photo_worker_loop,
                name="capture-photo-worker",
                daemon=True,
            )
            self._photo_worker.start()
        self._restore_active_session_if_present()

    def start(self, aisle_code: object, *, inventory_id: object | None = None) -> dict[str, object]:
        code = _validate_aisle_code(aisle_code)
        selection = self._recognition.selection()
        if not selection.get("client_id"):
            raise CaptureError("client_selection_required")
        requested_inventory_id = (
            inventory_id.strip() if isinstance(inventory_id, str) else None
        )
        bound_inventory_id: str | None = None
        aisle_id: str | None = None
        if self._session_store is not None and self._bind_inventory_context:
            try:
                resolved = resolve_inventory_aisle_for_capture(
                    code,
                    inventory_id=requested_inventory_id,
                    client_id=str(selection.get("client_id") or "") or None,
                )
            except InventoryContextError as exc:
                raise CaptureError(exc.code) from exc
            bound_inventory_id = resolved.inventory_id
            aisle_id = resolved.aisle_id
        with self._lock:
            if self._state != "IDLE" and self._state != "FINISHED":
                raise CaptureError("capture_requires_resolution")
            self._state = "ACTIVE"
            self._accepting_records = True
            self._aisle_code = code
            self._inventory_id = bound_inventory_id
            self._aisle_id = aisle_id
            self._selection = selection
            self._records = []
            self._photo_records = []
            self._capture_session_id = str(uuid.uuid4())
            self._next_sequence_number = 1
            self._accepted_count = 0
            self._physical_count = 0
            self._f2_accepted_count = 0
            self._rejected_count = 0
            self._not_exportable_count = 0
            self._started_at = _utc_now_iso()
            self._finished_at = None
            self._filename = None
            self._archived_filename = None
            self._error = None
            self._listener_error = None
            self._persist_session_locked()
            LOGGER.info(
                "capture started aisle=%s session=%s",
                code,
                self._capture_session_id,
            )
            return self._snapshot_locked()

    def abort_start(self, error: str) -> dict[str, object]:
        with self._lock:
            if self._state != "ACTIVE" or self._records:
                raise CaptureError("capture_abort_not_available")
            self._state = "IDLE"
            self._accepting_records = False
            self._aisle_code = None
            self._selection = None
            self._started_at = None
            self._capture_session_id = None
            self._error = error
            if self._session_store is not None:
                self._session_store.clear_active_pointer()
            return self._snapshot_locked()

    def record(self, reading: Reading) -> None:
        job_to_enqueue: _PhotoCaptureJob | None = None
        with self._lock:
            self._raise_if_pipeline_fatal()
            if self._state != "ACTIVE" or not self._accepting_records:
                return
            self._physical_count += 1
            decision = reading.decision or {}
            if decision.get("accepted") is not True:
                self._rejected_count += 1
                self._persist_session_locked()
                return
            self._f2_accepted_count += 1
            line = _export_line(reading.value, decision)
            if line is None:
                self._not_exportable_count += 1
                self._persist_session_locked()
                return
            semantics = build_scan_semantics(
                reading.value,
                decision,
                export_line=line,
            )
            semantics_dict = semantics.to_dict() if semantics is not None else None
            self._accepted_count += 1
            self._records.append(ExportRecord(reading.sequence, line))
            if (
                self._camera is not None
                and self._session_store is not None
                and self._capture_session_id is not None
            ):
                captured_at = _utc_now_iso()
                capture_photo_id = str(uuid.uuid4())
                sequence_number = self._next_sequence_number
                self._next_sequence_number += 1
                file_name = _photo_file_name(capture_photo_id, sequence_number)
                self._photo_records.append(
                    PhotoCaptureRecord(
                        capture_photo_id=capture_photo_id,
                        sequence_number=sequence_number,
                        scanner_sequence=reading.sequence,
                        export_line=line,
                        status="CAPTURING",
                        captured_at=captured_at,
                        file_name=file_name,
                        scan_semantics=semantics_dict,
                    )
                )
                job_to_enqueue = _PhotoCaptureJob(
                    capture_photo_id=capture_photo_id,
                    sequence_number=sequence_number,
                    scanner_sequence=reading.sequence,
                    export_line=line,
                    file_name=file_name,
                    session_id=self._capture_session_id,
                    captured_at=captured_at,
                )
                with self._pipeline_cond:
                    self._pipeline_inflight += 1
                try:
                    self._persist_session_locked()
                except Exception as exc:
                    self._photo_records.pop()
                    self._next_sequence_number -= 1
                    with self._pipeline_cond:
                        self._pipeline_inflight -= 1
                        self._pipeline_cond.notify_all()
                    message = f"{type(exc).__name__}: {exc}"
                    self._pipeline_fatal_error = (
                        f"capture_metadata_persistence_failed: {message}"
                    )
                    self._accepting_records = False
                    self._error = self._pipeline_fatal_error
                    job_to_enqueue = None
                    raise CaptureError(self._pipeline_fatal_error) from exc
        if job_to_enqueue is not None:
            assert self._photo_queue is not None
            self._photo_queue.put(job_to_enqueue)

    def report_listener_error(self, exc: Exception) -> None:
        with self._lock:
            if self._state == "ACTIVE":
                self._listener_error = f"{type(exc).__name__}: {exc}"
                LOGGER.error(
                    "capture listener failed aisle=%s error=%s",
                    self._aisle_code,
                    self._listener_error,
                )

    def finish(self) -> dict[str, object]:
        with self._lock:
            if self._state not in {"ACTIVE", "EXPORT_FAILED"}:
                raise CaptureError("capture_not_active")
            self._accepting_records = False
        self._wait_for_photo_pipeline_idle()
        self._raise_if_pipeline_fatal()
        with self._lock:
            if self._state not in {"ACTIVE", "EXPORT_FAILED"}:
                raise CaptureError("capture_not_active")
            if any(p.status == "CAPTURING" for p in self._photo_records):
                raise CaptureError("capture_photos_not_terminal")
            if not self._records:
                self._state = "FINISHED"
                self._finished_at = _utc_now_iso()
                self._filename = None
                self._error = None
                self._persist_session_locked()
                LOGGER.info(
                    "capture finished without export aisle=%s physical=%s f2_accepted=%s",
                    self._aisle_code,
                    self._physical_count,
                    self._f2_accepted_count,
                )
                return self._snapshot_locked()
            assert self._aisle_code is not None
            filename = f"{self._aisle_code}.txt"
            content = "\n".join(record.line for record in self._records) + "\n"
            try:
                archived_filename = _write_atomic_preserving_existing(
                    self._export_directory,
                    filename,
                    content,
                )
            except OSError as exc:
                self._state = "EXPORT_FAILED"
                self._error = f"export_write_failed: {type(exc).__name__}: {exc}"
                self._persist_session_locked()
                LOGGER.exception("capture export failed aisle=%s", self._aisle_code)
                raise CaptureError(self._error) from exc
            self._state = "FINISHED"
            self._finished_at = _utc_now_iso()
            self._filename = filename
            self._archived_filename = archived_filename
            self._error = None
            self._persist_session_locked()
            LOGGER.info(
                "capture export succeeded aisle=%s filename=%s archived_filename=%s",
                self._aisle_code,
                filename,
                archived_filename,
            )
            return self._snapshot_locked()

    def wait_for_photo_pipeline_idle(self, timeout: float | None = 5.0) -> None:
        """Block until queued/in-flight photo captures finish (tests and finish())."""
        self._wait_for_photo_pipeline_idle(timeout=timeout)

    def load_finished_session(self, capture_session_id: str) -> dict[str, object] | None:
        if self._session_store is None:
            return None
        stored = self._session_store.load_session(capture_session_id)
        if stored is None or stored.state != "FINISHED":
            return None
        return _snapshot_from_state(stored)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, object]:
        selection = self._selection or {}
        photos = [
            {
                "capture_photo_id": record.capture_photo_id,
                "sequence_number": record.sequence_number,
                "scanner_sequence": record.scanner_sequence,
                "status": record.status,
                "captured_at": record.captured_at,
                "file_name": record.file_name,
                "photo_sha256": record.photo_sha256,
                "photo_size_bytes": record.photo_size_bytes,
                "error": record.error,
            }
            for record in self._photo_records
        ]
        return {
            "state": self._state,
            "aisle_code": self._aisle_code,
            "capture_session_id": self._capture_session_id,
            "client_id": selection.get("client_id"),
            "supplier_id": selection.get("supplier_id"),
            "selection_mode": selection.get("selection_mode"),
            "accepted_count": self._accepted_count,
            "physical_count": self._physical_count,
            "f2_accepted_count": self._f2_accepted_count,
            "rejected_count": self._rejected_count,
            "not_exportable_count": self._not_exportable_count,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "filename": self._filename,
            "archived_filename": self._archived_filename,
            "error": self._error,
            "listener_error": self._listener_error,
            "photos": photos,
            "next_sequence_number": self._next_sequence_number,
        }

    def _photo_worker_loop(self) -> None:
        assert self._photo_queue is not None
        while True:
            job = self._photo_queue.get()
            if job is None:
                self._photo_queue.task_done()
                break
            try:
                self._execute_photo_job(job)
            except Exception as exc:
                self._fail_pipeline_fatal(exc)
            finally:
                with self._pipeline_cond:
                    self._pipeline_inflight -= 1
                    self._pipeline_cond.notify_all()
                self._photo_queue.task_done()

    def _execute_photo_job(self, job: _PhotoCaptureJob) -> None:
        assert self._camera is not None
        photos_dir = self._session_photos_dir(job.session_id)
        photos_dir.mkdir(parents=True, exist_ok=True)
        final_path = photos_dir / job.file_name
        try:
            jpeg = self._camera.capture_jpeg()
            if not jpeg:
                raise CameraError("empty_jpeg")
            _write_jpeg_atomic(final_path, jpeg)
            digest = hashlib.sha256(jpeg).hexdigest()
            with self._lock:
                self._update_photo_record(
                    job.capture_photo_id,
                    status="COMPLETE",
                    photo_sha256=digest,
                    photo_size_bytes=len(jpeg),
                    error=None,
                )
        except _CAMERA_OPERATION_ERRORS as exc:
            LOGGER.warning(
                "photo capture failed session=%s photo=%s error=%s",
                job.session_id,
                job.capture_photo_id,
                exc,
            )
            _safe_unlink(final_path)
            with self._lock:
                self._update_photo_record(
                    job.capture_photo_id,
                    status="PHOTO_FAILED",
                    photo_sha256=None,
                    photo_size_bytes=None,
                    error=f"{type(exc).__name__}: {exc}",
                )

    def _raise_if_pipeline_fatal(self) -> None:
        if self._pipeline_fatal_error:
            raise CaptureError(f"capture_pipeline_fatal: {self._pipeline_fatal_error}")

    def _fail_pipeline_fatal(self, exc: BaseException) -> None:
        message = f"{type(exc).__name__}: {exc}"
        LOGGER.exception("capture photo worker failed: %s", message)
        with self._lock:
            self._accepting_records = False
            self._pipeline_fatal_error = message
        with self._pipeline_cond:
            self._pipeline_cond.notify_all()

    def _wait_for_photo_pipeline_idle(self, timeout: float | None = None) -> None:
        if self._photo_queue is None:
            self._raise_if_pipeline_fatal()
            return
        deadline = None
        if timeout is not None:
            deadline = time.monotonic() + timeout
        with self._pipeline_cond:
            while True:
                self._raise_if_pipeline_fatal()
                if self._pipeline_inflight <= 0 and self._photo_queue.empty():
                    return
                if deadline is None:
                    self._pipeline_cond.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CaptureError("capture_photo_pipeline_timeout")
                self._pipeline_cond.wait(timeout=remaining)

    def _update_photo_record(
        self,
        capture_photo_id: str,
        *,
        status: str,
        photo_sha256: str | None,
        photo_size_bytes: int | None,
        error: str | None,
    ) -> None:
        updated: list[PhotoCaptureRecord] = []
        for record in self._photo_records:
            if record.capture_photo_id != capture_photo_id:
                updated.append(record)
                continue
            updated.append(
                PhotoCaptureRecord(
                    capture_photo_id=record.capture_photo_id,
                    sequence_number=record.sequence_number,
                    scanner_sequence=record.scanner_sequence,
                    export_line=record.export_line,
                    status=status,
                    captured_at=record.captured_at,
                    file_name=record.file_name,
                    photo_sha256=photo_sha256,
                    photo_size_bytes=photo_size_bytes,
                    error=error,
                    scan_semantics=record.scan_semantics,
                )
            )
        self._photo_records = updated
        self._persist_session_locked()

    def _session_photos_dir(self, session_id: str) -> Path:
        return self._photos_root / session_id

    def _persist_session_locked(self) -> None:
        if self._session_store is None or self._capture_session_id is None:
            return
        if self._state not in {"ACTIVE", "EXPORT_FAILED", "FINISHED"}:
            return
        assert self._aisle_code is not None
        state = CaptureSessionState(
            capture_session_id=self._capture_session_id,
            aisle_code=self._aisle_code,
            state=self._state,
            selection=self._selection or {},
            started_at=self._started_at,
            inventory_id=self._inventory_id,
            aisle_id=self._aisle_id,
            finished_at=self._finished_at,
            next_sequence_number=self._next_sequence_number,
            export_records=[(r.sequence, r.line) for r in self._records],
            photos=list(self._photo_records),
            physical_count=self._physical_count,
            f2_accepted_count=self._f2_accepted_count,
            rejected_count=self._rejected_count,
            not_exportable_count=self._not_exportable_count,
            accepted_count=self._accepted_count,
            filename=self._filename,
            archived_filename=self._archived_filename,
        )
        self._session_store.save(state)

    def _restore_active_session_if_present(self) -> None:
        if self._session_store is None:
            return
        stored = self._session_store.load_active()
        if stored is None:
            return
        with self._lock:
            self._apply_session_state(stored)
            photos_dir = self._session_photos_dir(stored.capture_session_id)
            recovered: list[PhotoCaptureRecord] = []
            for photo in self._photo_records:
                if photo.status == "CAPTURING":
                    _cleanup_tmp_artifacts(photos_dir, photo.file_name)
                    if photo.file_name:
                        _safe_unlink(photos_dir / photo.file_name)
                    recovered.append(
                        PhotoCaptureRecord(
                            capture_photo_id=photo.capture_photo_id,
                            sequence_number=photo.sequence_number,
                            scanner_sequence=photo.scanner_sequence,
                            export_line=photo.export_line,
                            status="PHOTO_FAILED",
                            captured_at=photo.captured_at,
                            file_name=photo.file_name,
                            photo_sha256=None,
                            photo_size_bytes=None,
                            error="crash_recovery_incomplete_capture",
                            scan_semantics=photo.scan_semantics,
                        )
                    )
                    continue
                if photo.status == "COMPLETE" and photo.file_name:
                    final_path = photos_dir / photo.file_name
                    if not final_path.is_file():
                        recovered.append(
                            PhotoCaptureRecord(
                                capture_photo_id=photo.capture_photo_id,
                                sequence_number=photo.sequence_number,
                                scanner_sequence=photo.scanner_sequence,
                                export_line=photo.export_line,
                                status="PHOTO_FAILED",
                                captured_at=photo.captured_at,
                                file_name=photo.file_name,
                                photo_sha256=None,
                                photo_size_bytes=None,
                                error="missing_photo_file_after_restart",
                                scan_semantics=photo.scan_semantics,
                            )
                        )
                        continue
                recovered.append(photo)
            self._photo_records = recovered
            self._accepting_records = True
            self._persist_session_locked()
        LOGGER.info(
            "restored active capture session=%s aisle=%s photos=%s",
            stored.capture_session_id,
            stored.aisle_code,
            len(self._photo_records),
        )

    def _apply_session_state(self, stored: CaptureSessionState) -> None:
        self._state = stored.state
        self._aisle_code = stored.aisle_code
        self._inventory_id = stored.inventory_id
        self._aisle_id = stored.aisle_id
        self._selection = stored.selection
        self._capture_session_id = stored.capture_session_id
        self._next_sequence_number = stored.next_sequence_number
        self._started_at = stored.started_at
        self._finished_at = stored.finished_at
        self._physical_count = stored.physical_count
        self._f2_accepted_count = stored.f2_accepted_count
        self._rejected_count = stored.rejected_count
        self._not_exportable_count = stored.not_exportable_count
        self._accepted_count = stored.accepted_count
        self._filename = stored.filename
        self._archived_filename = stored.archived_filename
        self._records = [
            ExportRecord(seq, line) for seq, line in stored.export_records
        ]
        self._photo_records = list(stored.photos)


def _snapshot_from_state(stored: CaptureSessionState) -> dict[str, object]:
    photos = [
        {
            "capture_photo_id": record.capture_photo_id,
            "sequence_number": record.sequence_number,
            "scanner_sequence": record.scanner_sequence,
            "status": record.status,
            "captured_at": record.captured_at,
            "file_name": record.file_name,
            "photo_sha256": record.photo_sha256,
            "photo_size_bytes": record.photo_size_bytes,
            "error": record.error,
        }
        for record in stored.photos
    ]
    selection = stored.selection or {}
    return {
        "state": stored.state,
        "aisle_code": stored.aisle_code,
        "capture_session_id": stored.capture_session_id,
        "client_id": selection.get("client_id"),
        "supplier_id": selection.get("supplier_id"),
        "selection_mode": selection.get("selection_mode"),
        "accepted_count": stored.accepted_count,
        "physical_count": stored.physical_count,
        "f2_accepted_count": stored.f2_accepted_count,
        "rejected_count": stored.rejected_count,
        "not_exportable_count": stored.not_exportable_count,
        "started_at": stored.started_at,
        "finished_at": stored.finished_at,
        "filename": stored.filename,
        "archived_filename": stored.archived_filename,
        "error": None,
        "listener_error": None,
        "photos": photos,
        "next_sequence_number": stored.next_sequence_number,
    }


def _write_jpeg_atomic(final_path: Path, jpeg: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{final_path.name}.", dir=final_path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(jpeg)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, final_path)
        try:
            directory_fd = os.open(final_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        _safe_unlink(temp_path)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _cleanup_tmp_artifacts(photos_dir: Path, file_name: str | None) -> None:
    if not file_name:
        return
    for path in photos_dir.glob(f".{file_name}.*"):
        _safe_unlink(path)


def _photo_file_name(capture_photo_id: str, sequence_number: int) -> str:
    safe_id = capture_photo_id.replace("-", "").replace(" ", "_")
    safe_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in safe_id)
    return f"{sequence_number:04d}_{safe_id}.jpg"


def _validate_aisle_code(value: object) -> str:
    if not isinstance(value, str):
        raise CaptureError("aisle_code_required")
    code = value.strip()
    if not code:
        raise CaptureError("aisle_code_required")
    if ".." in code or "/" in code or "\\" in code or code in {".", ".."}:
        raise CaptureError("aisle_code_invalid")
    if any(unicodedata.category(char).startswith("C") for char in code):
        raise CaptureError("aisle_code_invalid")
    return code


def _export_line(raw: str, decision: dict[str, object]) -> str | None:
    classification = decision.get("classification")
    recognition = decision.get("recognition")
    if (
        decision.get("accepted") is True
        and classification == "RAW"
        and isinstance(recognition, dict)
        and recognition.get("selection_mode") == "ALL"
    ):
        return raw
    results = recognition.get("results") if isinstance(recognition, dict) else None
    if not isinstance(results, dict):
        return None
    if classification == "ITEM":
        item = results.get("ITEM")
        if not isinstance(item, dict) or item.get("status") != "VALID":
            return None
        return raw
    if classification == "POSITION":
        position = results.get("POSITION")
        if not isinstance(position, dict) or position.get("status") != "VALID":
            return None
        if position.get("source") == "SUPPLIER":
            return raw
        label_id = position.get("position_id")
        pallet = position.get("pallet")
        side = position.get("side")
        if not all(isinstance(value, str) and value.strip() for value in (label_id, pallet, side)):
            return None
        return f"POSITION|{label_id.strip()}|{pallet.strip()}|{side.strip().upper()}"
    return None


def _write_atomic_preserving_existing(
    directory: Path,
    filename: str,
    content: str,
) -> str | None:
    directory.mkdir(parents=True, exist_ok=True)
    final_path = directory / filename
    fd, temp_name = tempfile.mkstemp(prefix=f".{filename}.", dir=directory)
    temp_path = Path(temp_name)
    archived_filename: str | None = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if final_path.exists():
            archive_directory = directory / ".archive"
            archive_directory.mkdir(parents=True, exist_ok=True)
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            sequence = 1
            while True:
                archive_name = f"{stem}.{sequence}{suffix}"
                archive_path = archive_directory / archive_name
                try:
                    os.link(final_path, archive_path)
                    archived_filename = str(Path(".archive") / archive_name)
                    break
                except FileExistsError:
                    sequence += 1

        os.replace(temp_path, final_path)
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        _safe_unlink(temp_path)
    return archived_filename
