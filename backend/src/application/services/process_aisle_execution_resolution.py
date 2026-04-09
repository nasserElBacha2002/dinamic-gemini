"""Resolve provider / model / prompt for POST .../aisles/{id}/process (production vs test).

Keeps policy out of API routes: production uses inventory operational snapshot (with resolver
fallback); test uses explicit request resolution.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from src.application.services.processing_provider_resolution import resolve_start_processing_request
from src.application.services.production_inventory_processing import effective_production_processing_keys
from src.domain.inventory.entities import Inventory, InventoryProcessingMode

logger = logging.getLogger(__name__)


def _strip_optional(raw: Optional[str]) -> str:
    return (raw or "").strip()


def _log_production_ignored_request_overrides(
    inventory_id: str,
    *,
    requested_provider_name: Optional[str],
    requested_model_name: Optional[str],
    requested_prompt_key: Optional[str],
) -> None:
    ignored: list[str] = []
    if _strip_optional(requested_provider_name):
        ignored.append("provider_name")
    if _strip_optional(requested_model_name):
        ignored.append("model_name")
    if _strip_optional(requested_prompt_key):
        ignored.append("prompt_key")
    if not ignored:
        return
    logger.warning(
        "production_process_ignoring_request_overrides inventory_id=%s ignored_fields=%s",
        inventory_id,
        ",".join(ignored),
    )


def resolve_process_aisle_execution_keys(
    inventory: Inventory,
    *,
    requested_provider_name: Optional[str],
    requested_model_name: Optional[str],
    requested_prompt_key: Optional[str],
    settings: Any,
) -> Tuple[str, Optional[str], str]:
    """Return ``(pipeline_provider_key, model_name, prompt_key)`` for a new process-aisle job."""
    if inventory.processing_mode == InventoryProcessingMode.PRODUCTION:
        _log_production_ignored_request_overrides(
            inventory.id,
            requested_provider_name=requested_provider_name,
            requested_model_name=requested_model_name,
            requested_prompt_key=requested_prompt_key,
        )
        return effective_production_processing_keys(inventory, settings)
    return resolve_start_processing_request(
        requested_provider_name=requested_provider_name,
        requested_model_name=requested_model_name,
        requested_prompt_key=requested_prompt_key,
        settings=settings,
    )
