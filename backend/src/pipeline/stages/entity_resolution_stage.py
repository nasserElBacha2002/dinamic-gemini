"""
EntityResolutionStage — parse analysis payload and run entity validation/transformation (v2.3.C).

Parses v2.1 analysis JSON into entities, then applies existing deterministic ordering,
enrichment, and derived-field logic (sort, resolve_pallet_id, assign_count_status,
compute_entity_quality_score). Epic 3.1.B / Phase 4.2: validates source_image_id against
the final primary frames sent to the model (never the full preliminary manifest).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.decision.count_status import assign_count_status
from src.decision.entity_order import sort_entities_deterministically
from src.decision.pallet_id import resolve_pallet_id
from src.decision.quality_score import compute_entity_quality_score
from src.domain.entity import Entity
from src.domain.traceability import (
    apply_traceability_validation,
    extract_reference_image_ids,
    extract_sent_image_ids_from_composition,
    log_traceability_validation_summary,
)
from src.jobs.image_identity import load_job_images_from_manifest
from src.jobs.photos_paths import photos_dir_relative_for_manifest, resolve_manifest_path
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.analysis_stage import AnalysisStageResult


@dataclass
class ResolvedEntities:
    """Output of EntityResolutionStage: entities with count_status, pallet_id, quality score set."""

    entities: list[Entity]


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

        composition = data.prompt_composition or {}
        provider_metadata = data.provider_metadata or {}
        reference_image_ids = extract_reference_image_ids(
            composition, provider_metadata=provider_metadata
        )

        valid_image_ids: frozenset[str] = frozenset()
        manifest_image_ids: frozenset[str] = frozenset()
        sent_metadata_available = False
        job_input = getattr(context, "job_input", None)
        if job_input and getattr(job_input, "input_type", "") == "photos":
            run_dir = context.run_dir
            manifest_path = resolve_manifest_path(run_dir, job_input)
            photos_dir_rel = photos_dir_relative_for_manifest(job_input)
            job_images = load_job_images_from_manifest(manifest_path, photos_dir_rel)
            manifest_image_ids = frozenset(img.image_id for img in job_images)
            sent_ids = extract_sent_image_ids_from_composition(composition)
            if sent_ids is not None:
                valid_image_ids = sent_ids
                sent_metadata_available = True
            else:
                logger.warning(
                    "traceability_validation missing frames_sent_ids job_id=%s; "
                    "entities with source_image_id will be UNVALIDATED",
                    job_id,
                )

        apply_traceability_validation(
            entities,
            valid_image_ids,
            manifest_image_ids=manifest_image_ids if manifest_image_ids else None,
            reference_image_ids=reference_image_ids if reference_image_ids else None,
            sent_metadata_available=sent_metadata_available,
        )
        log_traceability_validation_summary(
            job_id=job_id,
            entities=entities,
            valid_image_ids=valid_image_ids,
            sent_metadata_available=sent_metadata_available,
            provider=data.provider_name,
        )

        sort_entities_deterministically(entities)
        resolve_pallet_id(entities)
        for e in entities:
            assign_count_status(e)
        for e in entities:
            compute_entity_quality_score(e)

        return ResolvedEntities(entities=entities)
