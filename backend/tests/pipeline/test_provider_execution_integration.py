"""Phase 4.4 — Integration: manifest → request → evidence normalization → traceability."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.domain.entity import Entity
from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.manifest_evidence_resolution import normalize_entity_evidence_identifiers
from src.domain.prompt_image_projection import COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION
from src.domain.traceability import (
    TraceabilityStatus,
    apply_traceability_validation,
    extract_reference_image_ids,
    extract_sent_image_ids_from_composition,
)
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.services.execution_image_manifest_payload import (
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_request import build_provider_execution_request
from src.pipeline.services.provider_payload_serialization import serialize_provider_images


def _pipeline_fixtures():
    manifest = ExecutionImageManifest(
        job_id="job-1",
        entries=(
            ExecutionImageEntry(
                manifest_entry_id="REF_001",
                source_asset_id="ref-1",
                source_image_id="ref-1",
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=1,
                storage_reference="ref.jpg",
            ),
            ExecutionImageEntry(
                manifest_entry_id="IMG_001",
                source_asset_id="asset-1",
                source_image_id="asset-1",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=2,
                storage_reference="a1.jpg",
            ),
        ),
        excluded_entries=(),
    )
    paths = [Path("a1.jpg")]
    refs = ["asset-1"]
    nds = [np.zeros((2, 2, 3), dtype=np.uint8)]
    path_by, nd_by = primary_lookups_from_acquired(paths, refs, nds)
    bound = bind_provider_payload_from_manifest(
        manifest,
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id={"ref-1": object()},
    )
    _, prompt_projection = enrich_prompt_with_execution_manifest("p", manifest)
    req = build_provider_execution_request(
        job_id="job-1",
        prompt="p",
        manifest=manifest,
        bound_payload=bound,
    )
    serialized = serialize_provider_images(req, prompt_projection=prompt_projection)
    composition = manifest_composition_projection(manifest)
    composition[COMPOSITION_KEY_PROMPT_IMAGE_PROJECTION] = prompt_projection.to_dict()
    return manifest, composition, serialized


def _entity_from_response(evidence_field: str, evidence_value: str) -> list[Entity]:
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                evidence_field: evidence_value,
            }
        ],
    }
    return parse_entities(payload, job_id="job-1")


def test_img_001_resolves_to_valid_traceability() -> None:
    _, composition, _ = _pipeline_fixtures()
    entities = _entity_from_response("manifest_entry_id", "IMG_001")
    normalize_entity_evidence_identifiers(entities, composition=composition)
    sent = extract_sent_image_ids_from_composition(composition)
    refs = extract_reference_image_ids(composition)
    apply_traceability_validation(
        entities,
        sent or frozenset(),
        reference_image_ids=refs,
        sent_metadata_available=True,
    )
    assert entities[0].source_image_id == "asset-1"
    assert entities[0].traceability_status == TraceabilityStatus.VALID.value


def test_ref_001_is_invalid() -> None:
    _, composition, _ = _pipeline_fixtures()
    entities = _entity_from_response("manifest_entry_id", "REF_001")
    normalize_entity_evidence_identifiers(entities, composition=composition)
    sent = extract_sent_image_ids_from_composition(composition)
    refs = extract_reference_image_ids(composition)
    apply_traceability_validation(
        entities,
        sent or frozenset(),
        reference_image_ids=refs,
        sent_metadata_available=True,
    )
    assert entities[0].traceability_status == TraceabilityStatus.INVALID.value


def test_unknown_img_999_is_invalid() -> None:
    _, composition, _ = _pipeline_fixtures()
    entities = _entity_from_response("manifest_entry_id", "IMG_999")
    normalize_entity_evidence_identifiers(entities, composition=composition)
    sent = extract_sent_image_ids_from_composition(composition)
    apply_traceability_validation(
        entities,
        sent or frozenset(),
        sent_metadata_available=True,
    )
    assert entities[0].traceability_status == TraceabilityStatus.INVALID.value


def test_conflicting_manifest_and_legacy_ids_invalid() -> None:
    _, composition, _ = _pipeline_fixtures()
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "manifest_entry_id": "IMG_001",
                "source_image_id": "ref-1",
            }
        ],
    }
    entities = parse_entities(payload, job_id="job-1")
    normalize_entity_evidence_identifiers(entities, composition=composition)
    assert entities[0].traceability_status == TraceabilityStatus.INVALID.value
