"""Resolve provider / model / prompt for POST .../aisles/{id}/process (production vs test).

Keeps policy out of API routes: production honors validated provider/model selection against
the production catalog; test uses explicit request resolution with full model lists.

Phase 5: after key resolution, validates provider capabilities for visual inventory jobs
(aisle processing always requires vision + image binding).
"""

from __future__ import annotations

import logging
from typing import Any

from src.application.services.processing_provider_availability import (
    resolve_production_processing_keys,
)
from src.application.services.processing_provider_resolution import resolve_start_processing_request
from src.application.services.provider_contract_validation import (
    validate_provider_for_visual_inventory_job,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode

logger = logging.getLogger(__name__)


def _strip_optional(raw: str | None) -> str:
    return (raw or "").strip()


def _log_production_ignored_prompt_override(
    inventory_id: str,
    *,
    requested_prompt_key: str | None,
) -> None:
    if not _strip_optional(requested_prompt_key):
        return
    logger.warning(
        "production_process_ignoring_prompt_override inventory_id=%s ignored_fields=prompt_key",
        inventory_id,
    )


def resolve_process_aisle_execution_keys(
    inventory: Inventory,
    *,
    requested_provider_name: str | None,
    requested_model_name: str | None,
    requested_prompt_key: str | None,
    settings: Any,
) -> tuple[str, str | None, str]:
    """Return ``(pipeline_provider_key, model_name, prompt_key)`` for a new process-aisle job."""
    provider_key: str
    model_name: str | None
    prompt_key: str
    if inventory.processing_mode == InventoryProcessingMode.PRODUCTION:
        _log_production_ignored_prompt_override(
            inventory.id,
            requested_prompt_key=requested_prompt_key,
        )
        provider_key, model_name, prompt_key = resolve_production_processing_keys(
            inventory,
            requested_provider_name=requested_provider_name,
            requested_model_name=requested_model_name,
            settings=settings,
        )
    else:
        provider_key, model_name, prompt_key = resolve_start_processing_request(
            requested_provider_name=requested_provider_name,
            requested_model_name=requested_model_name,
            requested_prompt_key=requested_prompt_key,
            settings=settings,
        )
    validate_provider_for_visual_inventory_job(provider_key)
    return provider_key, model_name, prompt_key
