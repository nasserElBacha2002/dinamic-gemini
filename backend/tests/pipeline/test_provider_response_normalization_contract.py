"""Phase 4.5 — provider response normalization fixtures (Gemini, OpenAI, Claude)."""

from __future__ import annotations

import copy

import pytest

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
    manifest_composition_projection,
)
from src.domain.manifest_evidence_resolution import apply_evidence_resolution_to_entities
from src.domain.traceability import TraceabilityStatus, apply_traceability_validation
from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.parsing.global_analysis_parser import parse_entities


def _manifest() -> ExecutionImageManifest:
    return ExecutionImageManifest(
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
                storage_reference="a.jpg",
            ),
        ),
        excluded_entries=(),
    )


def _run_provider(provider: str, entity: dict) -> list:
    payload = normalize_llm_response(
        {
            "total_entities_detected": 1,
            "entities": [copy.deepcopy(entity)],
        },
        provider=provider,
    )
    entities = parse_entities(payload, job_id="job-1")
    composition = manifest_composition_projection(_manifest())
    apply_evidence_resolution_to_entities(entities, composition=composition)
    apply_traceability_validation(
        entities,
        frozenset({"asset-1"}),
        reference_image_ids=frozenset({"ref-1"}),
        sent_metadata_available=True,
    )
    return entities


@pytest.mark.parametrize("provider", ["gemini", "openai", "claude"])
def test_provider_manifest_entry_id_valid(provider: str) -> None:
    entities = _run_provider(
        provider,
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "has_boxes": True,
            "confidence": 0.9,
            "manifest_entry_id": "IMG_001",
        },
    )
    assert entities[0].traceability_status == TraceabilityStatus.VALID.value
    assert entities[0].source_image_id == "asset-1"


@pytest.mark.parametrize("provider", ["gemini", "openai", "claude"])
def test_provider_legacy_source_image_id_valid(provider: str) -> None:
    entities = _run_provider(
        provider,
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "has_boxes": True,
            "confidence": 0.9,
            "source_image_id": "asset-1",
        },
    )
    assert entities[0].traceability_status == TraceabilityStatus.VALID.value


@pytest.mark.parametrize("provider", ["gemini", "openai", "claude"])
def test_provider_ref_invalid(provider: str) -> None:
    entities = _run_provider(
        provider,
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "has_boxes": True,
            "confidence": 0.9,
            "manifest_entry_id": "REF_001",
        },
    )
    assert entities[0].traceability_status == TraceabilityStatus.INVALID.value
    assert entities[0].source_image_id is None


@pytest.mark.parametrize("provider", ["gemini", "openai", "claude"])
def test_provider_conflict_invalid(provider: str) -> None:
    entities = _run_provider(
        provider,
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "has_boxes": True,
            "confidence": 0.9,
            "manifest_entry_id": "IMG_001",
            "source_image_id": "ref-1",
        },
    )
    assert entities[0].traceability_status == TraceabilityStatus.INVALID.value
