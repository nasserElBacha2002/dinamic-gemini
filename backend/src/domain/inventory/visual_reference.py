"""
Inventory visual reference — v3.2.4 (Documento técnico §9.1).

Represents an image of reference associated with an inventory, for optional use
as visual context during aisle analysis. Provider-agnostic; no provider-specific metadata.
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
