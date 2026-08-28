"""Derive allowed positioning UX actions from authoritative backend state."""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.observability_access import (
    CAP_POSITION_OVERRIDE_CREATE,
    CAP_POSITION_OVERRIDE_RESTORE,
    CAP_POSITION_OVERRIDE_VIEW,
    CAP_POSITION_PROCESSING_RECOVER,
    CAP_POSITION_PROCESSING_REPROCESS,
    CAP_POSITION_PROCESSING_START,
    CAP_POSITION_RESULTS_VIEW,
    capabilities_for_role,
)
from src.domain.positioning_operational.entities import PositioningAllowedActions

_ACTIVE_PROCESSING = frozenset(
    {
        "PREPARING",
        "UPLOADING",
        "STARTING",
        "RUNNING",
        "FINALIZING",
        "SUSPECTED_STALE",
        "RECOVERY_REQUIRED",
    }
)

_TERMINAL_OK = frozenset({"COMPLETED", "COMPLETED_WITH_WARNINGS", "IDLE"})


def _caps(principal: AccessPrincipal) -> frozenset[str]:
    if principal.is_platform:
        return frozenset(
            {
                CAP_POSITION_RESULTS_VIEW,
                CAP_POSITION_PROCESSING_START,
                CAP_POSITION_PROCESSING_REPROCESS,
                CAP_POSITION_PROCESSING_RECOVER,
                CAP_POSITION_OVERRIDE_VIEW,
                CAP_POSITION_OVERRIDE_CREATE,
                CAP_POSITION_OVERRIDE_RESTORE,
            }
        )
    out: set[str] = set()
    for role in principal.roles:
        out.update(capabilities_for_role(role))
    return frozenset(out)


def resolve_positioning_allowed_actions(
    *,
    principal: AccessPrincipal,
    processing_state: str,
    can_start_new: bool,
    recoverable: bool,
    has_result_job: bool,
    operational_ux_enabled: bool,
    reprocessing_enabled: bool,
    recovery_enabled: bool,
    overrides_enabled: bool,
    reconciliation_status: str | None,
    block_processing_start: bool = False,
) -> PositioningAllowedActions:
    """Single authority for process/reprocess/recover/correct buttons."""
    if not operational_ux_enabled:
        return PositioningAllowedActions()

    caps = _caps(principal)
    state = (processing_state or "").strip().upper()
    busy = state in _ACTIVE_PROCESSING
    can_view = CAP_POSITION_RESULTS_VIEW in caps or CAP_POSITION_OVERRIDE_VIEW in caps
    terminal_stable = can_start_new and not recoverable and not busy

    process = (
        CAP_POSITION_PROCESSING_START in caps
        and can_start_new
        and not busy
        and not recoverable
        and not block_processing_start
    )
    recover = (
        recovery_enabled
        and recoverable
        and CAP_POSITION_PROCESSING_RECOVER in caps
    )
    reprocess = (
        reprocessing_enabled
        and CAP_POSITION_PROCESSING_REPROCESS in caps
        and has_result_job
        and terminal_stable
    )
    # Reconcile-only never while recovery is required or processing is active.
    reconcile_only = (
        reprocessing_enabled
        and CAP_POSITION_PROCESSING_REPROCESS in caps
        and has_result_job
        and terminal_stable
        and (reconciliation_status or "").upper() in {"STALE", "FAILED", "COMPLETED"}
    )
    correct = (
        overrides_enabled
        and CAP_POSITION_OVERRIDE_CREATE in caps
        and has_result_job
        and not busy
        and not recoverable
    )
    restore = (
        overrides_enabled
        and CAP_POSITION_OVERRIDE_RESTORE in caps
        and has_result_job
        and not busy
        and not recoverable
    )
    review = can_view and has_result_job

    return PositioningAllowedActions(
        process=process,
        reprocess=reprocess,
        recover=recover,
        review=review,
        correct_position=correct,
        restore_automatic=restore,
        reconcile_only=reconcile_only,
    )


def filter_warning_actions(
    warning_actions: tuple[str, ...],
    allowed: PositioningAllowedActions,
) -> tuple[str, ...]:
    """Intersect semantic warning actions with concrete allowed_actions."""
    mapping = allowed.as_dict()
    return tuple(a for a in warning_actions if mapping.get(a, False))
