"""Map hierarchical identification resolution into API response fields."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.aisle_identification.modes import AisleIdentificationMode
from src.domain.aisle_identification.resolver import resolve_aisle_identification_mode
from src.domain.aisle.entities import Aisle
from src.domain.client.entities import Client
from src.domain.inventory.entities import Inventory


@dataclass(frozen=True)
class IdentificationModeApiFields:
    identification_mode: str | None
    effective_identification_mode: str
    identification_mode_source: str


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
    from src.domain.aisle_identification.modes import parse_identification_mode

    return parse_identification_mode(raw)
