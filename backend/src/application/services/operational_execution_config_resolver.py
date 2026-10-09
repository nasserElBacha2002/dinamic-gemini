"""Resolve the system operational primary execution config for production inventories.

``prompt_key`` on the snapshot is always the **effective aisle protected profile**
(``global_v22``). It does **not** follow ``HYBRID_PROMPT`` env — that setting is for
test-mode defaults, catalog labels, and traceability hints only.

``prompt_version`` on the snapshot remains ``None`` at inventory creation (historical behavior);
``PROMPT_VERSION`` env affects composition traceability elsewhere, not this persisted field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.services.processing_provider_resolution import resolve_start_processing_request
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE


@dataclass(frozen=True)
class OperationalPrimaryExecutionConfig:
    """Snapshot fields persisted on a production inventory at creation time."""

    provider_name: str
    model_name: str
    prompt_key: str
    prompt_version: str | None


class OperationalExecutionConfigResolver:
    """Returns the default approved provider / model / prompt for operational (production) runs."""

    def resolve(self, settings: Any) -> OperationalPrimaryExecutionConfig:
        provider_name, model_name, _catalog_default_prompt_key = resolve_start_processing_request(
            requested_provider_name=None,
            requested_model_name=None,
            requested_prompt_key=None,
            settings=settings,
        )
        if not model_name:
            raise ValueError("Operational config resolver returned no model_name")
        del _catalog_default_prompt_key  # HYBRID_PROMPT — not used for production aisle body
        return OperationalPrimaryExecutionConfig(
            provider_name=provider_name,
            model_name=model_name,
            prompt_key=DEFAULT_HYBRID_PROMPT_PROFILE,
            prompt_version=None,
        )
