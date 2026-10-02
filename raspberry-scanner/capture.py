"""Ephemeral aisle capture and atomic Dinamic Scanner TXT export."""

from __future__ import annotations

import os
import logging
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recognition import RecognitionService
from scanner_service import Reading

LOGGER = logging.getLogger(__name__)


class CaptureError(ValueError):
    """A local capture cannot start, record, or export safely."""


@dataclass(frozen=True)
class ExportRecord:
    sequence: int
    line: str


class CaptureService:
    """Owns one in-memory aisle capture; export is the only durable result."""

    def __init__(self, recognition: RecognitionService, export_directory: Path) -> None:
        self._recognition = recognition
        self._export_directory = export_directory
        self._lock = threading.Lock()
        self._state = "IDLE"
        self._aisle_code: str | None = None
        self._selection: dict[str, object] | None = None
        self._records: list[ExportRecord] = []
        self._accepted_count = 0
        self._physical_count = 0
        self._f2_accepted_count = 0
        self._rejected_count = 0
        self._not_exportable_count = 0
        self._listener_error: str | None = None
        self._started_at: str | None = None
        self._filename: str | None = None
        self._archived_filename: str | None = None
        self._error: str | None = None

    def start(self, aisle_code: object) -> dict[str, object]:
        code = _validate_aisle_code(aisle_code)
        selection = self._recognition.selection()
        if not selection.get("client_id"):
            raise CaptureError("client_selection_required")
        with self._lock:
            if self._state != "IDLE" and self._state != "FINISHED":
                raise CaptureError("capture_requires_resolution")
            self._state = "ACTIVE"
            self._aisle_code = code
            self._selection = selection
            self._records = []
            self._accepted_count = 0
            self._physical_count = 0
            self._f2_accepted_count = 0
            self._rejected_count = 0
            self._not_exportable_count = 0
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._filename = None
            self._archived_filename = None
            self._error = None
            self._listener_error = None
            LOGGER.info("capture started aisle=%s", code)
            return self._snapshot_locked()

    def abort_start(self, error: str) -> dict[str, object]:
        """Rollback a start transition that could not start the scanner."""
        with self._lock:
            if self._state != "ACTIVE" or self._records:
                raise CaptureError("capture_abort_not_available")
            self._state = "IDLE"
            self._aisle_code = None
            self._selection = None
            self._started_at = None
            self._error = error
            return self._snapshot_locked()

    def record(self, reading: Reading) -> None:
        decision = reading.decision or {}
        with self._lock:
            if self._state != "ACTIVE":
                return
            self._physical_count += 1
            if decision.get("accepted") is not True:
                self._rejected_count += 1
                return
            self._f2_accepted_count += 1
            line = _export_line(reading.value, decision)
            if line is None:
                self._not_exportable_count += 1
                return
            self._accepted_count += 1
            self._records.append(ExportRecord(reading.sequence, line))

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
            if not self._records:
                self._state = "FINISHED"
                self._filename = None
                self._error = None
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
                LOGGER.exception("capture export failed aisle=%s", self._aisle_code)
                raise CaptureError(self._error) from exc
            self._state = "FINISHED"
            self._filename = filename
            self._archived_filename = archived_filename
            self._error = None
            LOGGER.info(
                "capture export succeeded aisle=%s filename=%s archived_filename=%s",
                self._aisle_code,
                filename,
                archived_filename,
            )
            return self._snapshot_locked()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, object]:
        selection = self._selection or {}
        return {
            "state": self._state,
            "aisle_code": self._aisle_code,
            "client_id": selection.get("client_id"),
            "supplier_id": selection.get("supplier_id"),
            "selection_mode": selection.get("selection_mode"),
            "accepted_count": self._accepted_count,
            "physical_count": self._physical_count,
            "f2_accepted_count": self._f2_accepted_count,
            "rejected_count": self._rejected_count,
            "not_exportable_count": self._not_exportable_count,
            "started_at": self._started_at,
            "filename": self._filename,
            "archived_filename": self._archived_filename,
            "error": self._error,
            "listener_error": self._listener_error,
        }


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
    """Map F2's structured decision to the existing TXT grammar without reparse."""
    classification = decision.get("classification")
    recognition = decision.get("recognition")
    # ALL is F2's explicitly accepted, transport-preserving mode: it has no
    # supplier/Dinamic recognition result to normalize. Keep the scanner value
    # verbatim for the backend import flow to interpret later.
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
        # D1 is already validated by F2; supplier payload is intentionally kept
        # raw because backend's supplier profile parser consumes its native form.
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
    """Publish ``filename`` atomically and archive a previous export first.

    The canonical filename must remain ``<aisle>.txt`` because the backend uses
    it to identify the aisle. A hard link snapshots an existing export without
    removing it; only after that succeeds is the canonical path atomically
    replaced. Therefore a failed replacement still leaves the old export at
    both its canonical path and its archived path.
    """
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
                    # link(2) snapshots the exact previous bytes and refuses to
                    # overwrite an archive created by an earlier capture.
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
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return archived_filename
