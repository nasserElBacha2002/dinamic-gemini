"""Observability company scope, artifact catalog, retry chain, log pagination, secret redaction."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.services.execution_log_pagination import paginate_execution_log_events
from src.application.services.job_artifact_catalog_service import (
    JobArtifactCatalogService,
    assert_job_owned_storage_key,
)
from src.application.services.job_retry_chain_service import JobRetryChainService
from src.application.services.observability_access import (
    CAP_VIEW_FULL_PROMPT,
    ObservabilityAccessContext,
    assert_inventory_client_scope,
    principal_has_capability,
)
from src.application.use_cases.aisles.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.pipeline.secret_redaction import redact_secrets_in_text, redact_secrets_in_value

UTC = timezone.utc


def _inv(client_id: str, inv_id: str = "inv-a") -> Inventory:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    return Inventory(
        id=inv_id,
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id=client_id,
    )


def test_cross_company_inventory_scope_denied() -> None:
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(_inv("client-a", "inv-a"))
    access = ObservabilityAccessContext.from_user(
        AuthUser(id="u", username="op", role="company_admin", client_id="client-b")
    )
    with pytest.raises(InventoryNotFoundError):
        assert_inventory_client_scope(inv_repo, inventory_id="inv-a", access=access)


def test_same_company_inventory_scope_ok() -> None:
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(_inv("client-a", "inv-a"))
    access = ObservabilityAccessContext.from_user(
        AuthUser(id="u", username="op", role="company_admin", client_id="client-a")
    )
    got = assert_inventory_client_scope(inv_repo, inventory_id="inv-a", access=access)
    assert got.client_id == "client-a"


def test_platform_admin_unbound_can_access_any_inventory() -> None:
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(_inv("client-a", "inv-a"))
    access = ObservabilityAccessContext.from_user(
        AuthUser(id="admin", username="admin", role="administrator", client_id=None)
    )
    got = assert_inventory_client_scope(inv_repo, inventory_id="inv-a", access=access)
    assert got.id == "inv-a"


def test_resolve_job_enforces_client_scope() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(_inv("client-a", "inv-a"))
    aisle_repo.save(Aisle("aisle-1", "inv-a", "A1", AisleStatus.PROCESSED, now, now))
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)
    uc = ResolveAisleJobForInventoryReadUseCase(job_repo, aisle_repo, inv_repo)
    ok_user = AuthUser(id="u", username="a", role="company_admin", client_id="client-a")
    assert uc.execute("inv-a", "aisle-1", "job-1", access_user=ok_user).id == "job-1"
    bad_user = AuthUser(id="u", username="b", role="company_admin", client_id="client-b")
    with pytest.raises(InventoryNotFoundError):
        uc.execute("inv-a", "aisle-1", "job-1", access_user=bad_user)


def test_operator_cannot_view_full_prompt() -> None:
    user = AuthUser(id="op", username="op", role="operator", client_id="c1")
    assert not principal_has_capability(user, CAP_VIEW_FULL_PROMPT)


def test_retry_chain_two_attempts() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    j1 = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={},
        created_at=now,
        updated_at=now,
        attempt_count=1,
        failure_code="PROVIDER_INVALID_REQUEST",
    )
    j2 = Job(
        id="job-2",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        attempt_count=2,
        retry_of_job_id="job-1",
    )
    job_repo.save(j1)
    job_repo.save(j2)
    view = JobRetryChainService(job_repo).build(j2, aisle_id="aisle-1")
    assert view.root_job_id == "job-1"
    assert view.current_job_id == "job-2"
    assert len(view.attempts) == 2
    assert view.attempts[0].is_selected is False
    assert view.attempts[1].is_selected is True
    assert view.attempts[1].is_current is True


def test_artifact_catalog_from_durable_result_json() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        result_json={
            "durable_artifacts": {
                "hybrid_report_json": {
                    "storage_key": "jobs/job-1/run/hybrid_report.json",
                    "content_type": "application/json",
                    "size_bytes": 12,
                }
            }
        },
    )
    svc = JobArtifactCatalogService(manifest_store=None, job_source_asset_repo=None)
    page = svc.list_for_job(job, aisle_id="aisle-1")
    assert len(page.items) == 1
    assert page.items[0].kind == "hybrid_report_json"
    assert page.items[0].category.value == "OUTPUT"
    assert page.items[0].storage_key == "jobs/job-1/run/hybrid_report.json"


def test_storage_key_namespace_validation() -> None:
    assert_job_owned_storage_key(job_id="job-1", storage_key="jobs/job-1/run/a.json")
    with pytest.raises(ValueError):
        assert_job_owned_storage_key(job_id="job-1", storage_key="jobs/other/run/a.json")


def test_execution_log_pagination_stable_cursor() -> None:
    events = [
        {"ts": "2026-01-01T00:00:00Z", "level": "info", "stage": "a", "message": f"m{i}"}
        for i in range(250)
    ]
    # duplicate timestamp
    events.append({"ts": "2026-01-01T00:00:00Z", "level": "error", "stage": "b", "message": "dup"})
    page1 = paginate_execution_log_events(events, limit=100, max_limit=500)
    assert len(page1.items) == 100
    assert page1.has_more is True
    page2 = paginate_execution_log_events(
        events, cursor=page1.next_cursor, limit=100, max_limit=500
    )
    assert len(page2.items) == 100
    assert page1.items[0]["message"] != page2.items[0]["message"]
    filtered = paginate_execution_log_events(events, level="error", limit=50)
    assert all(str(e.get("level")).lower() == "error" for e in filtered.items)


def test_secret_redaction() -> None:
    text = "Authorization: Bearer abc123 sk-ant-secretvalue password=secret PWD=secret"
    out = redact_secrets_in_text(text)
    assert "abc123" not in out
    assert "secretvalue" not in out
    assert "password=secret" not in out.lower() or "[REDACTED]" in out
    payload = redact_secrets_in_value(
        {"authorization": "Bearer x", "nested": {"api_key": "sk-proj-abc", "ok": 1}}
    )
    assert payload["authorization"] == "[REDACTED]"
    assert payload["nested"]["api_key"] == "[REDACTED]"
    assert payload["nested"]["ok"] == 1
