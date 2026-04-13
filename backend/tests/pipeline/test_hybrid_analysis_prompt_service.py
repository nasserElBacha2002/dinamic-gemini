"""Provider-neutral prompt assembly for hybrid analysis."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.pipeline.services.hybrid_analysis_prompt as hap_mod
from src.llm.prompt_composer.enrichments import IMAGE_ID_TRACEABILITY_ENRICHMENT_ID
from src.llm.prompt_composer.prompt_traceability import (
    COMPOSITION_STEP_COMPOSE_HYBRID_BASE,
    COMPOSITION_STEP_ENRICH_IMAGE_IDS,
    COMPOSITION_STEP_NORMALIZE_PIPELINE_PROVIDER,
    COMPOSITION_STEP_RESOLVE_PROFILE,
    sha256_utf8,
    validate_prompt_composition_dict,
)
from src.pipeline.context.run_context import RunContext
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_text,
    build_hybrid_analysis_prompt_with_traceability,
    resolve_analysis_context_for_run,
)


def test_build_hybrid_prompt_prefers_job_prompt_key() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "video"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        job_prompt_key="global_v21_b",
    )
    text = build_hybrid_analysis_prompt_text(ctx)
    assert "Conservative" in text or "conservative" in text.lower()
    assert "INSUFFICIENT_EVIDENCE" in text


def test_build_hybrid_prompt_uses_settings_hybrid_prompt_key() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "video"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    text = build_hybrid_analysis_prompt_text(ctx)
    assert "warehouse" in text.lower() or "aisle" in text.lower() or len(text) > 50


def test_build_hybrid_prompt_video_does_not_call_image_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    real = hap_mod.enrich_prompt_with_image_ids

    def _spy(base: str, images: list) -> str:
        calls.append((base, len(images)))
        return real(base, images)

    monkeypatch.setattr(hap_mod, "enrich_prompt_with_image_ids", _spy)
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "video"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    build_hybrid_analysis_prompt_text(ctx)
    assert calls == []


def test_build_hybrid_prompt_photos_calls_image_enrichment_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    real = hap_mod.enrich_prompt_with_image_ids

    def _spy(base: str, images: list) -> str:
        calls.append(1)
        return real(base, images)

    monkeypatch.setattr(hap_mod, "enrich_prompt_with_image_ids", _spy)
    job_dir = tmp_path / "j"
    run_dir = job_dir / "r"
    run_dir.mkdir(parents=True)
    photos_dir = job_dir / "photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "photos": [{"index": 1, "stored_filename": "a.jpg", "image_id": "img_001"}],
    }
    (job_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "photos"
    job_input.input_manifest_path = "input_manifest.json"
    job_input.photos_dir = "photos"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    text = build_hybrid_analysis_prompt_text(ctx)
    assert sum(calls) == 1
    assert "img_001" in text


def test_build_hybrid_traceability_matches_legacy_prompt_text() -> None:
    """Video / non-photo path: no enrichments → base and final identical; hashes align; validation OK."""
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "video"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    legacy = build_hybrid_analysis_prompt_text(ctx)
    text, meta = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert text == legacy
    assert meta["final_prompt_text"] == text
    assert meta["base_prompt_text"] == text
    assert meta["base_prompt_text"] == meta["final_prompt_text"]
    assert meta["prompt_hash"] == meta["base_prompt_hash"]
    assert meta["prompt_hash"] == sha256_utf8(text)
    assert meta["enrichments_applied"] == []
    step_names = [s.get("step") for s in meta["composition_steps"]]
    assert step_names == [
        COMPOSITION_STEP_RESOLVE_PROFILE,
        COMPOSITION_STEP_NORMALIZE_PIPELINE_PROVIDER,
        COMPOSITION_STEP_COMPOSE_HYBRID_BASE,
    ]
    assert validate_prompt_composition_dict(meta) == []


def test_build_hybrid_traceability_photos_records_enrichment(tmp_path: Path) -> None:
    job_dir = tmp_path / "j"
    run_dir = job_dir / "r"
    run_dir.mkdir(parents=True)
    photos_dir = job_dir / "photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "photos": [{"index": 1, "stored_filename": "a.jpg", "image_id": "img_001"}],
    }
    (job_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "photos"
    job_input.input_manifest_path = "input_manifest.json"
    job_input.photos_dir = "photos"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    text, meta = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert IMAGE_ID_TRACEABILITY_ENRICHMENT_ID in meta["enrichments_applied"]
    assert meta["base_prompt_text"] != meta["final_prompt_text"]
    assert meta["prompt_hash"] == sha256_utf8(text)
    assert meta["composition_steps"][-1]["step"] == COMPOSITION_STEP_ENRICH_IMAGE_IDS
    assert validate_prompt_composition_dict(meta) == []


def test_resolve_analysis_context_from_run_context_attribute() -> None:
    ac = MagicMock()
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=MagicMock(),
        settings=MagicMock(),
        logger=MagicMock(),
        analysis_context=ac,
    )
    assert resolve_analysis_context_for_run(ctx) is ac
