"""Job-level aisle processing mode (CODE_SCAN / Vision dispatch policy).

Distinct from ``AisleIdentificationMode`` (strategy family) and
``InventoryProcessingMode`` (production | test).
"""

from __future__ import annotations

from enum import Enum


class AisleProcessingMode(str, Enum):
    """How a process-aisle job dispatches CODE_SCAN vs Vision AI.

    ``AUTO`` — CODE_SCAN first; Vision only when eligible (fail-closed for
    known invalid Dinamic formats).
    ``CODE_SCAN_ONLY`` — barcode/QR only; never call Vision.
    ``VISION_ONLY`` — Vision only; never call CODE_SCAN (diagnostic / test).
    """

    AUTO = "AUTO"
    CODE_SCAN_ONLY = "CODE_SCAN_ONLY"
    VISION_ONLY = "VISION_ONLY"


DEFAULT_AISLE_PROCESSING_MODE = AisleProcessingMode.AUTO

# Seed error when VISION_ONLY skips the scanner (eligible for Vision; not a scan miss).
VISION_ONLY_DIRECT_ERROR_CODE = "VISION_ONLY_DIRECT"


def parse_aisle_processing_mode(
    value: str | AisleProcessingMode | None,
    *,
    default: AisleProcessingMode = DEFAULT_AISLE_PROCESSING_MODE,
) -> AisleProcessingMode:
    """Parse request/snapshot value; empty/None → default (backward compatible)."""
    if isinstance(value, AisleProcessingMode):
        return value
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    try:
        return AisleProcessingMode(raw.upper())
    except ValueError as exc:
        allowed = ", ".join(m.value for m in AisleProcessingMode)
        raise ValueError(
            f"Invalid processing_mode {value!r}; expected one of: {allowed}"
        ) from exc


def processing_mode_from_identification_execution(
    block: dict | None,
) -> AisleProcessingMode:
    """Read snapshotted processing_mode; default AUTO for historical jobs."""
    if not isinstance(block, dict):
        return DEFAULT_AISLE_PROCESSING_MODE
    return parse_aisle_processing_mode(block.get("processing_mode"))
