"""Supplier prompt config domain entity — Phase D2 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SupplierPromptConfig:
    """Editable supplier-scoped prompt instructions configuration (no protected prompt internals)."""

    id: str
    client_supplier_id: str
    provider_name: str | None
    model_name: str | None
    instructions_text: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("SupplierPromptConfig.id is required")
        if not self.client_supplier_id or not self.client_supplier_id.strip():
            raise ValueError("SupplierPromptConfig.client_supplier_id is required")
        normalized_provider = (self.provider_name or "").strip() or None
        normalized_model = (self.model_name or "").strip() or None
        if normalized_provider is None and normalized_model is not None:
            raise ValueError(
                "SupplierPromptConfig.provider_name is required when model_name is provided"
            )
        self.provider_name = normalized_provider
        self.model_name = normalized_model
        if self.instructions_text is None or not self.instructions_text.strip():
            raise ValueError("SupplierPromptConfig.instructions_text is required")
        if self.version is None or self.version < 1:
            raise ValueError("SupplierPromptConfig.version must be >= 1")
        if self.created_at is None:
            raise ValueError("SupplierPromptConfig.created_at is required")
        if self.updated_at is None:
            raise ValueError("SupplierPromptConfig.updated_at is required")
