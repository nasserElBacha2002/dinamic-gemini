"""Phase 1 — sent-frame allowlist, prompt list, traceability warnings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.entity import Entity
from src.domain.traceability import (
    TRACEABILITY_INVALID,
    TRACEABILITY_MISSING,
    TRACEABILITY_VALID,
    apply_traceability_validation,
)
from src.jobs.image_identity import JobImage
from src.llm.prompt_composer.enrichments import enrich_prompt_with_sent_image_ids
from src.llm.prompt_composer.enrichments import enrich_prompt_with_sent_image_ids
from src.pipeline.context.run_context import RunContext
from src.pipeline.services.hybrid_analysis_prompt import build_hybrid_analysis_prompt_with_traceability
from src.pipeline.stages.analysis_stage import AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage


def test_frame_cap_invalid_when_id_not_in_sent_frames() -> None:
    """80 manifest IDs, 48 sent — model returns img_050 -> invalid with sent-frame warning."""
    manifest_ids = {f"img_{i:03d}" for i in range(1, 81)}
    sent_ids = {f"img_{i:03d}" for i in range(1, 49)}
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_050",
        )
    ]
    apply_traceability_validation(
        entities,
        frozenset(sent_ids),
        manifest_image_ids=manifest_ids,
    )
    assert entities[0].traceability_status == TRACEABILITY_INVALID
    assert entities[0].traceability_warning is not None
    assert "not part of the model input frames" in entities[0].traceability_warning


def test_valid_when_source_image_id_in_sent_frames() -> None:
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_048",
        )
    ]
    sent = frozenset(f"img_{i:03d}" for i in range(1, 49))
    apply_traceability_validation(entities, sent, manifest_image_ids=sent | {"img_080"})
    assert entities[0].traceability_status == TRACEABILITY_VALID


def test_missing_source_image_id_unchanged() -> None:
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id=None,
        )
    ]
    apply_traceability_validation(entities, frozenset({"img_001"}))
    assert entities[0].traceability_status == TRACEABILITY_MISSING


def test_unknown_id_not_in_manifest_uses_generic_warning() -> None:
    entities = [
        Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id="img_999",
        )
    ]
    apply_traceability_validation(
        entities,
        frozenset({"img_001"}),
        manifest_image_ids=frozenset({"img_001", "img_002"}),
    )
    assert entities[0].traceability_status == TRACEABILITY_INVALID
    assert "not in job" in (entities[0].traceability_warning or "")


def test_enrich_sent_image_ids_all_found_in_job_images() -> None:
    images = [
        JobImage("img_001", "a.jpg", 1, "p1.jpg"),
        JobImage("img_002", "b.jpg", 2, "p2.jpg"),
    ]
    text = enrich_prompt_with_sent_image_ids("BASE", images, ["img_001", "img_002"])
    assert "upload_order=1" in text
    assert "upload_order=2" in text
    assert text.index("img_001") < text.index("img_002")


def test_enrich_sent_image_ids_none_found_uses_id_only_lines() -> None:
    images = [JobImage("img_001", "a.jpg", 1, "p1.jpg")]
    text = enrich_prompt_with_sent_image_ids("BASE", images, ["photo_0002", "photo_0003"])
    assert "photo_0002" in text
    assert "photo_0003" in text
    assert "upload_order" not in text


def test_enrich_sent_image_ids_partial_metadata_preserves_all_ids_in_order() -> None:
    images = [JobImage("img_001", "a.jpg", 1, "p1.jpg")]
    text = enrich_prompt_with_sent_image_ids("BASE", images, ["img_001", "photo_0002"])
    assert text.index("img_001") < text.index("photo_0002")
    assert "upload_order=1" in text
    assert "- photo_0002" in text


def test_prompt_enrichment_lists_only_sent_frames() -> None:
    images = [
        JobImage(
            image_id=f"img_{i:03d}",
            upload_order=i,
            original_filename=f"f{i}.jpg",
            storage_path=f"p{i}.jpg",
        )
        for i in range(1, 81)
    ]
    sent = [f"img_{i:03d}" for i in range(1, 49)]
    text = enrich_prompt_with_sent_image_ids("BASE", images, sent)
    assert "img_048" in text
    assert "img_049" not in text
    assert "img_080" not in text
    assert text.index("img_001") < text.index("img_048")


def test_entity_resolution_uses_frames_sent_ids_from_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EntityResolutionStage prefers prompt_composition.frames_sent_ids over full manifest."""
    context = MagicMock(spec=RunContext)
    context.job_id = "job1"
    context.logger = MagicMock()
    context.run_dir = Path("/tmp/job1/run1")
    job_input = MagicMock()
    job_input.input_type = "photos"
    context.job_input = job_input

    manifest_images = [
        JobImage(
            image_id=f"img_{i:03d}",
            upload_order=i,
            original_filename="x.jpg",
            storage_path="x.jpg",
        )
        for i in range(1, 81)
    ]

    def fake_load(_mp: Path, _pd: str) -> list[JobImage]:
        return manifest_images

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        fake_load,
    )
    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.resolve_manifest_path",
        lambda _rd, _ji: Path("/fake/manifest.json"),
    )
    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.photos_dir_relative_for_manifest",
        lambda _ji: "photos",
    )

    analysis_result = AnalysisStageResult(
        parsed_json={
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "has_boxes": True,
                    "confidence": 0.9,
                    "source_image_id": "img_050",
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={
            "frames_sent_ids": [f"img_{i:03d}" for i in range(1, 49)],
            "prompt_listed_image_ids": [f"img_{i:03d}" for i in range(1, 49)],
        },
    )

    resolved = EntityResolutionStage().run(context, analysis_result)
    assert resolved.entities[0].traceability_status == TRACEABILITY_INVALID
    assert "not part of the model input frames" in (
        resolved.entities[0].traceability_warning or ""
    )
