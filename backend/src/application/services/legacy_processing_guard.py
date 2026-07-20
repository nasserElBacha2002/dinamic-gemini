"""Phase 8 — guard against new LEGACY_LLM configurations and process overrides."""

from __future__ import annotations

import logging
from typing import Any

from src.application.errors import LegacyProcessingModeNotAllowedError
from src.domain.aisle_identification.modes import AisleIdentificationMode

logger = logging.getLogger(__name__)

LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION = (
    "LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION"
)

# Temporary retirement metrics (in-process; not persisted).
legacy_mode_jobs_blocked_total = 0
legacy_mode_config_writes_blocked_total = 0
legacy_mode_jobs_created_total = 0  # reserved for residual paths during soak
legacy_frontend_action_used_total = 0


def is_legacy_identification_mode(mode: Any) -> bool:
    if mode is None:
        return False
    if isinstance(mode, AisleIdentificationMode):
        return mode is AisleIdentificationMode.LEGACY_LLM
    raw = str(mode).strip().upper()
    return raw in {
        AisleIdentificationMode.LEGACY_LLM.value,
        "LEGACY_LLM_TEMPORARY",
    }


def reject_legacy_mode_for_new_configuration(
    mode: AisleIdentificationMode | str | None,
    *,
    context: str = "configuration",
) -> None:
    """Block writing LEGACY_LLM onto client/inventory/aisle config or process override.

    Clearing the override (``None``) remains allowed so tenants can inherit
    a non-legacy ancestor or system default after migration.
    """
    global legacy_mode_config_writes_blocked_total
    if mode is None:
        return
    if not is_legacy_identification_mode(mode):
        return
    legacy_mode_config_writes_blocked_total += 1
    raw = mode.value if isinstance(mode, AisleIdentificationMode) else str(mode)
    logger.warning(
        "legacy_processing.blocked context=%s mode=%s blocked_total=%s",
        context,
        raw,
        legacy_mode_config_writes_blocked_total,
    )
    raise LegacyProcessingModeNotAllowedError(raw, context=context)


def reject_legacy_mode_for_new_job(
    mode: AisleIdentificationMode | str | None,
) -> None:
    global legacy_mode_jobs_blocked_total
    if mode is None or not is_legacy_identification_mode(mode):
        return
    legacy_mode_jobs_blocked_total += 1
    raw = mode.value if isinstance(mode, AisleIdentificationMode) else str(mode)
    logger.warning(
        "legacy_processing.job_override_blocked mode=%s blocked_total=%s",
        raw,
        legacy_mode_jobs_blocked_total,
    )
    raise LegacyProcessingModeNotAllowedError(raw, context="job_start")


def legacy_usage_metrics_snapshot() -> dict[str, int]:
    return {
        "legacy_mode_jobs_blocked_total": int(legacy_mode_jobs_blocked_total),
        "legacy_mode_config_writes_blocked_total": int(
            legacy_mode_config_writes_blocked_total
        ),
        "legacy_mode_jobs_created_total": int(legacy_mode_jobs_created_total),
        "legacy_frontend_action_used_total": int(legacy_frontend_action_used_total),
    }


__all__ = [
    "LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION",
    "LegacyProcessingModeNotAllowedError",
    "is_legacy_identification_mode",
    "legacy_usage_metrics_snapshot",
    "reject_legacy_mode_for_new_configuration",
    "reject_legacy_mode_for_new_job",
]
