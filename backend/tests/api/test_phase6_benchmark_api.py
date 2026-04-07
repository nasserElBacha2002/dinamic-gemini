"""Phase 6 — benchmark compare, promote, and explicit benchmark export API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_export_aisle_benchmark_compare_csv_use_case,
    get_export_aisle_benchmark_run_csv_use_case,
    get_inventory_repo,
    get_job_repo,
    get_position_repo,
    get_product_record_repo,
    get_promote_aisle_operational_job_use_case,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def _seed() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    inv_repo.save(Inventory("inv-b6", "B6", InventoryStatus.IN_REVIEW, now, now))
    aisle_repo.save(
        Aisle("aisle-b6", "inv-b6", "A", AisleStatus.PROCESSED, now, now, operational_job_id="j1")
    )
    for jid in ("j1", "j2"):
        job_repo.save(
            Job(
                id=jid,
                target_type="aisle",
                target_id="aisle-b6",
                job_type="process_aisle",
                status=JobStatus.SUCCEEDED,
                payload_json={},
                created_at=now,
                updated_at=now,
                provider_name="openai",
                model_name="gpt",
                prompt_key="global_v21",
                prompt_version="pv1",
            )
        )
    pos_repo.save(
        Position(
            id="pb6-a",
            aisle_id="aisle-b6",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "S1", "final_quantity": 1},
            job_id="j1",
        )
    )
    pos_repo.save(
        Position(
            id="pb6-b",
            aisle_id="aisle-b6",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={"internal_code": "S1", "final_quantity": 2},
            job_id="j2",
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_position_repo] = lambda: pos_repo
    app.dependency_overrides[get_product_record_repo] = lambda: prod_repo
    app.dependency_overrides.pop(get_promote_aisle_operational_job_use_case, None)
    app.dependency_overrides.pop(get_export_aisle_benchmark_run_csv_use_case, None)
    app.dependency_overrides.pop(get_export_aisle_benchmark_compare_csv_use_case, None)


def _clear() -> None:
    for dep in (
        get_current_admin,
        get_inventory_repo,
        get_aisle_repo,
        get_job_repo,
        get_position_repo,
        get_product_record_repo,
    ):
        app.dependency_overrides.pop(dep, None)


def test_benchmark_compare_rejects_same_job_ids() -> None:
    _seed()
    try:
        c = TestClient(app)
        r = c.get(
            "/api/v3/inventories/inv-b6/aisles/aisle-b6/benchmark/compare",
            params={"job_a_id": "j1", "job_b_id": "j1"},
        )
        assert r.status_code == 422
        assert "different benchmark runs" in (r.json().get("detail") or "").lower()
    finally:
        _clear()


def test_benchmark_compare_and_jobs_list_operational_flag() -> None:
    _seed()
    try:
        c = TestClient(app)
        r = c.get(
            "/api/v3/inventories/inv-b6/aisles/aisle-b6/benchmark/compare",
            params={"job_a_id": "j1", "job_b_id": "j2"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["workflow"] == "benchmark_compare"
        assert body["diff_summary"]["quantity_changed"] == 1

        jr = c.get("/api/v3/inventories/inv-b6/aisles/aisle-b6/jobs")
        assert jr.status_code == 200
        jobs = jr.json()["jobs"]
        assert any(j["id"] == "j1" and j.get("is_operational") is True for j in jobs)
        assert any(j["id"] == "j2" and j.get("is_operational") is False for j in jobs)
    finally:
        _clear()


def test_promote_operational_updates_pointer() -> None:
    _seed()
    try:
        c = TestClient(app)
        pr = c.post(
            "/api/v3/inventories/inv-b6/aisles/aisle-b6/promote-operational",
            json={"job_id": "j2"},
        )
        assert pr.status_code == 200
        assert pr.json()["operational_job_id"] == "j2"

        jr = c.get("/api/v3/inventories/inv-b6/aisles/aisle-b6/jobs")
        assert jr.json()["operational_job_id"] == "j2"
        jobs = jr.json()["jobs"]
        assert any(j["id"] == "j2" and j.get("is_operational") is True for j in jobs)
    finally:
        _clear()


def test_benchmark_export_requires_exclusive_params() -> None:
    _seed()
    try:
        c = TestClient(app)
        r = c.get(
            "/api/v3/inventories/inv-b6/aisles/aisle-b6/benchmark/export",
            params={"format": "csv"},
        )
        assert r.status_code == 422

        r2 = c.get(
            "/api/v3/inventories/inv-b6/aisles/aisle-b6/benchmark/export",
            params={"format": "csv", "run_job_id": "j1", "job_a_id": "j1", "job_b_id": "j2"},
        )
        assert r2.status_code == 422

        ok = c.get(
            "/api/v3/inventories/inv-b6/aisles/aisle-b6/benchmark/export",
            params={"format": "csv", "run_job_id": "j1"},
        )
        assert ok.status_code == 200
        assert "benchmark_run_job_id" in ok.text
    finally:
        _clear()


def test_analytics_benchmark_compare_alias() -> None:
    _seed()
    try:
        c = TestClient(app)
        r = c.get(
            "/api/v3/analytics/benchmark/inventories/inv-b6/aisles/aisle-b6/compare",
            params={"job_a_id": "j1", "job_b_id": "j2"},
        )
        assert r.status_code == 200
        assert r.json()["read_only"] is True
    finally:
        _clear()
