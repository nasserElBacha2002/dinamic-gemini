"""Observability correction tests: capabilities, tenant binding, incremental log, timeline, artifacts."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.services.execution_log_incremental import (
    InvalidCursorError,
    encode_incremental_cursor,
    paginate_jsonl_stream,
)
from src.application.services.job_artifact_catalog_service import (
    JobArtifactCatalogService,
    artifact_id_from_parts,
)
from src.application.services.job_retry_chain_service import (
    JobRetryChainService,
    RetryChainIntegrity,
)
from src.application.services.job_source_asset_snapshot import build_job_source_asset_links
from src.application.services.job_timeline_service import derive_timeline_events
from src.application.services.observability_access import (
    CAP_DOWNLOAD_ARTIFACTS,
    CAP_FINALIZATION_RECOVERY,
    CAP_VIEW_FULL_PROMPT,
    CAP_VIEW_TECHNICAL_LOGS,
    ObservabilityAccessContext,
    ObservabilityAuthError,
    assert_inventory_client_scope,
    principal_has_capability,
    validate_principal_tenant_binding,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.auth.schemas import AuthUser
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.persistence.memory_job_source_asset_repository import (
    MemoryJobSourceAssetRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.pipeline.secret_redaction import redact_secrets_in_text, redact_secrets_in_value
from src.application.services.observability_output_sanitizer import sanitize_observability_value

UTC = timezone.utc


def test_platform_admin_global_scope() -> None:
    user = AuthUser(id="a", username="a", role="platform_admin", client_id=None)
    validate_principal_tenant_binding(user)
    inv_repo = MemoryInventoryRepository()
    now = datetime(2026, 7, 1, tzinfo=UTC)
    inv_repo.save(
        Inventory("inv-a", "A", InventoryStatus.DRAFT, now, now, client_id="c1")
    )
    access = ObservabilityAccessContext.from_user(user)
    assert assert_inventory_client_scope(inv_repo, inventory_id="inv-a", access=access).id == "inv-a"


def test_company_admin_requires_client_id() -> None:
    user = AuthUser(id="a", username="a", role="company_admin", client_id=None)
    with pytest.raises(ObservabilityAuthError):
        validate_principal_tenant_binding(user)


def test_operator_cross_company_denied() -> None:
    inv_repo = MemoryInventoryRepository()
    now = datetime(2026, 7, 1, tzinfo=UTC)
    inv_repo.save(
        Inventory("inv-a", "A", InventoryStatus.DRAFT, now, now, client_id="c1")
    )
    user = AuthUser(id="op", username="op", role="operator", client_id="c2")
    access = ObservabilityAccessContext.from_user(user)
    with pytest.raises(InventoryNotFoundError):
        assert_inventory_client_scope(inv_repo, inventory_id="inv-a", access=access)


def test_operator_lacks_technical_and_recovery() -> None:
    user = AuthUser(id="op", username="op", role="operator", client_id="c1")
    assert not principal_has_capability(user, CAP_VIEW_TECHNICAL_LOGS)
    assert not principal_has_capability(user, CAP_VIEW_FULL_PROMPT)
    assert not principal_has_capability(user, CAP_FINALIZATION_RECOVERY)
    assert principal_has_capability(user, CAP_DOWNLOAD_ARTIFACTS)


def test_legacy_administrator_role_is_platform() -> None:
    user = AuthUser(id="a", username="a", role="administrator", client_id=None)
    validate_principal_tenant_binding(user)
    assert principal_has_capability(user, CAP_FINALIZATION_RECOVERY)


def test_incremental_jsonl_does_not_require_full_materialization() -> None:
    lines = [
        json.dumps({"ts": f"2026-01-01T00:00:{i:02d}Z", "level": "info", "stage": "a", "message": f"m{i}"})
        + "\n"
        for i in range(100)
    ]
    # Interleave many more without loading as list of dicts first
    blob = "".join(lines * 120)  # 12000 events
    stream = io.BytesIO(blob.encode("utf-8"))
    page1 = paginate_jsonl_stream(
        stream, cursor=None, limit=50, max_limit=500, max_scan_bytes=5_000_000
    )
    assert len(page1.items) == 50
    assert page1.has_more is True
    assert page1.mode == "incremental"
    stream2 = io.BytesIO(blob.encode("utf-8"))
    page2 = paginate_jsonl_stream(
        stream2,
        cursor=page1.next_cursor,
        limit=50,
        max_limit=500,
        max_scan_bytes=5_000_000,
    )
    assert page2.items[0]["message"] != page1.items[0]["message"]


def test_invalid_cursor_and_filter_mismatch() -> None:
    stream = io.BytesIO(b'{"ts":"t","level":"info","stage":"a","message":"m"}\n')
    with pytest.raises(InvalidCursorError):
        paginate_jsonl_stream(
            stream,
            cursor="not-a-cursor",
            limit=10,
            max_limit=100,
            max_scan_bytes=10000,
        )
    fp_other = encode_incremental_cursor(byte_offset=0, sequence=0, filters_fp="deadbeefdeadbeef")
    stream2 = io.BytesIO(b'{"ts":"t","level":"info","stage":"a","message":"m"}\n')
    with pytest.raises(InvalidCursorError):
        paginate_jsonl_stream(
            stream2,
            cursor=fp_other,
            limit=10,
            max_limit=100,
            max_scan_bytes=10000,
            level="error",
        )


def test_timeline_does_not_infer_job_succeeded_from_completed_text() -> None:
    events = [
        {"ts": "t1", "stage": "preprocessing", "level": "info", "message": "Preprocessing completed"},
        {"ts": "t2", "stage": "worker", "level": "info", "message": "all succeed now"},
        {
            "ts": "t3",
            "stage": "job",
            "level": "info",
            "message": "done",
            "event_type": "JOB_SUCCEEDED",
        },
    ]
    derived = derive_timeline_events(job_id="j1", execution_id=None, raw_events=events)
    assert derived[0].event_type == "PREPROCESSING_STARTED"
    assert derived[1].event_type == "WORKER_STARTED"
    assert derived[2].event_type == "JOB_SUCCEEDED"


def test_artifact_versions_distinct_ids() -> None:
    a = artifact_id_from_parts(job_id="j", kind="hybrid_report_json", storage_key="jobs/j/a", version=1)
    b = artifact_id_from_parts(job_id="j", kind="hybrid_report_json", storage_key="jobs/j/b", version=2)
    assert a != b


def test_job_source_assets_snapshot_not_aisle_wide() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    assets = [
        SourceAsset(
            id=f"a{i}",
            aisle_id="aisle-1",
            type=SourceAssetType.PHOTO,
            original_filename=f"f{i}.jpg",
            storage_path=f"p{i}",
            mime_type="image/jpeg",
            uploaded_at=now,
            storage_key=f"uploads/a{i}.jpg",
            file_size_bytes=10 + i,
        )
        for i in range(20)
    ]
    links = build_job_source_asset_links(job_id="job-1", assets=assets)
    assert len(links) == 20
    assert [x.position_order for x in links] == list(range(20))
    repo = MemoryJobSourceAssetRepository()
    repo.replace_for_job("job-1", links)
    # Later aisle asset must not appear on job-1
    later = build_job_source_asset_links(
        job_id="job-2",
        assets=assets
        + [
            SourceAsset(
                id="new",
                aisle_id="aisle-1",
                type=SourceAssetType.PHOTO,
                original_filename="new.jpg",
                storage_path="pn",
                mime_type="image/jpeg",
                uploaded_at=now,
                storage_key="uploads/new.jpg",
            )
        ],
    )
    repo.replace_for_job("job-2", later)
    assert len(repo.list_for_job("job-1")) == 20
    assert len(repo.list_for_job("job-2")) == 21
    catalog = JobArtifactCatalogService(manifest_store=None, job_source_asset_repo=repo)
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
    page = catalog.list_for_job(job, aisle_id="aisle-1")
    assert page.inputs_legacy_unverified is False
    assert len([i for i in page.items if i.category.value == "INPUT"]) == 20
    assert all(i.source_asset_id != "new" for i in page.items)


def test_legacy_job_without_snapshot_marked() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    catalog = JobArtifactCatalogService(
        manifest_store=None, job_source_asset_repo=MemoryJobSourceAssetRepository()
    )
    job = Job(
        id="legacy",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    page = catalog.list_for_job(job, aisle_id="aisle-1")
    assert page.inputs_legacy_unverified is True
    assert page.items == []


def test_retry_chain_detects_fork() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    job_repo = MemoryJobRepository()
    root = Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={},
        created_at=now,
        updated_at=now,
        attempt_count=1,
    )
    c1 = Job(
        id="j2",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={},
        created_at=now,
        updated_at=now,
        attempt_count=2,
        retry_of_job_id="j1",
    )
    c2 = Job(
        id="j3",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        attempt_count=2,
        retry_of_job_id="j1",
    )
    for j in (root, c1, c2):
        job_repo.save(j)
    view = JobRetryChainService(job_repo).build(c1, aisle_id="a1")
    assert view.integrity == RetryChainIntegrity.FORKED
    assert any("fork_at=j1" in w for w in view.warnings)


def test_secret_redaction_table() -> None:
    samples = [
        "Bearer abc123",
        "sk-ant-secretvalue123456",
        "password=secret",
        "PWD=secret",
        "Server=x;UID=u;PWD=p;",
        "https://x?X-Amz-Signature=abc",
    ]
    for s in samples:
        out = redact_secrets_in_text(s)
        assert "abc123" not in out or "[REDACTED]" in out
        assert "secretvalue" not in out
    nested = sanitize_observability_value(
        {"authorization": "Bearer x", "ok": 1, "deep": {"api_key": "k"}},
        user=AuthUser(id="op", username="op", role="operator", client_id="c1"),
        allow_full_prompt=False,
        allow_stack_traces=False,
    )
    assert nested["authorization"] == "[REDACTED]"
    assert nested["ok"] == 1
