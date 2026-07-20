"""Central resolver for aisle identification mode inheritance.

Priority (highest first):
  Request → Aisle → Inventory → Client → SYSTEM_DEFAULT (INTERNAL_OCR)

Null overrides mean “inherit from the next level” and must not be treated as a mode.

New job starts reject effective LEGACY_LLM after resolution (see
``reject_legacy_effective_mode_for_new_job``). Historical jobs that stored LEGACY
remain readable; historical retries may re-execute that snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
    parse_identification_mode,
)


@dataclass(frozen=True)
class AisleIdentificationModeResolution:
    effective_mode: AisleIdentificationMode
    source: AisleIdentificationModeSource


def resolve_aisle_identification_mode(
    *,
    request_mode: str | AisleIdentificationMode | None = None,
    aisle_mode: str | AisleIdentificationMode | None = None,
    inventory_mode: str | AisleIdentificationMode | None = None,
    client_mode: str | AisleIdentificationMode | None = None,
) -> AisleIdentificationModeResolution:
    """Resolve effective mode and source. Raises ValueError on invalid non-null values."""
    if request_mode is not None and str(request_mode).strip() != "":
        return AisleIdentificationModeResolution(
            effective_mode=parse_identification_mode(request_mode),
            source=AisleIdentificationModeSource.REQUEST,
        )
    if aisle_mode is not None and str(aisle_mode).strip() != "":
        return AisleIdentificationModeResolution(
            effective_mode=parse_identification_mode(aisle_mode),
            source=AisleIdentificationModeSource.AISLE,
        )
    if inventory_mode is not None and str(inventory_mode).strip() != "":
        return AisleIdentificationModeResolution(
            effective_mode=parse_identification_mode(inventory_mode),
            source=AisleIdentificationModeSource.INVENTORY,
        )
    if client_mode is not None and str(client_mode).strip() != "":
        return AisleIdentificationModeResolution(
            effective_mode=parse_identification_mode(client_mode),
            source=AisleIdentificationModeSource.CLIENT,
        )
    return AisleIdentificationModeResolution(
        effective_mode=AisleIdentificationMode.INTERNAL_OCR,
        source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
    )
