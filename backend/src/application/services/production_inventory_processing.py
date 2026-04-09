"""Derive effective processing keys for production inventories (snapshot with operational fallback)."""

from __future__ import annotations

import logging
from typing import Any, List, Tuple

from src.application.services.operational_execution_config_resolver import OperationalExecutionConfigResolver
from src.domain.inventory.entities import Inventory

logger = logging.getLogger(__name__)


def effective_production_processing_keys(inventory: Inventory, settings: Any) -> Tuple[str, str, str]:
    """Use persisted primary snapshot, filling any missing piece from the operational resolver.

    Logs a **warning** when the inventory snapshot is incomplete and resolver fallback is used
    (includes inventory id and which snapshot fields were missing).
    """
    missing_snapshot: List[str] = []
    p_raw = (inventory.primary_provider_name or "").strip()
    m_raw = (inventory.primary_model_name or "").strip()
    pk_raw = (inventory.primary_prompt_key or "").strip()
    if not p_raw:
        missing_snapshot.append("primary_provider_name")
    if not m_raw:
        missing_snapshot.append("primary_model_name")
    if not pk_raw:
        missing_snapshot.append("primary_prompt_key")

    resolver = OperationalExecutionConfigResolver()
    baseline = resolver.resolve(settings)

    if missing_snapshot:
        logger.warning(
            "production_inventory_snapshot_incomplete_using_operational_fallback "
            "inventory_id=%s missing_snapshot_fields=%s",
            inventory.id,
            ",".join(missing_snapshot),
        )

    provider = (p_raw or baseline.provider_name).strip().lower()
    model = (m_raw or baseline.model_name or "").strip()
    if not model:
        model = (baseline.model_name or "").strip()
    prompt_key = (pk_raw or baseline.prompt_key).strip()
    if not provider or not prompt_key:
        raise ValueError("Production inventory missing effective provider or prompt after resolution")
    return provider, model, prompt_key
