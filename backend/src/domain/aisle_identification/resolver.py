"""Central resolver for aisle identification mode inheritance.

Priority (highest first):
  Request → Aisle → Inventory → Client → SYSTEM_DEFAULT (CODE_SCAN)

Null overrides mean “inherit from the next level” and must not be treated as a mode.

Position-label detection runs inside CODE_SCAN execution. Vision (EXTERNAL_PROVIDER)
is the post-scan recognition path when snapshotted fallback is enabled.

New job starts reject effective LEGACY_LLM and INTERNAL_OCR after resolution.
Historical jobs that stored those modes remain readable / retryable via snapshot.
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
        effective_mode=AisleIdentificationMode.CODE_SCAN,
        source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
    )
