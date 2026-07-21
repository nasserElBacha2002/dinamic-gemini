"""Hybrid batch analyzer for GLOBAL_BATCH external fallback.

Runs :class:`V3PipelineExecutionService` for an ordered asset subset and returns
``GlobalEntityResponseV21`` entities **without** PersistAisleResult delete-all.
"""

from __future__ import annotations

import copy
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.services.image_processing.external_fallback_mode import (
    GLOBAL_FALLBACK_PROMPT_KEY,
    GLOBAL_FALLBACK_SCHEMA_VERSION,
)
from src.application.services.image_processing.global_external_fallback_coordinator import (
    GlobalFallbackBatchAnalysisResult,
)
from src.application.services.image_processing.global_fallback_batching import (
    GlobalFallbackBatchSlice,
)
from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.config import Settings
from src.domain.assets.entities import SourceAsset
from src.infrastructure.pipeline.v3_pipeline_execution_service import (
    V3PipelineExecutionRequest,
    V3PipelineExecutionService,
)
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    V3ProcessAislePipelineRunner,
)
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.stages.frame_acquisition_stage import HYBRID_MAX_FRAMES_LOAD_CAP

logger = logging.getLogger(__name__)


def supplier_prompt_resolution_from_fallback_snapshot(
    *,
    inventory_id: str,
    aisle_id: str,
    snapshot: Any,
) -> SupplierPromptResolution | None:
    """Build a resolved SupplierPromptResolution from the immutable job snapshot."""
    sp = getattr(snapshot, "supplier_prompt", None)
    if not isinstance(sp, dict):
        return None
    content = str(sp.get("content") or sp.get("instructions_text") or "").strip()
    if not content:
        return None
    return SupplierPromptResolution(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        client_id=None,
        client_supplier_id=str(sp.get("supplier_id") or getattr(snapshot, "supplier_id", None) or "")
        or None,
        provider_name=str(getattr(snapshot, "provider", "") or "") or None,
        model_name=str(getattr(snapshot, "model", "") or "") or None,
        supplier_prompt_config_id=str(sp.get("prompt_id") or "") or None,
        supplier_prompt_config_version=int(sp.get("prompt_version") or 1)
        if sp.get("prompt_version") is not None
        else 1,
        editable_instructions=content,
        fallback_used=False,
        fallback_reason=None,
        resolution_status="resolved",
        warnings=("from_job_snapshot",),
    )


@dataclass
class HybridGlobalFallbackBatchAnalyzer:
    """Adapter: reusable hybrid pipeline → GLOBAL_BATCH analysis result."""

    pipeline_execution_service: V3PipelineExecutionService
    pipeline_runner: V3ProcessAislePipelineRunner
    settings: Settings
    base_path: Path
    v3_base: Path
    job_dir: Path
    run_dir: Path
    inventory_repo: Any
    log: logging.Logger
    execution_observer: Any
    cancellation_checkpoint: Any
    legacy_local_read_enabled: bool = False

    def analyze_batch(
        self,
        *,
        job: Any,
        aisle: Any,
        assets: Sequence[SourceAsset],
        batch: GlobalFallbackBatchSlice,
        snapshot: Any,
        prompt_fingerprint: str,
    ) -> GlobalFallbackBatchAnalysisResult:
        started = time.monotonic()
        if len(assets) > HYBRID_MAX_FRAMES_LOAD_CAP:
            return GlobalFallbackBatchAnalysisResult(
                ok=False,
                error_code="FALLBACK_BATCH_TOO_LARGE",
                error_message=(
                    f"batch size {len(assets)} exceeds HYBRID_MAX_FRAMES_LOAD_CAP="
                    f"{HYBRID_MAX_FRAMES_LOAD_CAP}"
                ),
            )

        # Snapshot-bound provider/model/prompt — do not mutate the durable job row.
        job_view = copy.copy(job)
        job_view.provider_name = str(getattr(snapshot, "provider", "") or "").strip() or None
        job_view.model_name = (
            str(getattr(snapshot, "model", "") or "").strip() or None
        )
        job_view.prompt_key = GLOBAL_FALLBACK_PROMPT_KEY
        job_view.prompt_version = GLOBAL_FALLBACK_SCHEMA_VERSION

        try:
            inv = self.inventory_repo.get_by_id(aisle.inventory_id)
            inv_client = (inv.client_id or "").strip() if inv is not None else ""
            analysis_context: AnalysisContext = self.pipeline_runner.build_analysis_context(
                aisle,
                inventory_client_id=inv_client or None,
            )
            job_input, video_path = self.pipeline_runner.build_pipeline_input(
                list(assets),
                self.v3_base,
                self.job_dir,
                job.id,
                analysis_context=analysis_context,
                aisle=aisle,
                run_id=f"global_fallback_b{batch.batch_index}",
                legacy_local_read_enabled=self.legacy_local_read_enabled,
            )
        except Exception as exc:
            logger.exception(
                "global_fallback.build_input_failed job_id=%s batch=%s",
                job.id,
                batch.batch_index,
            )
            return GlobalFallbackBatchAnalysisResult(
                ok=False,
                error_code="FALLBACK_BATCH_INPUT_FAILED",
                error_message=str(exc)[:500],
            )

        batch_run_dir = self.run_dir / f"global_fallback_batch_{batch.batch_index}"
        batch_run_dir.mkdir(parents=True, exist_ok=True)

        pipeline_out = self.pipeline_execution_service.run(
            V3PipelineExecutionRequest(
                base_path=self.base_path,
                job_id=job.id,
                job=job_view,
                aisle=aisle,
                aisle_id=aisle.id,
                run_dir=batch_run_dir,
                settings=self.settings,
                log=self.log,
                pipeline_video_path=video_path or "",
                job_input=job_input,
                analysis_context=analysis_context,
                execution_observer=self.execution_observer,
                cancellation_checkpoint=self.cancellation_checkpoint,
                supplier_prompt_resolution_override=supplier_prompt_resolution_from_fallback_snapshot(
                    inventory_id=aisle.inventory_id,
                    aisle_id=aisle.id,
                    snapshot=snapshot,
                ),
            )
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        if pipeline_out is None:
            return GlobalFallbackBatchAnalysisResult(
                ok=False,
                error_code="FALLBACK_BATCH_PIPELINE_FAILED",
                error_message="hybrid pipeline returned None",
                duration_ms=duration_ms,
            )

        report = pipeline_out.report if isinstance(pipeline_out.report, dict) else {}
        entities = report.get("entities")
        if not isinstance(entities, list):
            # Contract must be GlobalEntityResponseV21 (entities list).
            return GlobalFallbackBatchAnalysisResult(
                ok=False,
                error_code="EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
                error_message=(
                    "GLOBAL_BATCH requires GlobalEntityResponseV21 with entities[]; "
                    f"got keys={sorted(report.keys())[:20]}"
                ),
                schema_version=str(report.get("schema_version") or ""),
                raw_report=report,
                duration_ms=duration_ms,
            )

        schema_version = str(
            report.get("schema_version") or GLOBAL_FALLBACK_SCHEMA_VERSION
        ).strip()
        cost = None
        prompt_tokens = None
        response_tokens = None
        meta = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        if isinstance(meta, dict):
            cost = meta.get("estimated_cost") or meta.get("cost")
            prompt_tokens = meta.get("prompt_tokens")
            response_tokens = meta.get("response_tokens") or meta.get("completion_tokens")

        return GlobalFallbackBatchAnalysisResult(
            ok=True,
            entities=[e for e in entities if isinstance(e, dict)],
            schema_version=schema_version,
            prompt_key=GLOBAL_FALLBACK_PROMPT_KEY,
            prompt_fingerprint=prompt_fingerprint,
            provider=job_view.provider_name,
            model=job_view.model_name,
            estimated_cost=float(cost) if isinstance(cost, (int, float)) else None,
            prompt_tokens=int(prompt_tokens) if isinstance(prompt_tokens, int) else None,
            response_tokens=int(response_tokens)
            if isinstance(response_tokens, int)
            else None,
            raw_report=report,
            duration_ms=duration_ms,
        )
