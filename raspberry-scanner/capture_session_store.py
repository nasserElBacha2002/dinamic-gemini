"""Durable per-session capture state (atomic JSON files)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

PhotoStatus = Literal["CAPTURING", "COMPLETE", "PHOTO_FAILED"]

_ACTIVE_FILE = "_active.json"


@dataclass
class PhotoCaptureRecord:
    capture_photo_id: str
    sequence_number: int
    scanner_sequence: int
    export_line: str
    status: PhotoStatus
    captured_at: str
    file_name: str | None = None
    photo_sha256: str | None = None
    photo_size_bytes: int | None = None
    error: str | None = None
    scan_semantics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "capture_photo_id": self.capture_photo_id,
            "sequence_number": self.sequence_number,
            "scanner_sequence": self.scanner_sequence,
            "export_line": self.export_line,
            "status": self.status,
            "captured_at": self.captured_at,
            "file_name": self.file_name,
            "photo_sha256": self.photo_sha256,
            "photo_size_bytes": self.photo_size_bytes,
            "error": self.error,
        }
        if self.scan_semantics is not None:
            payload["scan_semantics"] = self.scan_semantics
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PhotoCaptureRecord:
        semantics = raw.get("scan_semantics")
        return cls(
            capture_photo_id=str(raw["capture_photo_id"]),
            sequence_number=int(raw["sequence_number"]),
            scanner_sequence=int(raw["scanner_sequence"]),
            export_line=str(raw["export_line"]),
            status=str(raw["status"]),
            captured_at=str(raw.get("captured_at") or ""),
            file_name=raw.get("file_name"),
            photo_sha256=raw.get("photo_sha256"),
            photo_size_bytes=(
                int(raw["photo_size_bytes"])
                if raw.get("photo_size_bytes") is not None
                else None
            ),
            error=raw.get("error"),
            scan_semantics=dict(semantics) if isinstance(semantics, dict) else None,
        )


@dataclass
class CaptureSessionState:
    capture_session_id: str
    aisle_code: str
    state: str
    selection: dict[str, object]
    started_at: str | None
    inventory_id: str | None = None
    aisle_id: str | None = None
    finished_at: str | None = None
    next_sequence_number: int = 1
    export_records: list[tuple[int, str]] = field(default_factory=list)
    photos: list[PhotoCaptureRecord] = field(default_factory=list)
    physical_count: int = 0
    f2_accepted_count: int = 0
    rejected_count: int = 0
    not_exportable_count: int = 0
    accepted_count: int = 0
    filename: str | None = None
    archived_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_session_id": self.capture_session_id,
            "aisle_code": self.aisle_code,
            "state": self.state,
            "selection": self.selection,
            "started_at": self.started_at,
            "inventory_id": self.inventory_id,
            "aisle_id": self.aisle_id,
            "finished_at": self.finished_at,
            "next_sequence_number": self.next_sequence_number,
            "export_records": [
                {"scanner_sequence": seq, "line": line}
                for seq, line in self.export_records
            ],
            "photos": [p.to_dict() for p in self.photos],
            "physical_count": self.physical_count,
            "f2_accepted_count": self.f2_accepted_count,
            "rejected_count": self.rejected_count,
            "not_exportable_count": self.not_exportable_count,
            "accepted_count": self.accepted_count,
            "filename": self.filename,
            "archived_filename": self.archived_filename,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CaptureSessionState:
        export_records = [
            (int(item["scanner_sequence"]), str(item["line"]))
            for item in raw.get("export_records", [])
        ]
        photos = [
            PhotoCaptureRecord.from_dict(item) for item in raw.get("photos", [])
        ]
        return cls(
            capture_session_id=str(raw["capture_session_id"]),
            aisle_code=str(raw["aisle_code"]),
            state=str(raw["state"]),
            selection=dict(raw.get("selection") or {}),
            started_at=raw.get("started_at"),
            inventory_id=(
                str(raw["inventory_id"]).strip()
                if raw.get("inventory_id")
                else None
            ),
            aisle_id=(
                str(raw["aisle_id"]).strip() if raw.get("aisle_id") else None
            ),
            finished_at=raw.get("finished_at"),
            next_sequence_number=int(raw.get("next_sequence_number", 1)),
            export_records=export_records,
            photos=photos,
            physical_count=int(raw.get("physical_count", 0)),
            f2_accepted_count=int(raw.get("f2_accepted_count", 0)),
            rejected_count=int(raw.get("rejected_count", 0)),
            not_exportable_count=int(raw.get("not_exportable_count", 0)),
            accepted_count=int(raw.get("accepted_count", 0)),
            filename=raw.get("filename"),
            archived_filename=raw.get("archived_filename"),
        )


class CaptureSessionStore:
    """Persists one JSON file per session; ``_active.json`` points at the live session."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def _session_path(self, capture_session_id: str) -> Path:
        return self._root / f"{capture_session_id}.json"

    def _active_path(self) -> Path:
        return self._root / _ACTIVE_FILE

    def load_session(self, capture_session_id: str) -> CaptureSessionState | None:
        path = self._session_path(capture_session_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return CaptureSessionState.from_dict(data)

    def load_active(self) -> CaptureSessionState | None:
        try:
            raw = self._active_path().read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        session_id = str(data.get("capture_session_id") or "").strip()
        if not session_id:
            return None
        state = self.load_session(session_id)
        if state is None or state.state != "ACTIVE":
            return None
        return state

    def save(self, state: CaptureSessionState) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._write_json(self._session_path(state.capture_session_id), state.to_dict())
        if state.state == "ACTIVE":
            self._write_json(
                self._active_path(),
                {"capture_session_id": state.capture_session_id},
            )
        elif state.state in {"FINISHED", "EXPORT_FAILED"}:
            self.clear_active_pointer()

    def clear_active_pointer(self) -> None:
        try:
            self._active_path().unlink()
        except FileNotFoundError:
            pass

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
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
