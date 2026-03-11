"""
EntityResolutionStage — parse analysis payload and run entity validation/transformation (v2.3.C).

Parses v2.1 analysis JSON into entities, then applies existing deterministic ordering,
enrichment, and derived-field logic (sort, resolve_pallet_id, assign_count_status,
compute_entity_quality_score). Epic 3.1.B: applies traceability validation using
job image IDs from the manifest when input_type is photos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.decision.count_status import assign_count_status
from src.decision.entity_order import sort_entities_deterministically
from src.decision.pallet_id import resolve_pallet_id
from src.decision.quality_score import compute_entity_quality_score
from src.domain.entity import Entity
from src.domain.traceability import apply_traceability_validation
from src.jobs.image_identity import load_job_images_from_manifest
from src.parsing.global_analysis_parser import GlobalAnalysisParseError, parse_entities
from src.pipeline.stages.analysis_stage import AnalysisStageResult
from src.pipeline.context.run_context import RunContext


@dataclass
class ResolvedEntities:
    """Output of EntityResolutionStage: entities with count_status, pallet_id, quality score set."""

    entities: List[Entity]


class EntityResolutionStage:
    """
    Stage: parse v2.1 JSON into entities; apply deterministic ordering and enrichment.

    Runs parse_entities, then existing business logic: sort, resolve_pallet_id,
    assign_count_status, compute_entity_quality_score. All derived fields and ordering
    rules are preserved as in the pre-Stage-C pipeline.
    """

    def run(self, context: RunContext, data: AnalysisStageResult) -> ResolvedEntities:
        """
        Parse analysis payload, validate, and run resolution/status/quality logic.

        Raises:
            GlobalAnalysisParseError: When parsing or validation fails (caller maps to exit code 1).
        """
        job_id = context.job_id
        logger = context.logger

        entities = parse_entities(data.parsed_json, job_id=job_id)
        logger.info("Entidades detectadas (hybrid v2.1): %d", len(entities))

        # Epic 3.1.B: validate source_image_id against job images when input is photos.
        # Reuse same path resolution as PhotosFrameSource so manifest location is consistent.
        # When manifest is missing or not photos, valid_image_ids stays empty → status "unvalidated" for present refs (no false invalid).
        valid_image_ids: frozenset[str] = frozenset()
        job_input = getattr(context, "job_input", None)
        if job_input and getattr(job_input, "input_type", "") == "photos":
            from src.frames.sources.photos_source import _resolve_manifest_path

            run_dir = context.run_dir
            manifest_path = _resolve_manifest_path(run_dir, job_input)
            photos_dir_rel = (getattr(job_input, "photos_dir", None) or "").strip() or "run/input_photos"
            job_images = load_job_images_from_manifest(manifest_path, photos_dir_rel)
            valid_image_ids = frozenset(img.image_id for img in job_images)
        apply_traceability_validation(entities, valid_image_ids)

        sort_entities_deterministically(entities)
        resolve_pallet_id(entities)
        for e in entities:
            assign_count_status(e)
        for e in entities:
            compute_entity_quality_score(e)

        return ResolvedEntities(entities=entities)
