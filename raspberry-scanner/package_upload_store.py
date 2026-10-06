"""Durable local state for Phase 2 export + Phase 3 upload (per capture session)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from durable_io import fsync_directory

UploadState = Literal["EXPORTED", "PREVIEWED", "CONFIRMED", "FAILED"]


@dataclass
class PackageUploadRecord:
    capture_session_id: str
    export_id: str
    inventory_id: str
    aisle_id: str
    zip_path: str
    state: UploadState
    package_id: str | None = None
    error: str | None = None
    previewed_at: str | None = None
    confirmed_at: str | None = None
    exported_at: str | None = None
    csv_checksum_sha256: str | None = None
    package_checksum_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_session_id": self.capture_session_id,
            "export_id": self.export_id,
            "inventory_id": self.inventory_id,
            "aisle_id": self.aisle_id,
            "zip_path": self.zip_path,
            "state": self.state,
            "package_id": self.package_id,
            "error": self.error,
            "previewed_at": self.previewed_at,
            "confirmed_at": self.confirmed_at,
            "exported_at": self.exported_at,
            "csv_checksum_sha256": self.csv_checksum_sha256,
            "package_checksum_sha256": self.package_checksum_sha256,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PackageUploadRecord:
        return cls(
            capture_session_id=str(raw["capture_session_id"]),
            export_id=str(raw["export_id"]),
            inventory_id=str(raw["inventory_id"]),
            aisle_id=str(raw["aisle_id"]),
            zip_path=str(raw["zip_path"]),
            state=str(raw["state"]),
            package_id=raw.get("package_id"),
            error=raw.get("error"),
            previewed_at=raw.get("previewed_at"),
            confirmed_at=raw.get("confirmed_at"),
            exported_at=raw.get("exported_at"),
            csv_checksum_sha256=raw.get("csv_checksum_sha256"),
            package_checksum_sha256=raw.get("package_checksum_sha256"),
        )


class PackageUploadStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for_session(self, capture_session_id: str) -> Path:
        safe = capture_session_id.replace("/", "_")
        return self._root / f"{safe}.json"

    def load(self, capture_session_id: str) -> PackageUploadRecord | None:
        path = self._path_for_session(capture_session_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(raw, dict):
            return None
        return PackageUploadRecord.from_dict(raw)

    def save(self, record: PackageUploadRecord) -> None:
        path = self._path_for_session(record.capture_session_id)
        body = json.dumps(record.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            fsync_directory(path.parent)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
