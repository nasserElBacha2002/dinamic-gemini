"""API tests for preliminary reconciliation routes (Phase 5 corrections)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_list_preliminary_reconciliations_use_case,
    get_reconcile_preliminary_detections_use_case,
)
from src.api.server import app
from src.application.use_cases.aisles.list_preliminary_reconciliations import (
    ListPreliminaryReconciliationsResult,
    ReconciliationMetricsSummary,
)
from src.application.use_cases.aisles.reconcile_preliminary_detections import (
    EnqueueReconciliationResult,
    ReconciliationDisabledError,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


class _EnqueueOk:
    def execute(self, command):
        return EnqueueReconciliationResult(
            accepted=True,
            enqueued=1,
            already_terminal=0,
            reconciliation_ids=["r1"],
            batch_id="batch-1",
        )


class _EnqueueDisabled:
    def execute(self, command):
        raise ReconciliationDisabledError()


class _ListOk:
    def execute(self, command):
        return ListPreliminaryReconciliationsResult(
            items=[],
            total=0,
            metrics=ReconciliationMetricsSummary(
                total_eligible_drafts=0,
                total_reconciled=0,
                total_pending=0,
                total_not_comparable=0,
                mapping_comparable=0,
                code_comparable=0,
                quantity_comparable=0,
                code_match_count=0,
                code_mismatch_count=0,
                quantity_match_count=0,
                quantity_mismatch_count=0,
                local_only_count=0,
                remote_only_count=0,
                ambiguous_count=0,
                both_unresolved_count=0,
                comparability_rate=None,
                server_code_agreement_rate=None,
                quantity_agreement_rate=None,
                local_only_rate=None,
                remote_only_rate=None,
                ambiguity_rate=None,
                numerator_agreement=0,
                denominator_comparable=0,
            ),
        )


def test_reconcile_route_accepted_202() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_reconcile_preliminary_detections_use_case] = lambda: _EnqueueOk()
    try:
        client = TestClient(app)
        res = client.post(
            "/api/v3/inventories/inv-1/aisles/aisle-1/reconcile-preliminary-detections",
            json={"job_id": "job-1", "enqueue_limit": 50},
        )
        assert res.status_code == 202
        body = res.json()
        assert body["accepted"] is True
        assert body["reconciliation_ids"] == ["r1"]
        assert body["batch_id"] == "batch-1"
    finally:
        app.dependency_overrides.clear()


def test_reconcile_route_disabled() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_reconcile_preliminary_detections_use_case] = (
        lambda: _EnqueueDisabled()
    )
    try:
        client = TestClient(app)
        res = client.post(
            "/api/v3/inventories/inv-1/aisles/aisle-1/reconcile-preliminary-detections",
            json={"job_id": "job-1"},
        )
        assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_list_reconciliations_supports_job_filter() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_list_preliminary_reconciliations_use_case] = lambda: _ListOk()
    try:
        client = TestClient(app)
        res = client.get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/preliminary-reconciliations"
            "?job_id=job-1&preliminary_detection_id=p1"
        )
        assert res.status_code == 200
        data = res.json()
        assert "authority_notice" in data
        assert "total_eligible_drafts" in data["metrics"]
    finally:
        app.dependency_overrides.clear()
