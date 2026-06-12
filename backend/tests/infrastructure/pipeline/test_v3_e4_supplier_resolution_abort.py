"""E4: v3 executor aborts hybrid run when ``SupplierPromptResolver`` returns ``error``."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_executor import RUN_ID, V3JobExecutor, _V3HybridRunParams
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import AnalysisContext
from tests.infrastructure.pipeline.test_v3_job_executor_phase5 import (
    FixedClock,
    InMemoryAisleRepo,
    InMemoryInventoryRepo,
    InMemoryJobRepo,
    NoopRepo,
)
from tests.support.worker_phase2.executor_persist_deps import memory_executor_persist_kwargs


def test_v3_hybrid_run_aborts_before_pipeline_when_resolver_errors(tmp_path: Path) -> None:
    now = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "e4-abort"
    aisle_id = "aisle-e4"
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
        execution_id="ex-e4",
        provider_name="gemini",
        model_name="m1",
    )
    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A",
        status=AisleStatus.QUEUED,
        created_at=now,
        updated_at=now,
    )
    ac = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])
    p = _V3HybridRunParams(
        base_path=tmp_path,
        job_id=job_id,
        job=job,
        aisle=aisle,
        aisle_id=aisle_id,
        run_dir=tmp_path / job_id / RUN_ID,
        settings=MagicMock(),
        log=logging.getLogger("e4-abort"),
        pipeline_video_path="",
        job_input=JobInput(
            video_path="",
            mode="hybrid",
            input_type="photos",
            metadata={"inventory_id": "inv-1", "aisle_id": aisle_id},
        ),
        analysis_context=ac,
        execution_observer=lambda *a, **k: None,
        cancellation_checkpoint=lambda *a, **k: None,
    )

    job_repo = InMemoryJobRepo()
    job_repo.save(job)
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = InMemoryInventoryRepo()
    noop = NoopRepo()

    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=noop,
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        supplier_reference_image_repo=noop,
        artifact_store=None,
        **memory_executor_persist_kwargs(raw_label_repo=noop),
    )
    spy_runner = MagicMock()
    executor._pipeline_runner = spy_runner
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state

    bad = SupplierPromptResolution(
        inventory_id="inv-1",
        aisle_id=aisle_id,
        client_id="c1",
        client_supplier_id="s1",
        provider_name="gemini",
        model_name="m1",
        supplier_prompt_config_id=None,
        supplier_prompt_config_version=None,
        editable_instructions=None,
        fallback_used=False,
        fallback_reason=None,
        resolution_status="error",
        warnings=(),
        error_code="CLIENT_SUPPLIER_OWNERSHIP_MISMATCH",
    )
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = bad
    executor._supplier_prompt_resolver = mock_resolver

    assert executor._v3_hybrid_run_and_load_report(p) is None
    spy_state.fail_job_and_aisle.assert_called_once()
    assert "CLIENT_SUPPLIER_OWNERSHIP_MISMATCH" in spy_state.fail_job_and_aisle.call_args[0][2]
    spy_runner.run_hybrid_pipeline.assert_not_called()
