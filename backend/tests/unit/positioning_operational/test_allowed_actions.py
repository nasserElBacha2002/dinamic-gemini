"""Unit tests for Phase 7 positioning operational allowed actions + warnings."""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.positioning_operational.allowed_actions import (
    resolve_positioning_allowed_actions,
)
from src.application.services.positioning_operational.warnings_builder import (
    build_operational_warnings,
)


def _principal(*roles: str, is_platform: bool = False) -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="u1",
        roles=frozenset(roles) if roles else frozenset({"operator"}),
        client_id=None if is_platform else "c1",
        is_platform=is_platform,
    )


def test_recovery_blocks_process_and_allows_recover() -> None:
    actions = resolve_positioning_allowed_actions(
        principal=_principal("operator"),
        processing_state="RECOVERY_REQUIRED",
        can_start_new=False,
        recoverable=True,
        has_result_job=True,
        operational_ux_enabled=True,
        reprocessing_enabled=True,
        recovery_enabled=True,
        overrides_enabled=True,
        reconciliation_status="COMPLETED",
    )
    assert actions.recover is True
    assert actions.process is False
    assert actions.reprocess is False


def test_completed_allows_reprocess_for_operator() -> None:
    actions = resolve_positioning_allowed_actions(
        principal=_principal("operator"),
        processing_state="COMPLETED",
        can_start_new=True,
        recoverable=False,
        has_result_job=True,
        operational_ux_enabled=True,
        reprocessing_enabled=True,
        recovery_enabled=True,
        overrides_enabled=False,
        reconciliation_status="COMPLETED",
    )
    assert actions.reprocess is True
    assert actions.correct_position is False


def test_feature_flag_disables_all_actions() -> None:
    actions = resolve_positioning_allowed_actions(
        principal=_principal("platform_admin", is_platform=True),
        processing_state="IDLE",
        can_start_new=True,
        recoverable=False,
        has_result_job=False,
        operational_ux_enabled=False,
        reprocessing_enabled=True,
        recovery_enabled=True,
        overrides_enabled=True,
        reconciliation_status=None,
    )
    assert actions.as_dict() == {
        "process": False,
        "reprocess": False,
        "recover": False,
        "review": False,
        "correct_position": False,
        "restore_automatic": False,
        "reconcile_only": False,
    }


def test_warnings_include_recovery_and_no_resolved_detections() -> None:
    warnings = build_operational_warnings(
        processing_state="RECOVERY_REQUIRED",
        recoverable=True,
        reconciliation_status="STALE",
        unassigned_count=3,
        ambiguous_count=1,
        resolved_detections_count=0,
        unordered_count=1,
        invalid_count=0,
        stale_count=3,
    )
    codes = {w.code for w in warnings}
    assert "PROCESSING_RECOVERY_REQUIRED" in codes
    assert "RECONCILIATION_STALE" in codes
    assert "NO_POSITION_LABEL_DETECTIONS" in codes


def test_warnings_skip_no_detections_when_resolved_present() -> None:
    warnings = build_operational_warnings(
        processing_state="COMPLETED",
        recoverable=False,
        reconciliation_status="COMPLETED",
        unassigned_count=2,
        ambiguous_count=0,
        resolved_detections_count=1,
        unordered_count=0,
        invalid_count=0,
        stale_count=0,
    )
    codes = {w.code for w in warnings}
    assert "NO_POSITION_LABEL_DETECTIONS" not in codes
