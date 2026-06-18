"""Phase 4.2 — EntityResolutionStage must not fall back to full manifest for validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.domain.manifest_evidence_resolution import WARNING_MANIFEST_UNAVAILABLE
from src.domain.traceability import TRACEABILITY_UNVALIDATED
from src.jobs.image_identity import JobImage
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.analysis_stage import AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage


def test_entity_resolution_unvalidated_when_frames_sent_ids_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = MagicMock(spec=RunContext)
    context.job_id = "job1"
    context.logger = MagicMock()
    context.run_dir = tmp_path
    job_input = MagicMock()
    job_input.input_type = "photos"
    context.job_input = job_input

    manifest_images = [
        JobImage("asset-only-manifest", "a.jpg", 1, "a.jpg"),
    ]

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        lambda _mp, _pd: manifest_images,
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
                    "source_image_id": "asset-only-manifest",
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={},
    )

    resolved = EntityResolutionStage().run(context, analysis_result)
    assert resolved.entities[0].traceability_status == TRACEABILITY_UNVALIDATED
    assert resolved.entities[0].traceability_warning == WARNING_MANIFEST_UNAVAILABLE


def test_entity_resolution_unvalidated_when_only_prompt_listed_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """prompt_listed_image_ids must not authorize VALID when frames_sent_ids is absent."""
    context = MagicMock(spec=RunContext)
    context.job_id = "job1"
    context.logger = MagicMock()
    context.run_dir = tmp_path
    job_input = MagicMock()
    job_input.input_type = "photos"
    context.job_input = job_input

    manifest_images = [
        JobImage("asset-only-manifest", "a.jpg", 1, "a.jpg"),
    ]

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        lambda _mp, _pd: manifest_images,
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
                    "source_image_id": "asset-only-manifest",
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={"prompt_listed_image_ids": ["asset-only-manifest"]},
    )

    resolved = EntityResolutionStage().run(context, analysis_result)
    assert resolved.entities[0].traceability_status == TRACEABILITY_UNVALIDATED
    assert resolved.entities[0].traceability_warning == WARNING_MANIFEST_UNAVAILABLE


def test_entity_resolution_unvalidated_when_frames_sent_ids_empty_with_prompt_listed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context = MagicMock(spec=RunContext)
    context.job_id = "job1"
    context.logger = MagicMock()
    context.run_dir = tmp_path
    job_input = MagicMock()
    job_input.input_type = "photos"
    context.job_input = job_input

    manifest_images = [
        JobImage("asset-1", "a.jpg", 1, "a.jpg"),
    ]

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        lambda _mp, _pd: manifest_images,
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
                    "source_image_id": "asset-1",
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={
            "frames_sent_ids": [],
            "prompt_listed_image_ids": ["asset-1"],
        },
    )

    resolved = EntityResolutionStage().run(context, analysis_result)
    assert resolved.entities[0].traceability_status == TRACEABILITY_UNVALIDATED
    assert resolved.entities[0].traceability_warning == WARNING_MANIFEST_UNAVAILABLE
