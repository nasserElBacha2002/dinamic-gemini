"""
Stage 2.2.D — LLM Provider Strategy (Strategy pattern).

Tests:
- Pipeline uses provider factory; no direct Gemini imports in pipeline.
- Hybrid pipeline E2E without network via ``patch_offline_hybrid_json_fixture`` (Phase 2 harness).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from src.jobs.models import JobInput


def test_pipeline_hybrid_does_not_import_gemini_sdk():
    """Hybrid orchestrator must not bind Gemini SDK types; execution goes through registry + strategy."""
    import src.pipeline.hybrid_inventory_pipeline as m

    assert not hasattr(m, "GeminiClient"), "Pipeline must not import GeminiClient"
    assert not hasattr(m, "GeminiGlobalAnalyzer"), "Pipeline must not import GeminiGlobalAnalyzer"
    from src.pipeline.providers import registry as reg

    assert hasattr(reg, "resolve_llm_executor"), "Registry must expose LLM executor resolution"


def test_hybrid_pipeline_e2e_patched_executor_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hybrid path uses patched ``resolve_llm_executor_for_context`` + fixture JSON; no network."""
    from tests.support.llm_executor_harness import patch_offline_hybrid_json_fixture

    fixtures_v21 = Path(__file__).resolve().parent / "fixtures" / "v2_1"
    patch_offline_hybrid_json_fixture(monkeypatch, fixtures_v21 / "global_analysis_ok.json")

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
    settings.llm_provider = "openai"
    settings.gemini_api_key = ""
    settings.openai_api_key = "offline-test-key"
    settings.photo_resize_max_side = 1280
    settings.photo_jpeg_quality = 85
    settings.photos_min_side = 64
    settings.debug_save_frames = False
    settings.hybrid_max_frames = None

    from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, _HybridRunParams

    logger = MagicMock()
    pipe = HybridInventoryPipeline()
    result = pipe._run_hybrid(
        "",
        _HybridRunParams(
            settings=settings,
            video_id="job_photos",
            output_path=tmp_path,
            run_id="run",
            logger=logger,
            job_input=job_input,
        ),
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
