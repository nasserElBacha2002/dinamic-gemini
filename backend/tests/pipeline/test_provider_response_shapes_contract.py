"""Phase 4.5 corrections — provider-specific response shape fixtures."""

from __future__ import annotations

import copy
from typing import Any, Callable

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

_BASE_ENTITY: dict[str, Any] = {
    "entity_type": "PALLET",
    "model_entity_id": "E1",
    "has_boxes": True,
    "confidence": 0.9,
}

ProviderShapeFn = Callable[[dict[str, Any]], dict[str, Any]]


def _gemini_shape(entity: dict[str, Any]) -> dict[str, Any]:
    """Gemini structured output — canonical keys as returned by schema."""
    return copy.deepcopy(entity)


def _openai_shape(entity: dict[str, Any]) -> dict[str, Any]:
    """OpenAI Chat Completions JSON — may include qty alias alongside evidence fields."""
    shaped = copy.deepcopy(entity)
    shaped.setdefault("quantity", 1)
    return shaped


def _claude_shape(entity: dict[str, Any]) -> dict[str, Any]:
    """Claude JSON — may include product_label noise stripped by normalizer."""
    shaped = copy.deepcopy(entity)
    shaped["product_label"] = "SKU-IGNORED"
    shaped["position_label"] = "A1"
    return shaped


PROVIDER_SHAPES: dict[str, ProviderShapeFn] = {
    "gemini": _gemini_shape,
    "openai": _openai_shape,
    "claude": _claude_shape,
}


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


def _run_scenario(provider: str, evidence: dict[str, Any]) -> list:
    entity = {**_BASE_ENTITY, **evidence}
    shaped = PROVIDER_SHAPES[provider](entity)
    payload = normalize_llm_response(
        {"total_entities_detected": 1, "entities": [shaped]},
        provider=provider,
    )
    entities = parse_entities(payload, job_id="job-1")
    composition = manifest_composition_projection(_manifest())
    apply_evidence_resolution_to_entities(
        entities, composition=composition, manifest_required=True
    )
    apply_traceability_validation(
        entities,
        frozenset({"asset-1"}),
        reference_image_ids=frozenset({"ref-1"}),
        sent_metadata_available=True,
    )
    return entities


SCENARIOS: dict[str, dict[str, Any]] = {
    "manifest_entry_id_valid": {"manifest_entry_id": "IMG_001"},
    "legacy_source_image_id_valid": {"source_image_id": "asset-1"},
    "both_fields_agree": {"manifest_entry_id": "IMG_001", "source_image_id": "asset-1"},
    "both_fields_conflict": {"manifest_entry_id": "IMG_001", "source_image_id": "ref-1"},
    "ref_invalid": {"manifest_entry_id": "REF_001"},
    "unknown_img_invalid": {"manifest_entry_id": "IMG_999"},
    "missing_evidence": {},
    "malformed_evidence": {"manifest_entry_id": "filename.jpg"},
}


@pytest.mark.parametrize("provider", list(PROVIDER_SHAPES))
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_provider_shape_scenario(provider: str, scenario: str) -> None:
    entities = _run_scenario(provider, SCENARIOS[scenario])
    ent = entities[0]
    if scenario in ("manifest_entry_id_valid", "legacy_source_image_id_valid", "both_fields_agree"):
        assert ent.traceability_status == TraceabilityStatus.VALID.value
        assert ent.source_image_id == "asset-1"
    elif scenario in ("both_fields_conflict", "ref_invalid", "unknown_img_invalid", "malformed_evidence"):
        assert ent.traceability_status == TraceabilityStatus.INVALID.value
        assert ent.source_image_id is None
    elif scenario == "missing_evidence":
        assert ent.traceability_status == TraceabilityStatus.MISSING.value
        assert ent.source_image_id is None
