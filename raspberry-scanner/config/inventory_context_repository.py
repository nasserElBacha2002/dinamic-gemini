"""Durable last-known-good storage for inventory aisle bindings (mobile bundle subset)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from durable_io import fsync_directory
from inventory_context import InventoryContextError, InventoryOperationalConfig


class InventoryContextRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> InventoryOperationalConfig | None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_UNREADABLE",
                f"cannot read inventory context file: {exc}",
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_UNREADABLE",
                f"invalid inventory context JSON: {exc}",
            ) from exc
        return InventoryOperationalConfig.from_dict(data)

    def save(self, config: InventoryOperationalConfig) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "inventory_id": config.inventory_id,
                "aisles": [
                    {"aisle_id": aisle_id, "aisle_code": aisle_code}
                    for aisle_code, aisle_id in config.aisles
                ],
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        fd, temp_name = tempfile.mkstemp(prefix=f".{self._path.name}.", dir=self._path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
            fsync_directory(self._path.parent)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
