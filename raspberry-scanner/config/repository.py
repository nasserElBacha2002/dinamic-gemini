"""Durable last-known-good storage for the recognition snapshot."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import RecognitionSnapshot


class SnapshotRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> RecognitionSnapshot | None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        data = json.loads(raw)
        return RecognitionSnapshot.from_dict(data)

    def save(self, snapshot: RecognitionSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(snapshot.as_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        fd, temp_name = tempfile.mkstemp(prefix=f".{self._path.name}.", dir=self._path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
            try:
                directory_fd = os.open(self._path.parent, os.O_RDONLY)
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
