"""Phase 1 follow-up — integration-style sent-frame ID propagation through hybrid analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.domain.traceability import TRACEABILITY_INVALID, WARNING_NOT_IN_SENT
from src.jobs.image_identity import JobImage
from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_COMPOSITION
from src.llm.types import LLMRequest, LLMResponse
from src.llm.vision_multimodal_payload import (
    LLM_METADATA_KEY_FRAMES_SENT_IDS,
    LLM_METADATA_KEY_PROMPT_LISTED_IMAGE_IDS,
)
from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.analysis_stage import AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage
from tests.support.llm_executor_harness import (
    TestLLMExecutor,
    llm_response_success,
    patch_hybrid_resolve_llm_executor,
)


def _photos_context(tmp_path: Path) -> RunContext:
    job_input = MagicMock()
    job_input.input_type = "photos"
    job_input.input_manifest_path = "input_manifest.json"
    job_input.photos_dir = "photos"
    job_input.metadata = {}
    settings = MagicMock()
    settings.hybrid_prompt = "global_v22"
    settings.debug_log_full_analysis_prompt = False
    settings.execution_log_include_full_prompt = False
    run_dir = tmp_path / "job1" / "run1"
    run_dir.mkdir(parents=True)
    return RunContext(
        job_id="job1",
        run_id="run1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        execution_log=MagicMock(),
    )


def test_hybrid_strategy_propagates_sent_frame_ids_to_entity_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Production path: strategy → request metadata → prompt_composition → EntityResolutionStage."""
    manifest_images = [
        JobImage(
            image_id=f"img_{i:03d}",
            upload_order=i,
            original_filename=f"f{i}.jpg",
            storage_path=f"p{i}.jpg",
        )
        for i in range(1, 81)
    ]
    sent_refs = [f"img_{i:03d}" for i in range(1, 49)]

    monkeypatch.setattr(
        "src.pipeline.services.hybrid_analysis_prompt.load_job_images_from_manifest",
        lambda _mp, _pd: manifest_images,
    )

    captured: dict[str, Any] = {}

    def _handler(request: LLMRequest, settings: Any) -> LLMResponse:
        del settings
        captured["request"] = request
        return llm_response_success(
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
            provider="harness",
        )

    patch_hybrid_resolve_llm_executor(monkeypatch, TestLLMExecutor(handler=_handler))
    context = _photos_context(tmp_path)
    frames_nd = [np.zeros((8, 8, 3), dtype=np.uint8) for _ in sent_refs]

    strategy = HybridGlobalAnalysisStrategy()
    analysis_result_provider = strategy.analyze(
        context=context,
        frames_nd=frames_nd,
        frame_paths=[Path(f"/tmp/{r}.jpg") for r in sent_refs],
        frame_refs=sent_refs,
        metadata={},
    )

    req = captured["request"]
    assert req.metadata[LLM_METADATA_KEY_FRAMES_SENT_IDS] == sent_refs
    listed = req.metadata[LLM_METADATA_KEY_PROMPT_LISTED_IMAGE_IDS]
    assert listed[:3] == ["IMG_001", "IMG_002", "IMG_003"]
    assert len(listed) == len(sent_refs)
    pc = req.metadata[LLM_METADATA_KEY_PROMPT_COMPOSITION]
    assert pc["frames_sent_ids"] == sent_refs
    assert pc["prompt_listed_image_ids"][:3] == ["IMG_001", "IMG_002", "IMG_003"]
    assert pc.get("execution_image_manifest") is not None
    assert "manifest_bound_multimodal_order" in req.metadata
    assert "IMG_048" in req.prompt
    assert "source_image_id='img_048'" in req.prompt
    assert "img_050" not in req.prompt
    assert "img_080" not in req.prompt

    analysis_stage_result = AnalysisStageResult(
        parsed_json=normalize_llm_response(
            analysis_result_provider.parsed_json,
            analysis_result_provider.provider_name,
        ),
        provider_name=analysis_result_provider.provider_name,
        provider_metadata=analysis_result_provider.provider_metadata,
        prompt_composition=analysis_result_provider.prompt_composition,
        llm_cost_snapshot=analysis_result_provider.llm_cost_snapshot,
    )

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

    resolved = EntityResolutionStage().run(context, analysis_stage_result)
    assert resolved.entities[0].traceability_status == TRACEABILITY_INVALID
    assert resolved.entities[0].traceability_warning == WARNING_NOT_IN_SENT
