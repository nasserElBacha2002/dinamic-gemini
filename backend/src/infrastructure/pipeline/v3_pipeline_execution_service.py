"""
V3 hybrid pipeline execution — Phase 6 extraction from :class:`V3JobExecutor`.

Runs the hybrid pipeline, resolves supplier prompts, and loads ``hybrid_report.json``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.services.job_engine_params import coerce_prompt_parity_mode
from src.application.services.supplier_prompt_resolver import (
    SupplierPromptResolution,
    SupplierPromptResolutionErrorCode,
    SupplierPromptResolver,
)
from src.config import Settings
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    V3ProcessAislePipelineRunner,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.execution_log import read_last_stage_error
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, PipelineRunResult

logger = logging.getLogger(__name__)

RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


def supplier_prompt_resolution_failure_message(resolution: SupplierPromptResolution) -> str:
    """Human-readable job failure text for observability (worker logs + job row)."""
    code = resolution.error_code or "UNKNOWN"
    base = (
        f"Supplier prompt resolution failed ({code}) "
        f"inventory_id={resolution.inventory_id} aisle_id={resolution.aisle_id}"
    )
    if code == SupplierPromptResolutionErrorCode.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG:
        return (
            f"{base}: No active supplier_prompt_configs for client_supplier_id="
            f"{resolution.client_supplier_id!r} provider={resolution.provider_name!r} "
            f"model={resolution.model_name!r}. Configure and activate a supplier prompt "
            f"(Client → Supplier → Instrucciones / prompts)."
        )
    return f"{base}."


@dataclass(frozen=True)
class V3PipelineExecutionRequest:
    """Arguments for hybrid pipeline invocation and report load."""

    base_path: Path
    job_id: str
    job: Job
    aisle: Aisle
    aisle_id: str
    run_dir: Path
    settings: Settings
    log: logging.Logger
    pipeline_video_path: str
    job_input: JobInput
    analysis_context: AnalysisContext
    execution_observer: Callable[
        [str, str | None, str, dict[str, Any] | None],
        None,
    ]
    cancellation_checkpoint: Callable[[str, str | None, str], None]
    # When set (GLOBAL_BATCH), use immutable job-snapshot instructions instead of live resolve.
    supplier_prompt_resolution_override: SupplierPromptResolution | None = None


@dataclass(frozen=True)
class V3PipelineExecutionResult:
    """Successful hybrid pipeline run with loaded report."""

    report: dict[str, Any]
    pipeline_result: PipelineRunResult
    report_path: Path


class V3PipelineExecutionService:
    """Run hybrid pipeline and load ``hybrid_report.json`` for v3 process_aisle jobs."""

    def __init__(
        self,
        *,
        state_service: V3JobExecutionStateService,
        pipeline_runner: V3ProcessAislePipelineRunner,
        supplier_prompt_resolver: SupplierPromptResolver | None = None,
    ) -> None:
        self._state = state_service
        self._pipeline_runner = pipeline_runner
        self._supplier_prompt_resolver = supplier_prompt_resolver

    @staticmethod
    def _create_pipeline() -> HybridInventoryPipeline:
        return HybridInventoryPipeline()

    def run(self, req: V3PipelineExecutionRequest) -> V3PipelineExecutionResult | None:
        """Run hybrid pipeline and load report. None => failure handled (caller returns True)."""
        req.cancellation_checkpoint(
            "Pipeline",
            "pre_pipeline",
            "Job canceled before pipeline execution",
        )
        logger.info(
            "v3 executor start: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
            req.job_id,
            req.job.job_type,
            req.job.target_type,
            req.job.target_id,
            req.aisle.inventory_id,
            req.aisle_id,
        )
        pipeline = self._create_pipeline()
        pipeline_provider_name = (req.job.provider_name or "").strip() or None
        job_model = (req.job.model_name or "").strip() or None
        job_prompt = (req.job.prompt_key or "").strip() or None
        job_prompt_version = (req.job.prompt_version or "").strip() or None
        job_prompt_parity_mode = coerce_prompt_parity_mode(req.job.engine_params_json)
        supplier_prompt_resolution = req.supplier_prompt_resolution_override
        spr = self._supplier_prompt_resolver
        if supplier_prompt_resolution is None and spr is not None:
            supplier_prompt_resolution = spr.resolve(
                inventory_id=req.aisle.inventory_id,
                aisle_id=req.aisle_id,
                provider_name=pipeline_provider_name,
                model_name=job_model,
                allow_missing_supplier_prompt_fallback=bool(
                    getattr(req.settings, "v3_allow_missing_supplier_prompt_fallback", False)
                ),
            )
            if supplier_prompt_resolution.resolution_status == "error":
                err_code = supplier_prompt_resolution.error_code or "UNKNOWN"
                logger.error(
                    "v3 supplier prompt resolution error job_id=%s inventory_id=%s aisle_id=%s code=%s",
                    req.job_id,
                    req.aisle.inventory_id,
                    req.aisle_id,
                    err_code,
                )
                self._state.fail_job_and_aisle(
                    req.job_id,
                    req.aisle,
                    supplier_prompt_resolution_failure_message(supplier_prompt_resolution),
                )
                return None
        elif (
            supplier_prompt_resolution is not None
            and supplier_prompt_resolution.resolution_status == "error"
        ):
            self._state.fail_job_and_aisle(
                req.job_id,
                req.aisle,
                supplier_prompt_resolution_failure_message(supplier_prompt_resolution),
            )
            return None
        result = self._pipeline_runner.run_hybrid_pipeline(
            pipeline=pipeline,
            video_path=req.pipeline_video_path,
            job_id=req.job_id,
            base_path=req.base_path,
            run_id=RUN_ID,
            settings=req.settings,
            job_input=req.job_input,
            analysis_context=req.analysis_context,
            log=req.log,
            execution_observer=req.execution_observer,
            cancellation_checkpoint=req.cancellation_checkpoint,
            pipeline_provider_name=pipeline_provider_name,
            job_model_name=job_model,
            job_prompt_key=job_prompt,
            job_prompt_version=job_prompt_version,
            job_prompt_parity_mode=job_prompt_parity_mode,
            supplier_prompt_resolution=supplier_prompt_resolution,
        )
        logger.info(
            "v3 executor finished: job_id=%s exit_code=%s inventory_id=%s aisle_id=%s",
            req.job_id,
            result.exit_code,
            req.aisle.inventory_id,
            req.aisle_id,
        )
        if result.exit_code != 0:
            last_error = read_last_stage_error(req.run_dir)
            if last_error:
                error_message = f"{last_error} (exit code {result.exit_code})"
            else:
                error_message = f"Pipeline exited with code {result.exit_code}"
            self._state.fail_job_and_aisle(req.job_id, req.aisle, error_message)
            return None

        req.cancellation_checkpoint(
            "Pipeline",
            "post_pipeline",
            "Job canceled after pipeline execution",
        )

        report_path = req.run_dir / "hybrid_report.json"
        if not report_path.exists():
            self._state.fail_job_and_aisle(
                req.job_id, req.aisle, "Reporting error: Pipeline did not produce hybrid_report.json"
            )
            return None

        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        return V3PipelineExecutionResult(
            report=report,
            pipeline_result=result,
            report_path=report_path,
        )
