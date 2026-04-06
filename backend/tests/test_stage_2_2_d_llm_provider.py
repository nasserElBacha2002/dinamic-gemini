"""
Stage 2.2.D — LLM Provider Strategy (Strategy pattern).

Tests:
- Pipeline uses provider factory; no direct Gemini imports in pipeline.
- FakeProvider returns valid v2.1-shaped JSON.
- With LLM_PROVIDER=fake, pipeline runs end-to-end without network and produces
  hybrid_report.json and evidence artifacts.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.jobs.models import JobInput
from src.llm.providers.fake_provider import DEFAULT_FAKE_RESPONSE, FakeProvider
from src.llm.types import LLMRequest, LLMResponse


def test_pipeline_hybrid_does_not_import_gemini_sdk():
    """Hybrid orchestrator must not bind Gemini SDK types; execution goes through registry + strategy."""
    import src.pipeline.hybrid_inventory_pipeline as m

    assert not hasattr(m, "GeminiClient"), "Pipeline must not import GeminiClient"
    assert not hasattr(m, "GeminiGlobalAnalyzer"), "Pipeline must not import GeminiGlobalAnalyzer"
    from src.pipeline.providers import registry as reg

    assert hasattr(reg, "resolve_llm_executor"), "Registry must expose LLM executor resolution"


def test_fake_provider_returns_v21_shaped_json():
    """FakeProvider returns dict with total_entities_detected and entities (v2.1)."""
    settings = MagicMock()
    settings.fake_llm_fixture_path = None
    provider = FakeProvider(settings)
    request = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="",
        schema_version="v2.1",
        metadata={},
    )
    response = provider.analyze_global(request)
    assert response.provider == "fake"
    assert "total_entities_detected" in response.parsed_json
    assert "entities" in response.parsed_json
    assert isinstance(response.parsed_json["entities"], list)
    assert response.parsed_json["total_entities_detected"] == len(response.parsed_json["entities"])


def test_fake_provider_uses_fixture_path_when_set(tmp_path):
    """When FAKE_LLM_FIXTURE_PATH is set, FakeProvider loads JSON from file."""
    fixture = {"total_entities_detected": 1, "entities": [{"model_entity_id": "e1", "entity_type": "PALLET"}]}
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    settings = MagicMock()
    settings.fake_llm_fixture_path = str(path)
    provider = FakeProvider(settings)
    request = LLMRequest(job_id="j1", frames=[], frame_refs=[], prompt="", schema_version="v2.1", metadata={})
    response = provider.analyze_global(request)
    assert response.parsed_json["total_entities_detected"] == 1
    assert len(response.parsed_json["entities"]) == 1
    assert response.parsed_json["entities"][0]["model_entity_id"] == "e1"


def test_fake_provider_default_fixture_is_minimal():
    """Default in-code fixture is minimal v2.1 (0 entities)."""
    assert DEFAULT_FAKE_RESPONSE["total_entities_detected"] == 0
    assert DEFAULT_FAKE_RESPONSE["entities"] == []


@pytest.mark.parametrize("llm_provider", ["fake"])
def test_hybrid_pipeline_e2e_fake_provider_no_network(tmp_path, llm_provider):
    """With LLM_PROVIDER=fake, hybrid pipeline runs without network and produces hybrid_report.json and evidence."""
    run_dir = tmp_path / "job_photos" / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest_photos = [{"index": i, "stored_filename": f"p_{i:04d}.jpg"} for i in range(1, 4)]
    manifest = {"input_type": "photos", "total_photos": 3, "photos": manifest_photos}
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    for i in range(1, 4):
        cv2.imwrite(str(photos_dir / f"p_{i:04d}.jpg"), img)

    job_input = JobInput(video_path="", input_type="photos")
    settings = MagicMock()
    settings.llm_provider = llm_provider
    settings.fake_llm_fixture_path = None
    settings.gemini_api_key = "unused"
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 64
    settings.debug_save_frames = False
    settings.hybrid_max_frames = None

    from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

    logger = MagicMock()
    pipe = HybridInventoryPipeline()
    result = pipe._run_hybrid(
        "",
        settings=settings,
        video_id="job_photos",
        output_path=tmp_path,
        run_id="run",
        logger=logger,
        job_input=job_input,
    )
    assert result.exit_code == 0
    report_path = run_dir / "hybrid_report.json"
    assert report_path.exists(), "hybrid_report.json must be produced"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("report_version") == "2.1"
    assert report.get("mode") == "hybrid_v2.1"
    assert "entities" in report
    assert "summary" in report

    evidence_index = run_dir / "evidence_index.json"
    assert evidence_index.exists(), "evidence_index.json must be produced"
