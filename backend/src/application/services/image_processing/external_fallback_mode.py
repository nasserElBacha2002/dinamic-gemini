"""EXTERNAL_FALLBACK_MODE — GLOBAL_BATCH (default) vs deprecated PER_ASSET rollback."""

from __future__ import annotations

EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH = "GLOBAL_BATCH"
EXTERNAL_FALLBACK_MODE_PER_ASSET = "PER_ASSET"

VALID_EXTERNAL_FALLBACK_MODES = frozenset(
    {
        EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
        EXTERNAL_FALLBACK_MODE_PER_ASSET,
    }
)

# Functional identity recorded in snapshots / events for GLOBAL_BATCH runs.
GLOBAL_FALLBACK_EXECUTION_SCOPE = "AISLE_BATCH"
GLOBAL_FALLBACK_SCHEMA_VERSION = "v2.1"
GLOBAL_FALLBACK_ANALYSIS_CONTRACT = "GlobalEntityResponseV21"
GLOBAL_FALLBACK_STRATEGY_KEY = "GLOBAL_EXTERNAL_FALLBACK"
GLOBAL_FALLBACK_PROMPT_KEY = "global_v22"

# Deprecation: PER_ASSET remains only as temporary rollback. Target removal after
# GLOBAL_BATCH is validated in production (see docs/plans for retirement metrics).
PER_ASSET_DEPRECATION_NOTE = (
    "EXTERNAL_FALLBACK_MODE=PER_ASSET is deprecated; use GLOBAL_BATCH. "
    "PER_ASSET is temporary rollback only and will be removed."
)


class ExternalFallbackModeError(ValueError):
    """Unknown or empty EXTERNAL_FALLBACK_MODE (fail closed; no silent fallback)."""


def parse_external_fallback_mode(raw: str | None) -> str:
    """Parse mode from env/settings. Default GLOBAL_BATCH. Unknown → error."""
    text = (raw or "").strip()
    if not text:
        return EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    value = text.upper()
    if value not in VALID_EXTERNAL_FALLBACK_MODES:
        raise ExternalFallbackModeError(
            f"EXTERNAL_FALLBACK_MODE={raw!r} is invalid; allowed: "
            f"{', '.join(sorted(VALID_EXTERNAL_FALLBACK_MODES))}"
        )
    return value


def is_global_batch_mode(mode: str | None) -> bool:
    return parse_external_fallback_mode(mode) == EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH


def is_per_asset_mode(mode: str | None) -> bool:
    return parse_external_fallback_mode(mode) == EXTERNAL_FALLBACK_MODE_PER_ASSET
