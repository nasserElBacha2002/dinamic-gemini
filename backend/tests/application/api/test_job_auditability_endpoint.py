"""HTTP-level tests for GET …/jobs/{job_id}/auditability (Phase H2 / H2.1).

**Location:** ``tests/application/api/`` (not ``tests/api/``). The ``tests/api/conftest.py`` module
imports ``src.api.server:app`` at import time, which fails on Python 3.9 (e.g. ``Settings | None`` in
auth settings) *before* this module's ``pytest.skip`` runs. Keeping this file here allows targeted
``pytest tests/application/api/test_job_auditability_endpoint.py`` on 3.9 (whole module skipped) and
full execution on 3.10+ without loading ``tests/api/conftest`` first.

Skip entire module on Python < 3.10: importing the FastAPI app pulls domain modules that use
``dataclass(kw_only=True)`` (not supported on 3.9).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if sys.version_info < (3, 10):
    pytest.skip("HTTP auditability tests require Python 3.10+.", allow_module_level=True)

from src.api.constants.error_wire import HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C
from src.api.dependencies import (
    get_aisle_repo,
    get_artifact_storage,
    get_inventory_repo,
    get_job_repo,
    get_resolve_aisle_job_for_inventory_read_use_case,
    get_run_auditability_service,
)
from src.api.server import app
from src.application.services.reference_usage_from_job_result import (
    VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY,
)
from src.application.services.run_auditability_execution_log import (
    ANALYSIS_REQUEST_EVENT_TYPE,
    ANALYSIS_REQUEST_PREPARED,
    ANALYSIS_STAGE,
)
from src.application.services.run_auditability_service import RunAuditabilityService
from src.application.use_cases.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.artifacts.stored_artifact_reader import DefaultStoredArtifactReader
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

client = TestClient(app)
_NOW = datetime(2026, 5, 11, tzinfo=timezone.utc)


def _admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def _analysis_event() -> dict[str, Any]:
    return {
        "ts": "2026-05-11T00:00:00+00:00",
        "stage": ANALYSIS_STAGE,
        "level": "info",
        "message": ANALYSIS_REQUEST_PREPARED,
        "payload": {
            "event_type": ANALYSIS_REQUEST_EVENT_TYPE,
            "prompt_composition": {
                "effective_prompt": {
                    "effective_prompt_hash": "hashh",
                    "supplier_prompt_config_id": "spc",
                    "supplier_prompt_config_version": "1",
                    "fallback_used": False,
                    "warnings": [],
                },
            },
        },
    }


class _FakeExecLogLoader:
    def try_load_events_for_job(self, job: Job) -> list[dict[str, Any]] | None:
        return [_analysis_event()]


class _NoExecLogLoader:
    def try_load_events_for_job(self, job: Job) -> list[dict[str, Any]] | None:
        return None


@pytest.fixture
def audit_ctx() -> dict[str, Any]:
    jobs = MemoryJobRepository()
    aisles = MemoryAisleRepository()
    inventories = MemoryInventoryRepository()
    store = MagicMock()

    inv = Inventory(
        id="inv-api",
        name="I",
        status=InventoryStatus.PROCESSING,
        created_at=_NOW,
        updated_at=_NOW,
        client_id="client-api",
        processing_mode=InventoryProcessingMode.PRODUCTION,
    )
    inventories.save(inv)

    aisle = Aisle(
        id="aisle-api",
        inventory_id="inv-api",
        code="A",
        status=AisleStatus.PROCESSED,
        created_at=_NOW,
        updated_at=_NOW,
        client_supplier_id="cs-api",
    )
    aisles.save(aisle)

    job = Job(
        id="job-api",
        target_type="aisle",
        target_id="aisle-api",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        result_json={
            VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY: {
                "resolved": True,
                "resolved_count": 1,
                "reference_ids": ["r1"],
                "provider_consumed": True,
                "provider_consumed_count": 1,
            },
        },
        provider_name="gemini",
        model_name="m1",
    )
    jobs.save(job)

    audit_svc = RunAuditabilityService(
        job_repo=jobs,
        aisle_repo=aisles,
        inventory_repo=inventories,
        stored_artifact_reader=DefaultStoredArtifactReader(jobs, store),
        execution_log_loader=_FakeExecLogLoader(),
    )

    app.dependency_overrides[get_current_admin] = _admin
    app.dependency_overrides[get_job_repo] = lambda: jobs
    app.dependency_overrides[get_aisle_repo] = lambda: aisles
    app.dependency_overrides[get_inventory_repo] = lambda: inventories
    app.dependency_overrides[get_resolve_aisle_job_for_inventory_read_use_case] = (
        lambda: ResolveAisleJobForInventoryReadUseCase(job_repo=jobs, aisle_repo=aisles)
    )
    app.dependency_overrides[get_run_auditability_service] = lambda: audit_svc
    app.dependency_overrides[get_artifact_storage] = lambda: store

    yield {
        "inv_id": inv.id,
        "aisle_id": aisle.id,
        "job_id": job.id,
        "jobs": jobs,
        "aisles": aisles,
        "inventories": inventories,
        "default_audit_svc": audit_svc,
    }

    for k in (
        get_current_admin,
        get_job_repo,
        get_aisle_repo,
        get_inventory_repo,
        get_resolve_aisle_job_for_inventory_read_use_case,
        get_run_auditability_service,
        get_artifact_storage,
    ):
        app.dependency_overrides.pop(k, None)


def test_get_job_auditability_happy_path_200(audit_ctx: dict[str, Any]) -> None:
    r = client.get(
        f"/api/v3/inventories/{audit_ctx['inv_id']}/aisles/{audit_ctx['aisle_id']}/jobs/{audit_ctx['job_id']}/auditability"
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["job_id"] == audit_ctx["job_id"]
    assert data["client_id"] == "client-api"
    assert data["client_supplier_id"] == "cs-api"
    assert data["effective_prompt_hash"] == "hashh"
    assert data["supplier_prompt_config_id"] == "spc"
    assert data["supplier_prompt_config_version"] == "1"
    assert data["metadata_sources"]["execution_log"] is True
    assert data["metadata_sources"]["hybrid_report"] is False
    assert data["metadata_sources"]["run_audit_snapshot"] is False


def test_get_job_auditability_missing_hybrid_and_execution_log_200(audit_ctx: dict[str, Any]) -> None:
    """No durable hybrid report or execution log: still 200, sources false, missing keys explicit."""
    jobs: MemoryJobRepository = audit_ctx["jobs"]
    aisles: MemoryAisleRepository = audit_ctx["aisles"]
    inventories: MemoryInventoryRepository = audit_ctx["inventories"]
    store = MagicMock()
    no_log_svc = RunAuditabilityService(
        job_repo=jobs,
        aisle_repo=aisles,
        inventory_repo=inventories,
        stored_artifact_reader=DefaultStoredArtifactReader(jobs, store),
        execution_log_loader=_NoExecLogLoader(),
    )
    app.dependency_overrides[get_run_auditability_service] = lambda: no_log_svc
    try:
        r = client.get(
            f"/api/v3/inventories/{audit_ctx['inv_id']}/aisles/{audit_ctx['aisle_id']}/jobs/{audit_ctx['job_id']}/auditability"
        )
    finally:
        app.dependency_overrides[get_run_auditability_service] = lambda: audit_ctx["default_audit_svc"]

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["metadata_sources"]["hybrid_report"] is False
    assert data["metadata_sources"]["execution_log"] is False
    assert "hybrid_report" in data["missing_metadata"]
    assert "execution_log" in data["missing_metadata"]


def test_get_job_auditability_404_unknown_job(audit_ctx: dict[str, Any]) -> None:
    r = client.get(
        f"/api/v3/inventories/{audit_ctx['inv_id']}/aisles/{audit_ctx['aisle_id']}/jobs/does-not-exist/auditability"
    )
    assert r.status_code == 404


def test_get_job_auditability_cross_scope_wrong_aisle_404(audit_ctx: dict[str, Any]) -> None:
    """Job targets another aisle: URL must not return auditability for a mismatched aisle scope."""
    jobs: MemoryJobRepository = audit_ctx["jobs"]
    aisles: MemoryAisleRepository = audit_ctx["aisles"]
    aisle_b = Aisle(
        id="aisle-b-scope",
        inventory_id=audit_ctx["inv_id"],
        code="B",
        status=AisleStatus.CREATED,
        created_at=_NOW,
        updated_at=_NOW,
        client_supplier_id="cs-b",
    )
    aisles.save(aisle_b)
    job_on_b = Job(
        id="job-on-b",
        target_type="aisle",
        target_id=aisle_b.id,
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        result_json={},
    )
    jobs.save(job_on_b)
    r = client.get(
        f"/api/v3/inventories/{audit_ctx['inv_id']}/aisles/{audit_ctx['aisle_id']}/jobs/job-on-b/auditability"
    )
    assert r.status_code == 404
    assert r.json().get("detail") == HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C


def test_get_job_auditability_legacy_job_200(audit_ctx: dict[str, Any]) -> None:
    """Legacy: no client_id / client_supplier_id from joins (null inventory client, null aisle CS)."""
    jobs: MemoryJobRepository = audit_ctx["jobs"]
    aisles: MemoryAisleRepository = audit_ctx["aisles"]
    inventories: MemoryInventoryRepository = audit_ctx["inventories"]

    inv_legacy = Inventory(
        id="inv-legacy",
        name="Legacy inventory",
        status=InventoryStatus.PROCESSING,
        created_at=_NOW,
        updated_at=_NOW,
        client_id=None,
        processing_mode=InventoryProcessingMode.PRODUCTION,
    )
    inventories.save(inv_legacy)

    aisle_legacy = Aisle(
        id="aisle-legacy",
        inventory_id=inv_legacy.id,
        code="LEG",
        status=AisleStatus.PROCESSED,
        created_at=_NOW,
        updated_at=_NOW,
        client_supplier_id=None,
    )
    aisles.save(aisle_legacy)

    legacy_job = Job(
        id="job-legacy",
        target_type="aisle",
        target_id=aisle_legacy.id,
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        result_json={},
    )
    jobs.save(legacy_job)

    r = client.get(
        f"/api/v3/inventories/{inv_legacy.id}/aisles/{aisle_legacy.id}/jobs/job-legacy/auditability"
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["legacy_mode"] is True
    assert data["client_id"] is None
    assert data["client_supplier_id"] is None


def test_get_job_auditability_failed_job_200(audit_ctx: dict[str, Any]) -> None:
    jobs: MemoryJobRepository = audit_ctx["jobs"]
    failed = Job(
        id="job-failed",
        target_type="aisle",
        target_id=audit_ctx["aisle_id"],
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        result_json=None,
    )
    jobs.save(failed)
    r = client.get(
        f"/api/v3/inventories/{audit_ctx['inv_id']}/aisles/{audit_ctx['aisle_id']}/jobs/job-failed/auditability"
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "failed"
