"""Tests for :class:`ObservabilityMetricsService` (Phase H5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.application.services.observability_metrics_service import (
    METRICS_JOB_LIMIT,
    ObservabilityMetricsFilters,
    ObservabilityMetricsService,
    resolve_metrics_time_range,
)
from src.application.services.run_audit_snapshot import RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.pipeline.run_metadata import RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT

_NOW = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)


def _inv(inv_id: str, *, client_id: str = "c1") -> Inventory:
    return Inventory(
        id=inv_id,
        name="I",
        status=InventoryStatus.PROCESSING,
        created_at=_NOW,
        updated_at=_NOW,
        client_id=client_id,
        processing_mode=InventoryProcessingMode.PRODUCTION,
    )


def _aisle(aid: str, inv_id: str, *, cs: str = "s1") -> Aisle:
    return Aisle(
        id=aid,
        inventory_id=inv_id,
        code="A",
        status=AisleStatus.PROCESSED,
        created_at=_NOW,
        updated_at=_NOW,
        client_supplier_id=cs,
    )


def _job(
    jid: str,
    *,
    status: JobStatus,
    aisle_id: str = "a1",
    created: datetime | None = None,
    snap: dict | None = None,
    provider: str | None = "gemini",
    model: str | None = "m1",
) -> Job:
    rj: dict | None = None
    if snap is not None:
        rj = {RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT: snap}
    return Job(
        id=jid,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=status,
        payload_json={},
        created_at=created or _NOW,
        updated_at=_NOW,
        result_json=rj,
        provider_name=provider,
        model_name=model,
    )


def _svc() -> tuple[ObservabilityMetricsService, MemoryJobRepository, MemoryAisleRepository, MemoryInventoryRepository]:
    jobs = MemoryJobRepository()
    aisles = MemoryAisleRepository()
    inv = MemoryInventoryRepository()
    inv.save(_inv("inv1"))
    aisles.save(_aisle("a1", "inv1", cs="s1"))
    aisles.save(_aisle("a2", "inv1", cs="s2"))
    return ObservabilityMetricsService(job_repo=jobs, aisle_repo=aisles, inventory_repo=inv), jobs, aisles, inv


def test_resolve_range_defaults_and_max() -> None:
    to = datetime(2026, 6, 1, tzinfo=timezone.utc)
    f, t = resolve_metrics_time_range(None, to)
    assert (t - f).days == 30
    with pytest.raises(ValueError, match="from_after_to"):
        resolve_metrics_time_range(to, to - timedelta(days=1))
    with pytest.raises(ValueError, match="range_too_large"):
        resolve_metrics_time_range(to - timedelta(days=91), to)


def test_totals_terminal_only_and_rates() -> None:
    svc, jobs, _, _ = _svc()
    jobs.save(_job("j1", status=JobStatus.SUCCEEDED))
    jobs.save(_job("j2", status=JobStatus.FAILED))
    jobs.save(_job("j3", status=JobStatus.CANCELED))
    jobs.save(_job("j4", status=JobStatus.RUNNING))
    f = ObservabilityMetricsFilters(
        created_from=_NOW - timedelta(days=1),
        created_to=_NOW + timedelta(days=1),
    )
    d = svc.build(f)
    assert d["totals"]["runs_total"] == 3
    assert d["totals"]["runs_succeeded"] == 1
    assert d["totals"]["runs_failed"] == 2
    assert d["totals"]["success_rate"] == round(1 / 3, 4)
    assert d["totals"]["failure_rate"] == round(2 / 3, 4)


def test_by_client_and_supplier_grouping() -> None:
    svc, jobs, aisles, inv = _svc()
    inv.save(_inv("inv2", client_id="c2"))
    aisles.save(_aisle("a3", "inv2", cs="s3"))

    jobs.save(_job("j1", status=JobStatus.SUCCEEDED, aisle_id="a1"))
    jobs.save(_job("j2", status=JobStatus.SUCCEEDED, aisle_id="a3"))

    f = ObservabilityMetricsFilters(
        created_from=_NOW - timedelta(days=1),
        created_to=_NOW + timedelta(days=1),
    )
    d = svc.build(f)
    by_c = {row["client_id"]: row for row in d["by_client"]}
    assert by_c["c1"]["runs_total"] == 1
    assert by_c["c2"]["runs_total"] == 1
    by_s = {row["client_supplier_id"]: row for row in d["by_supplier"]}
    assert by_s["s1"]["runs_total"] == 1
    assert by_s["s3"]["runs_total"] == 1


def test_fallback_and_snapshot_quality_counters() -> None:
    svc, jobs, _, _ = _svc()
    snap = {
        "schema_version": RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION,
        "supplier_prompt_fallback_used": True,
        "supplier_prompt_config_id": "spc",
        "reference_source": "supplier_reference_images",
        "reference_image_count": 2,
        "supplier_reference_images_used": True,
    }
    jobs.save(_job("j1", status=JobStatus.SUCCEEDED, snap=snap))
    jobs.save(_job("j2", status=JobStatus.SUCCEEDED, snap=None))

    f = ObservabilityMetricsFilters(
        created_from=_NOW - timedelta(days=1),
        created_to=_NOW + timedelta(days=1),
    )
    d = svc.build(f)
    assert d["totals"]["fallback_runs"] == 1
    assert d["data_quality"]["jobs_with_audit_snapshot"] == 1
    assert d["data_quality"]["jobs_without_audit_snapshot"] == 1
    assert d["totals"]["legacy_runs"] == 1


def test_missing_reference_and_prompt_from_snapshot() -> None:
    svc, jobs, _, _ = _svc()
    snap_ref = {
        "schema_version": RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION,
        "client_id": "c1",
        "supplier_prompt_config_id": "x",
        "reference_source": "supplier_reference_images",
        "reference_image_count": 0,
        "supplier_reference_images_used": False,
    }
    snap_prompt = {
        "schema_version": RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION,
        "client_id": "c1",
        "supplier_prompt_fallback_used": True,
        "supplier_prompt_fallback_reason": "NO_ACTIVE_SUPPLIER_PROMPT_CONFIG",
    }
    jobs.save(_job("j1", status=JobStatus.SUCCEEDED, snap=snap_ref))
    jobs.save(_job("j2", status=JobStatus.SUCCEEDED, snap=snap_prompt))
    f = ObservabilityMetricsFilters(
        created_from=_NOW - timedelta(days=1),
        created_to=_NOW + timedelta(days=1),
    )
    d = svc.build(f)
    assert d["totals"]["missing_reference_runs"] >= 1
    assert d["totals"]["missing_prompt_config_runs"] >= 1


def test_provider_model_filter() -> None:
    svc, jobs, _, _ = _svc()
    jobs.save(_job("j1", status=JobStatus.SUCCEEDED, provider="openai", model="gpt-4"))
    jobs.save(_job("j2", status=JobStatus.SUCCEEDED, provider="gemini", model="m1"))
    f = ObservabilityMetricsFilters(
        created_from=_NOW - timedelta(days=1),
        created_to=_NOW + timedelta(days=1),
        provider_name="openai",
    )
    d = svc.build(f)
    assert d["totals"]["runs_total"] == 1


def test_row_cap_constant() -> None:
    assert METRICS_JOB_LIMIT == 5000
