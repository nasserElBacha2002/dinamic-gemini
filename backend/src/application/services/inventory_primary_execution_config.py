"""Rules for when an inventory exposes its primary execution config to clients."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.inventory.entities import Inventory, InventoryProcessingMode


@dataclass(frozen=True)
class PrimaryExecutionConfigFields:
    """Neutral DTO before mapping to API ``PrimaryExecutionConfigResponse``."""

    provider_name: str
    model_name: str
    prompt_key: str
    prompt_version: str | None


def primary_execution_config_for_inventory(inv: Inventory) -> PrimaryExecutionConfigFields | None:
    """Expose primary config only when the snapshot is complete (no empty-string placeholders)."""
    if inv.processing_mode != InventoryProcessingMode.PRODUCTION:
        return None
    pn = (inv.primary_provider_name or "").strip()
    pm = (inv.primary_model_name or "").strip()
    pk = (inv.primary_prompt_key or "").strip()
    if not pn or not pm or not pk:
        return None
    return PrimaryExecutionConfigFields(
        provider_name=pn,
        model_name=pm,
        prompt_key=pk,
        prompt_version=inv.primary_prompt_version,
    )
