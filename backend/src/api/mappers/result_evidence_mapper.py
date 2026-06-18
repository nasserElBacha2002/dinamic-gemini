"""Map Phase 4.8 read models to API response schemas."""

from __future__ import annotations

from src.api.schemas.result_evidence_schemas import (
    JobTraceabilityEntityResponse,
    JobTraceabilityEnvelopeResponse,
    JobTraceabilityResponse,
    ResultEvidenceViewResponse,
    TraceabilityArtifactMetadataResponse,
    TraceabilitySummaryResponse,
)
from src.application.services.result_evidence_query_service import (
    JobTraceabilityReadModel,
    ResultEvidenceViewModel,
    TraceabilityArtifactReadModel,
)


def result_evidence_view_to_response(model: ResultEvidenceViewModel) -> ResultEvidenceViewResponse:
    return ResultEvidenceViewResponse(
        displayable=model.displayable,
        traceability_status=model.traceability_status,
        traceability_warning=model.traceability_warning,
        role=model.role,
        source_image_id=model.source_image_id,
        source_asset_id=model.source_asset_id,
        resolved_manifest_entry_id=model.resolved_manifest_entry_id,
        raw_manifest_entry_id=model.raw_manifest_entry_id,
        raw_source_image_id=model.raw_source_image_id,
        image_url=model.image_url,
        thumbnail_url=model.thumbnail_url,
        image_access_status=model.image_access_status,
        source_kind=model.source_kind,
        provider=model.provider,
        model_name=model.model_name,
    )


def artifact_read_model_to_response(
    model: TraceabilityArtifactReadModel | None,
) -> TraceabilityArtifactMetadataResponse | None:
    if model is None:
        return None
    return TraceabilityArtifactMetadataResponse(
        kind=model.kind,
        published=model.published,
        required=model.required,
        status=model.status,
        storage_key=model.storage_key,
        content_hash=model.content_hash,
        size_bytes=model.size_bytes,
        published_at=model.published_at,
    )


def job_traceability_to_response(model: JobTraceabilityReadModel) -> JobTraceabilityResponse:
    artifact = artifact_read_model_to_response(model.artifact)
    summary = TraceabilitySummaryResponse(**model.summary)
    return JobTraceabilityResponse(
        job_id=model.job_id,
        inventory_id=model.inventory_id,
        aisle_id=model.aisle_id,
        traceability=JobTraceabilityEnvelopeResponse(
            status=model.traceability_status,
            artifact=artifact,
            summary=summary,
        ),
        entities=[
            JobTraceabilityEntityResponse(
                position_id=entity.get("position_id"),
                entity_uid=entity.get("entity_uid"),
                model_entity_id=entity.get("model_entity_id"),
                evidence=result_evidence_view_to_response(entity["evidence"]),
            )
            for entity in model.entities
        ],
    )
