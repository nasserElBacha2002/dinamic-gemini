"""Admin finalization recovery API auth — Phase 3.4 corrections."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.jobs.finalization_evidence import FinalizationAssessmentOutcome
from src.domain.jobs.finalization_recovery import RecoveryOutcome, RecoveryResult
from src.runtime.v3_deps import get_finalization_recovery_coordinator


class _StubCoordinator:
    last_requested_by: str | None = None

    def execute(self, operation, command):
        _StubCoordinator.last_requested_by = command.requested_by

        class _Assessment:
            outcome = FinalizationAssessmentOutcome.COMPLETE
            blocking_reason = None
            technical_result_status = "succeeded"
            finalization_status = "completed"
            last_confirmed_stage = None
            next_required_stage = None
            recovery_candidate = False
            stages = {}

        assessment = _Assessment()
        return RecoveryResult(
            job_id=command.job_id,
            operation=operation,
            outcome=RecoveryOutcome.VERIFICATION_REQUIRED,
            previous_assessment=assessment,
            new_assessment=assessment,
            dry_run=command.dry_run,
        )


def test_admin_finalization_recover_requires_auth() -> None:
    client = TestClient(app)
    app.dependency_overrides.pop(get_current_admin, None)
    app.dependency_overrides[get_finalization_recovery_coordinator] = lambda: _StubCoordinator()
    try:
        r = client.post(
            "/api/v3/admin/jobs/job-1/finalization/recover",
            json={"operation": "verify", "dry_run": True},
        )
        assert r.status_code == 401
    finally:
        app.dependency_overrides.pop(get_finalization_recovery_coordinator, None)
        app.dependency_overrides[get_current_admin] = lambda: AuthUser(
            id="admin", username="admin", role="administrator"
        )


def test_admin_finalization_recover_allowed_for_admin_and_audits_username() -> None:
    client = TestClient(app)
    app.dependency_overrides[get_finalization_recovery_coordinator] = lambda: _StubCoordinator()
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="audit-admin", role="administrator"
    )
    try:
        r = client.post(
            "/api/v3/admin/jobs/job-1/finalization/recover",
            json={"operation": "verify", "dry_run": True},
        )
        assert r.status_code == 200
        assert r.json()["dry_run"] is True
        assert _StubCoordinator.last_requested_by == "audit-admin"
    finally:
        app.dependency_overrides.pop(get_finalization_recovery_coordinator, None)
        app.dependency_overrides.pop(get_current_admin, None)
