"""Tests for :mod:`src.application.services.run_auditability_service`."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.application.services.reference_usage_from_job_result import (
    VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY,
)
from src.application.services.run_auditability_service import RunAuditabilityService
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeJobRepo:
    def __init__(self, job: Job | None) -> None:
        self._job = job

    def get_by_id(self, job_id: str) -> Job | None:
        return self._job if self._job and self._job.id == job_id else None


class _FakeAisleRepo:
    def __init__(self, aisles: dict[str, Aisle]) -> None:
        self._aisles = aisles

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._aisles.get(aisle_id)


class _FakeInventoryRepo:
    def __init__(self, inventories: dict[str, Inventory]) -> None:
        self._inventories = inventories

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._inventories.get(inventory_id)


class _FakeArtifactReader:
    def __init__(self, hybrid: dict[str, Any] | None) -> None:
        self._hybrid = hybrid

    def load_hybrid_report_json_for_job(self, job_id: str) -> dict[str, Any] | None:
        return self._hybrid


class _FakeExecLogLoader:
    def __init__(self, events: list[dict[str, Any]] | None) -> None:
        self._events = events

    def try_load_events_for_job(self, job: Job) -> list[dict[str, Any]] | None:
        return self._events


def _base_aisle(aisle_id: str, inventory_id: str, *, cs: str | None = "cs-1") -> Aisle:
    return Aisle(
        id=aisle_id,
        inventory_id=inventory_id,
        code="A1",
        status=AisleStatus.PROCESSED,
        created_at=_NOW,
        updated_at=_NOW,
        client_supplier_id=cs,
    )


def _base_inventory(inv_id: str, *, client_id: str | None = "cl-1") -> Inventory:
    return Inventory(
        id=inv_id,
        name="Inv",
        status=InventoryStatus.PROCESSING,
        created_at=_NOW,
        updated_at=_NOW,
        client_id=client_id,
        processing_mode=InventoryProcessingMode.PRODUCTION,
    )


def _base_job(
    job_id: str,
    *,
    target_id: str = "aisle-1",
    result_json: dict[str, Any] | None = None,
    status: JobStatus = JobStatus.SUCCEEDED,
) -> Job:
    return Job(
        id=job_id,
        target_type="aisle",
        target_id=target_id,
        job_type="process_aisle",
        status=status,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        result_json=result_json,
        provider_name="gemini",
        model_name="gemini-2.0-flash",
        prompt_key="global_v21",
        prompt_version="global_v21@v2.1",
    )


def _analysis_request_event() -> dict[str, Any]:
    return {
        "ts": "2026-01-01T00:00:00+00:00",
        "stage": "AnalysisStage",
        "level": "info",
        "message": "Analysis request prepared",
        "payload": {
            "event_type": "analysis_request",
            "pipeline_provider": "gemini",
            "prompt_composition": {
                "resolved_llm_provider_key": "gemini",
                "model_name": "gemini-2.0-flash",
                "effective_prompt": {
                    "protected_prompt_contract_key": "hybrid_global",
                    "protected_prompt_contract_version": "v2",
                    "effective_prompt_hash": "abc123",
                    "supplier_prompt_config_id": "spc-1",
                    "supplier_prompt_config_version": "3",
                    "fallback_used": False,
                    "fallback_reason": None,
                    "warnings": ["w1"],
                    "reference_image_ids": ["rid-1"],
                    "reference_source": "supplier_reference_images",
                },
            },
        },
    }


def test_happy_path_full_metadata() -> None:
    job_id = "job-happy"
    inv = _base_inventory("inv-1")
    aisle = _base_aisle("aisle-1", "inv-1")
    job = _base_job(
        job_id,
        result_json={
            "provider": "gemini",
            VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY: {
                "resolved": True,
                "resolved_count": 1,
                "reference_ids": ["rid-1"],
                "reference_source": "supplier_reference_images",
                "provider_consumed": True,
                "provider_consumed_count": 1,
            },
        },
    )
    hybrid = {
        "supplier_traceability": {
            "supplier_prompt": {
                "supplier_prompt_config_id": "spc-1",
                "supplier_prompt_config_version": "3",
                "fallback_used": False,
                "fallback_reason": None,
                "resolution_status": "resolved",
            },
            "supplier_references": {
                "client_supplier_id": "cs-1",
                "image_count": 1,
                "reference_source": "supplier_reference_images",
            },
        }
    }
    events = [_analysis_request_event()]

    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({"aisle-1": aisle}),
        inventory_repo=_FakeInventoryRepo({"inv-1": inv}),
        stored_artifact_reader=_FakeArtifactReader(hybrid),
        execution_log_loader=_FakeExecLogLoader(events),
    )
    view = svc.build(job_id)
    assert view is not None
    assert view.client_id == "cl-1"
    assert view.client_supplier_id == "cs-1"
    assert view.effective_prompt_hash == "abc123"
    assert view.supplier_prompt_config_id == "spc-1"
    assert view.supplier_prompt_config_version == "3"
    assert view.supplier_prompt_fallback_used is False
    assert view.prompt_composition_available is True
    assert view.metadata_sources.hybrid_report is True
    assert view.metadata_sources.execution_log is True
    assert view.reference_usage is not None
    assert view.reference_usage.resolved is True
    assert "hybrid_report" not in view.missing_metadata
    assert "execution_log" not in view.missing_metadata
    assert view.legacy_mode is False


def test_missing_hybrid_report() -> None:
    job = _base_job("job-noh")
    aisle = _base_aisle("aisle-1", "inv-1")
    inv = _base_inventory("inv-1")
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({"aisle-1": aisle}),
        inventory_repo=_FakeInventoryRepo({"inv-1": inv}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader([_analysis_request_event()]),
    )
    view = svc.build("job-noh")
    assert view is not None
    assert view.metadata_sources.hybrid_report is False
    assert "hybrid_report" in view.missing_metadata
    assert view.supplier_prompt_config_id == "spc-1"


def test_missing_execution_log() -> None:
    job = _base_job("job-noe")
    aisle = _base_aisle("aisle-1", "inv-1")
    inv = _base_inventory("inv-1")
    hybrid = {
        "supplier_traceability": {
            "supplier_prompt": {
                "supplier_prompt_config_id": "x",
                "supplier_prompt_config_version": "1",
                "fallback_used": True,
                "fallback_reason": "missing",
            },
        }
    }
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({"aisle-1": aisle}),
        inventory_repo=_FakeInventoryRepo({"inv-1": inv}),
        stored_artifact_reader=_FakeArtifactReader(hybrid),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    view = svc.build("job-noe")
    assert view is not None
    assert view.metadata_sources.execution_log is False
    assert "execution_log" in view.missing_metadata
    assert view.prompt_composition_available is False
    assert view.effective_prompt_hash is None


def test_legacy_job_no_client_no_supplier() -> None:
    job = _base_job("job-leg", target_id="aisle-x")
    aisle = _base_aisle("aisle-x", "inv-x", cs=None)
    inv = _base_inventory("inv-x", client_id=None)
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({"aisle-x": aisle}),
        inventory_repo=_FakeInventoryRepo({"inv-x": inv}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    view = svc.build("job-leg")
    assert view is not None
    assert view.legacy_mode is True
    assert view.client_id is None
    assert view.client_supplier_id is None


def test_failed_job_no_crash() -> None:
    job = _base_job(
        "job-fail",
        result_json=None,
        status=JobStatus.FAILED,
    )
    aisle = _base_aisle("aisle-1", "inv-1")
    inv = _base_inventory("inv-1")
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({"aisle-1": aisle}),
        inventory_repo=_FakeInventoryRepo({"inv-1": inv}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    view = svc.build("job-fail")
    assert view is not None
    assert view.status == "failed"
    assert view.effective_prompt_hash is None


def test_non_aisle_target_skips_joins() -> None:
    job = Job(
        id="job-other",
        target_type="inventory",
        target_id="inv-x",
        job_type="other",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        provider_name="openai",
    )
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({}),
        inventory_repo=_FakeInventoryRepo({}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    view = svc.build("job-other")
    assert view is not None
    assert view.aisle_id is None
    assert view.inventory_id is None
    assert view.client_id is None
    assert view.metadata_sources.aisle_join is False
    assert view.metadata_sources.inventory_join is False


def test_missing_aisle_row_marks_aisle_row_missing() -> None:
    job = _base_job("job-miss-aisle", target_id="aisle-missing")
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({}),
        inventory_repo=_FakeInventoryRepo({}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    view = svc.build("job-miss-aisle")
    assert view is not None
    assert "aisle_row" in view.missing_metadata


def test_missing_inventory_row_marks_inventory_row_missing() -> None:
    aisle = _base_aisle("aisle-1", "inv-missing")
    job = _base_job("job-miss-inv")
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(job),
        aisle_repo=_FakeAisleRepo({"aisle-1": aisle}),
        inventory_repo=_FakeInventoryRepo({}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    view = svc.build("job-miss-inv")
    assert view is not None
    assert view.inventory_id == "inv-missing"
    assert "inventory_row" in view.missing_metadata


def test_unknown_job_returns_none() -> None:
    svc = RunAuditabilityService(
        job_repo=_FakeJobRepo(None),
        aisle_repo=_FakeAisleRepo({}),
        inventory_repo=_FakeInventoryRepo({}),
        stored_artifact_reader=_FakeArtifactReader(None),
        execution_log_loader=_FakeExecLogLoader(None),
    )
    assert svc.build("missing") is None
