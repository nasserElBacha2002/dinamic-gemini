from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class GlobalPromptConfig:
    """Editable global prompt instructions (management-only, no protected internals)."""

    id: str
    scope_type: str
    provider_name: str | None
    model_name: str | None
    instructions_text: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("GlobalPromptConfig.id is required")
        if (self.scope_type or "").strip().lower() != "global":
            raise ValueError("GlobalPromptConfig.scope_type must be 'global'")
        if self.instructions_text is None or not self.instructions_text.strip():
            raise ValueError("GlobalPromptConfig.instructions_text is required")
        if self.version is None or self.version < 1:
            raise ValueError("GlobalPromptConfig.version must be >= 1")
        if self.created_at is None:
            raise ValueError("GlobalPromptConfig.created_at is required")
        if self.updated_at is None:
            raise ValueError("GlobalPromptConfig.updated_at is required")
