"""Derive effective processing keys for production inventories (provider/model snapshot + operational fallback)."""

from __future__ import annotations

import logging
from typing import Any

from src.application.services.processing_provider_availability import (
    resolve_production_processing_keys,
)
from src.domain.inventory.entities import Inventory

logger = logging.getLogger(__name__)


def effective_production_processing_keys(
    inventory: Inventory, settings: Any
) -> tuple[str, str, str]:
    """Production keys without explicit request body (see ``resolve_production_processing_keys``)."""
    return resolve_production_processing_keys(
        inventory,
        requested_provider_name=None,
        requested_model_name=None,
        settings=settings,
    )
