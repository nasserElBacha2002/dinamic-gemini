"""Resolve the system operational primary execution config for production inventories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.services.processing_provider_resolution import resolve_start_processing_request


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
        provider_name, model_name, prompt_key = resolve_start_processing_request(
            requested_provider_name=None,
            requested_model_name=None,
            requested_prompt_key=None,
            settings=settings,
        )
        if not model_name:
            raise ValueError("Operational config resolver returned no model_name")
        return OperationalPrimaryExecutionConfig(
            provider_name=provider_name,
            model_name=model_name,
            prompt_key=prompt_key,
            prompt_version=None,
        )
