"""Map hierarchical identification resolution into API response fields."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.aisle_identification_configuration_query import (
    IdentificationModeConfiguration,
)
from src.domain.aisle.entities import Aisle
from src.domain.aisle_identification.modes import AisleIdentificationMode, parse_identification_mode
from src.domain.aisle_identification.resolver import resolve_aisle_identification_mode
from src.domain.client.entities import Client
from src.domain.inventory.entities import Inventory


@dataclass(frozen=True)
class IdentificationModeApiFields:
    identification_mode: str | None
    effective_identification_mode: str
    identification_mode_source: str


def api_fields_from_configuration(
    config: IdentificationModeConfiguration,
) -> IdentificationModeApiFields:
    return IdentificationModeApiFields(
        identification_mode=(
            config.configured_mode.value if config.configured_mode is not None else None
        ),
        effective_identification_mode=config.effective_mode.value,
        identification_mode_source=config.source.value,
    )


def client_identification_fields(client: Client) -> IdentificationModeApiFields:
    configured = client.default_identification_mode
    resolution = resolve_aisle_identification_mode(client_mode=configured)
    return IdentificationModeApiFields(
        identification_mode=configured.value if configured else None,
        effective_identification_mode=resolution.effective_mode.value,
        identification_mode_source=resolution.source.value,
    )


def inventory_identification_fields(
    inventory: Inventory,
    *,
    client: Client | None = None,
) -> IdentificationModeApiFields:
    """Prefer :meth:`AisleIdentificationConfigurationQuery.for_inventory` at API boundaries."""
    client_mode = client.default_identification_mode if client is not None else None
    resolution = resolve_aisle_identification_mode(
        inventory_mode=inventory.identification_mode,
        client_mode=client_mode,
    )
    return IdentificationModeApiFields(
        identification_mode=(
            inventory.identification_mode.value if inventory.identification_mode else None
        ),
        effective_identification_mode=resolution.effective_mode.value,
        identification_mode_source=resolution.source.value,
    )


def aisle_identification_fields(
    aisle: Aisle,
    *,
    inventory: Inventory | None = None,
    client: Client | None = None,
) -> IdentificationModeApiFields:
    """Prefer :meth:`AisleIdentificationConfigurationQuery.for_aisle` at API boundaries.

    Callers must supply inventory/client when hierarchy context is required; omitting them
    only yields a correct SYSTEM_DEFAULT when parents truly have no override.
    """
    inv_mode = inventory.identification_mode if inventory is not None else None
    client_mode = client.default_identification_mode if client is not None else None
    resolution = resolve_aisle_identification_mode(
        aisle_mode=aisle.identification_mode,
        inventory_mode=inv_mode,
        client_mode=client_mode,
    )
    return IdentificationModeApiFields(
        identification_mode=(
            aisle.identification_mode.value if aisle.identification_mode else None
        ),
        effective_identification_mode=resolution.effective_mode.value,
        identification_mode_source=resolution.source.value,
    )


def parse_optional_mode_update(
    raw: str | AisleIdentificationMode | None,
) -> AisleIdentificationMode | None:
    """Convert PATCH body value; None clears override."""
    if raw is None:
        return None
    if isinstance(raw, AisleIdentificationMode):
        return raw
    return parse_identification_mode(raw)
