"""
Inventory visual reference — v3.2.4 (Documento técnico §9.1).

Represents an image of reference associated with an inventory, for optional use
as visual context during aisle analysis. ``storage_path`` / ``mime_type`` are legacy-first
fields; provider-aware access uses ``storage_provider``, ``storage_bucket``, ``storage_key``,
and ``content_type`` (object metadata) per ``artifact_store`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class InventoryVisualReference:
    """A single visual reference image owned by an inventory."""

    id: str
    inventory_id: str
    filename: str
    storage_path: str
    mime_type: str
    file_size: int
    created_at: datetime
    # Phase 1 S3 foundation (optional during rollout; legacy records may be path-only).
    storage_provider: str | None = None
    storage_bucket: str | None = None
    storage_key: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    etag: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("InventoryVisualReference.id is required")
        if not self.inventory_id or not self.inventory_id.strip():
            raise ValueError("InventoryVisualReference.inventory_id is required")
        if not self.filename or not self.filename.strip():
            raise ValueError("InventoryVisualReference.filename is required")
        if not self.storage_path or not self.storage_path.strip():
            raise ValueError("InventoryVisualReference.storage_path is required")
        if not self.mime_type or not self.mime_type.strip():
            raise ValueError("InventoryVisualReference.mime_type is required")
        if self.file_size is None or self.file_size < 0:
            raise ValueError("InventoryVisualReference.file_size must be >= 0")
        if self.created_at is None:
            raise ValueError("InventoryVisualReference.created_at is required")
