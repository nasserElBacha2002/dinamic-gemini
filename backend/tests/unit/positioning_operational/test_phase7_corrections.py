"""Unit tests for Phase 7 positioning operational corrections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import IdempotencyKeyReusedError
from src.application.services.positioning_operational.allowed_actions import (
    resolve_positioning_allowed_actions,
)
from src.application.services.positioning_operational.warnings_builder import (
    build_operational_warnings,
)
from src.application.use_cases.positioning_operational.get_aisle_operational_view import (
    _recon_version_as_str,
)
from src.application.use_cases.positioning_operational.reprocess_aisle_positioning import (
    PositioningReprocessError,
    ReprocessAislePositioningCommand,
    ReprocessAislePositioningUseCase,
)
from src.domain.positioning_operational.entities import ManualOverridePolicy


def _principal(*roles: str, is_platform: bool = False) -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="u1",
        roles=frozenset(roles) if roles else frozenset({"operator"}),
        client_id=None if is_platform else "c1",
        is_platform=is_platform,
    )


@dataclass
class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_recon_version_as_str_accepts_semantic_and_legacy() -> None:
    assert _recon_version_as_str("1.0.0") == "1.0.0"
    assert _recon_version_as_str("global-v2") == "global-v2"
    assert _recon_version_as_str(None) is None
    assert _recon_version_as_str(3) == "3"
    assert _recon_version_as_str("  ") is None


def test_recovery_blocks_reconcile_only() -> None:
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
    assert actions.reconcile_only is False
    assert actions.reprocess is False


def test_warnings_filter_actions_by_allowed() -> None:
    warnings = build_operational_warnings(
        processing_state="RECOVERY_REQUIRED",
        recoverable=True,
        reconciliation_status="STALE",
        unassigned_count=1,
        ambiguous_count=0,
        detections_count=0,
        unordered_count=0,
        invalid_count=0,
        stale_count=1,
        allowed_action_names=frozenset({"recover"}),
    )
    for w in warnings:
        for action in w.allowed_actions:
            assert action == "recover"


def _status_with_jobs(*, active: Any = None, operational_id: str | None = None, latest: Any = None):
    aisle = MagicMock()
    aisle.operational_job_id = operational_id
    status = MagicMock()
    status.aisle = aisle
    status.latest_job = latest
    status.recent_jobs = [j for j in (active, latest) if j is not None]
    return status


def test_reprocess_cas_detects_active_job_disappeared() -> None:
    status_uc = MagicMock()
    latest = MagicMock()
    latest.id = "job-terminal"
    latest.status = MagicMock()
    status_uc.execute.return_value = _status_with_jobs(
        active=None, operational_id="job-terminal", latest=latest
    )

    # resolve_aisle_processing_state will be called with real logic — use IDLE-like mocks
    # by stubbing the whole resolve via patching processing state on a terminal job.
    from src.domain.jobs.entities import JobStatus

    latest.status = JobStatus.SUCCEEDED
    latest.failure_code = None
    latest.finalization_error_code = None
    latest.claim_owner_id = None
    latest.lease_expires_at = None
    latest.last_heartbeat_at = None
    latest.updated_at = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    latest.payload_json = {}

    access = MagicMock()
    idem = MagicMock()
    uc = ReprocessAislePositioningUseCase(
        status_use_case=status_uc,
        start_processing=MagicMock(),
        reconcile=MagicMock(),
        clock=_FakeClock(),
        access_policy=access,
        idempotency=idem,
        reprocessing_enabled=True,
    )

    with pytest.raises(PositioningReprocessError) as exc:
        uc.execute(
            ReprocessAislePositioningCommand(
                inventory_id="inv",
                aisle_id="aisle",
                principal=_principal("operator"),
                idempotency_key="idem-key-12345",
                reprocess_mode="RECONCILE_ONLY",
                expected_active_job_id="job-was-active",
                expected_result_job_id="job-terminal",
            )
        )
    assert exc.value.code == "ACTIVE_JOB_MISMATCH"
    access.require_inventory.assert_called_once()


def test_reprocess_cas_detects_result_job_change() -> None:
    from src.domain.jobs.entities import JobStatus

    status_uc = MagicMock()
    latest = MagicMock()
    latest.id = "job-b"
    latest.status = JobStatus.SUCCEEDED
    latest.failure_code = None
    latest.finalization_error_code = None
    latest.claim_owner_id = None
    latest.lease_expires_at = None
    latest.last_heartbeat_at = None
    latest.updated_at = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    latest.payload_json = {}
    status_uc.execute.return_value = _status_with_jobs(
        operational_id="job-b", latest=latest
    )

    uc = ReprocessAislePositioningUseCase(
        status_use_case=status_uc,
        start_processing=MagicMock(),
        reconcile=MagicMock(),
        clock=_FakeClock(),
        access_policy=MagicMock(),
        idempotency=MagicMock(),
        reprocessing_enabled=True,
    )
    with pytest.raises(PositioningReprocessError) as exc:
        uc.execute(
            ReprocessAislePositioningCommand(
                inventory_id="inv",
                aisle_id="aisle",
                principal=_principal("operator"),
                idempotency_key="idem-key-12345",
                reprocess_mode="RECONCILE_ONLY",
                expected_active_job_id=None,
                expected_result_job_id="job-a",
            )
        )
    assert exc.value.code == "RESULT_JOB_MISMATCH"


def test_reprocess_idempotency_conflict_on_payload_mismatch() -> None:
    from src.domain.jobs.entities import JobStatus

    status_uc = MagicMock()
    latest = MagicMock()
    latest.id = "job-a"
    latest.status = JobStatus.SUCCEEDED
    latest.failure_code = None
    latest.finalization_error_code = None
    latest.claim_owner_id = None
    latest.lease_expires_at = None
    latest.last_heartbeat_at = None
    latest.updated_at = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    latest.payload_json = {}
    status_uc.execute.return_value = _status_with_jobs(
        operational_id="job-a", latest=latest
    )

    idem = MagicMock()
    idem.begin.side_effect = IdempotencyKeyReusedError("conflict")

    uc = ReprocessAislePositioningUseCase(
        status_use_case=status_uc,
        start_processing=MagicMock(),
        reconcile=MagicMock(),
        clock=_FakeClock(),
        access_policy=MagicMock(),
        idempotency=idem,
        reprocessing_enabled=True,
    )
    with pytest.raises(PositioningReprocessError) as exc:
        uc.execute(
            ReprocessAislePositioningCommand(
                inventory_id="inv",
                aisle_id="aisle",
                principal=_principal("operator"),
                idempotency_key="idem-key-12345",
                reprocess_mode="RECONCILE_ONLY",
                expected_active_job_id=None,
                expected_result_job_id="job-a",
            )
        )
    assert exc.value.code == "POSITION_REPROCESS_IDEMPOTENCY_CONFLICT"


def test_full_reprocess_policy_requires_review() -> None:
    from src.application.services.image_processing.processing_action_idempotency_service import (
        IdempotencyBeginResult,
    )
    from src.domain.jobs.entities import JobStatus

    status_uc = MagicMock()
    latest = MagicMock()
    latest.id = "job-a"
    latest.status = JobStatus.SUCCEEDED
    latest.failure_code = None
    latest.finalization_error_code = None
    latest.claim_owner_id = None
    latest.lease_expires_at = None
    latest.last_heartbeat_at = None
    latest.updated_at = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    latest.payload_json = {}
    status_uc.execute.return_value = _status_with_jobs(
        operational_id="job-a", latest=latest
    )

    start = MagicMock()
    start.execute.return_value = MagicMock(job_id="job-b")
    idem = MagicMock()
    record = MagicMock()
    idem.begin.return_value = IdempotencyBeginResult(replay=False, record=record)
    override_repo = MagicMock()
    override_repo.list_active_for_results.return_value = [MagicMock(), MagicMock()]
    recon_repo = MagicMock()
    recon_repo.list_active_assignments.return_value = [
        MagicMock(result_id="r1"),
        MagicMock(result_id="r2"),
    ]

    uc = ReprocessAislePositioningUseCase(
        status_use_case=status_uc,
        start_processing=start,
        reconcile=MagicMock(),
        clock=_FakeClock(),
        access_policy=MagicMock(),
        idempotency=idem,
        override_repo=override_repo,
        reconciliation_repo=recon_repo,
        reprocessing_enabled=True,
    )
    result = uc.execute(
        ReprocessAislePositioningCommand(
            inventory_id="inv",
            aisle_id="aisle",
            principal=_principal("operator"),
            idempotency_key="idem-key-12345",
            reprocess_mode="REPROCESS_FULL_AISLE",
            expected_active_job_id=None,
            expected_result_job_id="job-a",
            identification_mode=None,
        )
    )
    assert result.manuals_preserved is False
    assert (
        result.manual_override_policy
        == ManualOverridePolicy.REQUIRES_REVIEW_AFTER_NEW_JOB.value
    )
    assert result.previous_manual_overrides_count == 2
    start.execute.assert_called_once()
    assert start.execute.call_args.args[0].requested_identification_mode is None
