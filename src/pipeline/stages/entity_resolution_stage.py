"""
EntityResolutionStage — parse analysis payload and run entity validation/transformation (v2.3.C).

Parses v2.1 analysis JSON into entities, then applies existing deterministic ordering,
enrichment, and derived-field logic (sort, resolve_pallet_id, assign_count_status,
compute_entity_quality_score). Preserves current business rules; no schema or behavior change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.decision.count_status import assign_count_status
from src.decision.entity_order import sort_entities_deterministically
from src.decision.pallet_id import resolve_pallet_id
from src.decision.quality_score import compute_entity_quality_score
from src.domain.entity import Entity
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

        sort_entities_deterministically(entities)
        resolve_pallet_id(entities)
        for e in entities:
            assign_count_status(e)
        for e in entities:
            compute_entity_quality_score(e)

        return ResolvedEntities(entities=entities)
