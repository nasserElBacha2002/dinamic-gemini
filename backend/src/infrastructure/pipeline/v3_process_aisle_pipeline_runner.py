"""
Pipeline input construction and hybrid pipeline invocation for v3 ``process_aisle`` jobs.

Phase 2: extracted from :class:`~src.infrastructure.pipeline.v3_job_executor.V3JobExecutor` so provider
and pipeline boundaries stay out of the top-level executor. The executor still constructs
:class:`~src.pipeline.hybrid_inventory_pipeline.HybridInventoryPipeline` where tests patch it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.application.ports.repositories import InventoryVisualReferenceRepository
from src.application.services.aisle_analysis_context_builder import AisleAnalysisContextBuilder
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAssetType
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
    analysis_context_to_dict,
)
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, PipelineRunResult
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
)
from src.pipeline.run_metadata import build_visual_reference_context
from src.infrastructure.pipeline.input_artifact_resolver import WorkerInputArtifactResolver

logger = logging.getLogger(__name__)


def visual_reference_failure_metadata(
    analysis_context: Optional[AnalysisContext],
    error_message: str,
) -> Dict[str, Any]:
    # No provider run: explicit zero consumption so the block does not list context reference_ids
    # as "resolved" for this failed job (resolution never reached the provider).
    block = build_visual_reference_context(
        analysis_context,
        provider_metadata={
            PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: False,
            PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 0,
        },
    )
    block["resolution_error"] = error_message[:2048] if len(error_message) > 2048 else error_message
    block["resolution_stage"] = "input_artifact_resolution"
    return block


def resolve_visual_reference_paths(
    ctx: AnalysisContext,
    *,
    resolver: WorkerInputArtifactResolver,
    references_by_id: dict[str, InventoryVisualReference],
    target_dir: Path,
) -> AnalysisContext:
    """Return AnalysisContext with provider/local resolved temp paths for visual references."""
    if not ctx.visual_references:
        return ctx
    resolved_refs = []
    for i, ref in enumerate(ctx.visual_references):
        ext = Path(ref.source_path or "").suffix or ".jpg"
        temp_ref = target_dir / f"{i:04d}_{ref.reference_id}{ext}"
        resolved_local = resolver.resolve_visual_reference(
            ref.reference_id,
            reference_record=references_by_id.get(ref.reference_id),
            source_path=ref.source_path,
            target_path=temp_ref,
        )
        resolved_refs.append(
            VisualReferenceContext(
                reference_id=ref.reference_id,
                source_path=ref.source_path,
                mime_type=ref.mime_type,
                role=ref.role,
                created_at=ref.created_at,
                resolved_path=str(resolved_local),
            )
        )
    return AnalysisContext(
        primary_evidence=ctx.primary_evidence,
        visual_references=resolved_refs,
        instructions=ctx.instructions,
        metadata=ctx.metadata,
    )


class V3ProcessAislePipelineRunner:
    """Builds analysis context + JobInput and runs :class:`HybridInventoryPipeline`."""

    def __init__(
        self,
        *,
        inventory_visual_reference_repo: InventoryVisualReferenceRepository,
        artifact_store: Any,
        context_builder: AisleAnalysisContextBuilder,
    ) -> None:
        self._inventory_visual_reference_repo = inventory_visual_reference_repo
        self._artifact_store = artifact_store
        self._context_builder = context_builder

    def build_analysis_context(self, aisle: Aisle) -> AnalysisContext:
        """Construct AnalysisContext for this aisle's inventory. Primary evidence left empty in v3.2.4."""
        inventory_id = aisle.inventory_id
        primary: list[AnalysisImage] = []
        return self._context_builder.build(
            inventory_id=inventory_id,
            primary_evidence=primary,
            metadata=None,
        )

    def build_pipeline_input(
        self,
        assets: list,
        v3_base: Path,
        job_dir: Path,
        job_id: str,
        *,
        analysis_context: AnalysisContext,
        inventory_id: str,
        run_id: str,
        legacy_local_read_enabled: bool,
    ) -> Tuple[JobInput, str]:
        """Return (JobInput, video_path). video_path used as first arg to process_video."""
        input_assets_dir = job_dir / run_id / "input_assets"
        visual_refs_dir = job_dir / run_id / "visual_references"
        resolver = WorkerInputArtifactResolver(
            self._artifact_store,
            legacy_base=v3_base,
            legacy_local_read_enabled=legacy_local_read_enabled,
        )
        single_video = (
            len(assets) == 1
            and getattr(assets[0], "type", None) == SourceAssetType.VIDEO
        )
        # Validate/classify asset shape first so we do not resolve visual references for unsupported sets.
        has_video_asset = any(getattr(a, "type", None) == SourceAssetType.VIDEO for a in assets)
        if has_video_asset and not single_video:
            raise ValueError(
                "Invalid aisle assets: videos must be uploaded/processed as a single video asset; "
                "mixed or multi-video sets are not supported in photos normalization flow."
            )
        refs = self._inventory_visual_reference_repo.list_by_inventory(inventory_id)
        refs_by_id = {r.id: r for r in refs}
        resolved_ctx = resolve_visual_reference_paths(
            analysis_context,
            resolver=resolver,
            references_by_id=refs_by_id,
            target_dir=visual_refs_dir,
        )
        if single_video:
            asset = assets[0]
            ext = Path(asset.storage_path or "").suffix or ".mp4"
            target_video = input_assets_dir / f"0000_{asset.id}{ext}"
            full = resolver.resolve_source_asset(asset, target_video)
            video_path = str(full)
            return (
                JobInput(
                    video_path=video_path,
                    mode="hybrid",
                    input_type="video",
                    metadata={"analysis_context": analysis_context_to_dict(resolved_ctx)},
                ),
                video_path,
            )

        # Photos (or multiple assets): resolve to job_dir/input_photos, write manifest
        photos_dir = job_dir / "input_photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        photos_list = []
        for i, asset in enumerate(assets):
            ext = Path(asset.storage_path).suffix or ".jpg"
            stored = f"{i:04d}_{asset.id}{ext}"
            dst = photos_dir / stored
            resolver.resolve_source_asset(asset, dst)
            # Expose image_id (asset.id) so pipeline/LLM use it as source_image_id; enables reference-image view.
            photos_list.append({
                "index": i + 1,  # 1-based for load_job_images_from_manifest
                "image_id": asset.id,
                "original_filename": asset.original_filename,
                "stored_filename": stored,
            })

        manifest_path = job_dir / "input_manifest.json"
        manifest = {
            "input_type": "photos",
            "photos": photos_list,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Paths relative to job dir for pipeline
        return (
            JobInput(
                video_path="",
                mode="hybrid",
                input_type="photos",
                input_manifest_path="input_manifest.json",
                photos_dir="input_photos",
                metadata={"analysis_context": analysis_context_to_dict(resolved_ctx)},
            ),
            "",  # video_path empty for photos
        )

    def run_hybrid_pipeline(
        self,
        *,
        pipeline: HybridInventoryPipeline,
        video_path: str,
        job_id: str,
        base_path: Path,
        run_id: str,
        settings: Any,
        job_input: JobInput,
        analysis_context: AnalysisContext,
        log: logging.Logger,
        execution_observer: Any,
        cancellation_checkpoint: Any,
        pipeline_provider_name: Optional[str],
        job_model_name: Optional[str],
        job_prompt_key: Optional[str],
        job_prompt_version: Optional[str],
        job_prompt_parity_mode: Optional[str],
    ) -> PipelineRunResult:
        """Invoke ``process_video`` (hybrid mode) with the same arguments the executor used."""
        return pipeline.process_video(
            video_path,
            mode="hybrid",
            settings=settings,
            video_id=job_id,
            output_path=base_path,
            run_id=run_id,
            logger=log,
            progress_callback=None,
            job_input=job_input,
            analysis_context=analysis_context,
            execution_observer=execution_observer,
            cancellation_checkpoint=cancellation_checkpoint,
            pipeline_provider_name=pipeline_provider_name,
            job_model_name=job_model_name,
            job_prompt_key=job_prompt_key,
            job_prompt_version=job_prompt_version,
            job_prompt_parity_mode=job_prompt_parity_mode,
        )
