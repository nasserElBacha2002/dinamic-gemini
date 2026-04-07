"""API tests: aisle-level aggregated execution log (multi-job)."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.dependencies import get_artifact_storage, get_aisle_repo, get_inventory_repo, get_job_repo
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def test_aisle_aggregate_execution_log_merges_jobs_and_metadata() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-agg", "Agg", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-agg", "inv-agg", "AG", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    j1 = Job(
        id="job-a",
        target_type="aisle",
        target_id="aisle-agg",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        provider_name="openai",
        model_name="gpt-test",
        prompt_key="global_v21",
        prompt_version="global_v21@v1",
        execution_id="ex-a",
    )
    j2 = Job(
        id="job-b",
        target_type="aisle",
        target_id="aisle-agg",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        provider_name="gemini",
        model_name="gemini-test",
        prompt_key="global_v21",
        prompt_version="global_v21@v1",
        execution_id="ex-b",
    )
    job_repo.save(j1)
    job_repo.save(j2)

    base = Path(tempfile.mkdtemp(prefix="agg_exec_"))
    r1 = base / "job-a" / RUN_ID
    r2 = base / "job-b" / RUN_ID
    r1.mkdir(parents=True)
    r2.mkdir(parents=True)
    (r1 / "execution_log.jsonl").write_text(
        '{"ts":"2024-06-01T12:00:00+00:00","stage":"S","level":"info","message":"first","payload":{}}\n',
        encoding="utf-8",
    )
    (r2 / "execution_log.jsonl").write_text(
        '{"ts":"2024-06-01T11:00:00+00:00","stage":"S","level":"info","message":"earlier","payload":{}}\n',
        encoding="utf-8",
    )

    fake_settings = type(
        "Settings",
        (),
        {
            "output_dir": str(base),
            "artifact_storage_legacy_local_read_enabled": True,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    store = V3ArtifactStorageAdapter(base / "artifact-unused")
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        with patch("src.api.services.v3_stored_artifact_access.load_settings", return_value=fake_settings):
            c = TestClient(app)
            resp = c.get("/api/v3/inventories/inv-agg/aisles/aisle-agg/execution-log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["requested_job_id"] is None
        assert set(data["available_job_ids"]) == {"job-a", "job-b"}
        assert [e["message"] for e in data["events"]] == ["earlier", "first"]
        assert data["events"][0]["event_job_id"] == "job-b"
        assert data["events"][0]["is_requested_job_event"] is False
        by_id = {j["job_id"]: j for j in data["jobs"]}
        assert by_id["job-a"]["provider_name"] == "openai"
        assert by_id["job-b"]["model_name"] == "gemini-test"
        assert all(s["status"] == "ok" for s in data["log_sources"])
    finally:
        for k in list(app.dependency_overrides.keys()):
            app.dependency_overrides.pop(k, None)
        shutil.rmtree(base, ignore_errors=True)


def test_aisle_aggregate_skips_unreadable_job_without_failing() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-skip", "Skip", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-skip", "inv-skip", "SK", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    j_ok = Job(
        id="job-ok",
        target_type="aisle",
        target_id="aisle-skip",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    j_bad = Job(
        id="job-bad",
        target_type="aisle",
        target_id="aisle-skip",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={},
        created_at=now,
        updated_at=now,
        result_json={
            "durable_artifacts": {
                "execution_log": {
                    "storage_provider": "",
                    "storage_key": "",
                }
            }
        },
    )
    job_repo.save(j_ok)
    job_repo.save(j_bad)

    base = Path(tempfile.mkdtemp(prefix="skip_exec_"))
    run_dir = base / "job-ok" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "execution_log.jsonl").write_text(
        '{"ts":"2024-06-01T12:00:00+00:00","stage":"S","level":"info","message":"only","payload":{}}\n',
        encoding="utf-8",
    )

    fake_settings = type(
        "Settings",
        (),
        {
            "output_dir": str(base),
            "artifact_storage_legacy_local_read_enabled": True,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    store = V3ArtifactStorageAdapter(base / "artifact-unused")
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        with patch("src.api.services.v3_stored_artifact_access.load_settings", return_value=fake_settings):
            c = TestClient(app)
            resp = c.get("/api/v3/inventories/inv-skip/aisles/aisle-skip/execution-log")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["message"] == "only"
        src_by = {s["job_id"]: s for s in data["log_sources"]}
        assert src_by["job-ok"]["status"] == "ok"
        assert src_by["job-bad"]["status"] == "missing"
    finally:
        for k in list(app.dependency_overrides.keys()):
            app.dependency_overrides.pop(k, None)
        shutil.rmtree(base, ignore_errors=True)


def test_aisle_aggregate_execution_log_txt_download() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-txt", "Txt", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-txt", "inv-txt", "TX", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-txt",
        target_type="aisle",
        target_id="aisle-txt",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    base = Path(tempfile.mkdtemp(prefix="txt_exec_"))
    run_dir = base / "job-txt" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "execution_log.jsonl").write_text(
        json.dumps(
            {
                "ts": "2024-06-01T12:00:00+00:00",
                "stage": "S",
                "level": "info",
                "message": "plain",
                "payload": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    fake_settings = type(
        "Settings",
        (),
        {
            "output_dir": str(base),
            "artifact_storage_legacy_local_read_enabled": True,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    store = V3ArtifactStorageAdapter(base / "artifact-unused")
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        with patch("src.api.services.v3_stored_artifact_access.load_settings", return_value=fake_settings):
            c = TestClient(app)
            r = c.get("/api/v3/inventories/inv-txt/aisles/aisle-txt/execution-log.txt")
        assert r.status_code == 200
        assert "text/plain" in r.headers.get("content-type", "").lower()
        cd = r.headers.get("content-disposition", "")
        assert "inventory_inv-txt_aisle_aisle-txt_execution_log.txt" in cd
        assert b"job_id=job-txt" in r.content
        assert b"plain" in r.content
    finally:
        for k in list(app.dependency_overrides.keys()):
            app.dependency_overrides.pop(k, None)
        shutil.rmtree(base, ignore_errors=True)
