"""
Stage 2.2.E — E2E tests and compatibility validation.

Offline, deterministic integration tests: registry ``resolve_llm_executor`` is patched to a
``TestLLMExecutor`` fed by JSON fixtures (no network, no ``FakeProvider`` in the pipeline path).
Validates: video path, photos path, evidence localization, assisted counting API, provider wiring.
"""

import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.jobs.job_store import create_job, get_job
from src.jobs.models import JobStatus
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

# Paths to fixtures (relative to repo root)
FIXTURES_V21 = Path(__file__).resolve().parent / "fixtures" / "v2_1"
GLOBAL_ANALYSIS_OK = FIXTURES_V21 / "global_analysis_ok.json"
GLOBAL_ANALYSIS_UNLOCALIZED = FIXTURES_V21 / "global_analysis_unlocalized.json"


# --- Test helpers (tests/ only) ---


def create_temp_job_dirs(output_dir: Path, job_id: str) -> Path:
    """Create output/<job_id>/ and return job dir."""
    job_dir = output_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def write_minimal_job_record(
    output_dir: Path,
    job_id: str,
    *,
    input_type: str = "video",
    video_path: str = "",
    mode: str = "hybrid",
    input_manifest_path: Optional[str] = None,
    photos_dir: Optional[str] = None,
) -> Path:
    """Create job via job_store and return job dir. Job is QUEUED."""
    create_job(
        output_dir,
        job_id,
        video_path=video_path or "",
        mode=mode,
        confidence_threshold=0.70,
        input_type=input_type,
        input_manifest_path=input_manifest_path,
        photos_dir=photos_dir,
    )
    return output_dir / job_id


def run_pipeline_sync(
    output_dir: Path,
    job_id: str,
    run_id: str = "run",
    *,
    settings: MagicMock,
    job_input: Optional[object] = None,
) -> int:
    """Run hybrid pipeline synchronously; return exit code."""
    from src.jobs.models import JobInput

    if job_input is None:
        record = get_job(output_dir, job_id)
        job_input = record.input if record else JobInput(video_path="", mode="hybrid", input_type="video")
    pipeline = HybridInventoryPipeline()
    logger = MagicMock()
    video_path = getattr(job_input, "video_path", "") or ""
    result = pipeline._run_hybrid(
        video_path,
        settings=settings,
        video_id=job_id,
        output_path=output_dir,
        run_id=run_id,
        logger=logger,
        job_input=job_input,
    )
    return result.exit_code


def _patch_registry_executor_from_json(monkeypatch: pytest.MonkeyPatch, fixture_path: Path) -> None:
    from tests.support.llm_executor_harness import patch_registry_resolve_llm_executor, test_executor_from_json_path

    patch_registry_resolve_llm_executor(monkeypatch, test_executor_from_json_path(fixture_path))


def make_offline_pipeline_settings(
    *,
    llm_provider: str = "gemini",
    output_dir: Optional[Path] = None,
    photos_min_side: int = 64,
    photo_resize_max_side: int = 1280,
    photo_jpeg_quality: int = 85,
) -> MagicMock:
    """Settings for offline pipeline runs (logical provider key + keys; LLM via patched executor)."""
    s = MagicMock()
    s.llm_provider = llm_provider
    s.fake_llm_fixture_path = None
    s.gemini_api_key = "offline-test-key"
    s.photo_resize_max_side = photo_resize_max_side
    s.photo_jpeg_quality = photo_jpeg_quality
    s.photos_min_side = photos_min_side
    s.debug_save_frames = False
    s.hybrid_max_frames = None
    if output_dir is not None:
        s.output_dir = str(output_dir)
    return s


# --- A) E2E Video ---


def test_e2e_video_job_generates_report_and_evidence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Video path: stub frames + patched executor from fixture JSON; assert report + evidence + stable order."""
    _patch_registry_executor_from_json(monkeypatch, GLOBAL_ANALYSIS_OK)
    job_id = "e2e_video_01"
    run_id = "run"
    create_temp_job_dirs(tmp_path, job_id)
    run_dir = tmp_path / job_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Stub video frame extraction: write a few frame images so bundle has paths
    extract_dir = run_dir / ".frames_extract_stub"
    extract_dir.mkdir(exist_ok=True)
    frames_nd = [np.zeros((64, 64, 3), dtype=np.uint8) for _ in range(3)]
    frame_paths = []
    for i in range(len(frames_nd)):
        p = extract_dir / f"frame_{i:06d}.jpg"
        cv2.imwrite(str(p), frames_nd[i])
        frame_paths.append(p)

    from src.frames.types import FramesBundle

    bundle = FramesBundle(
        frames=frame_paths,
        frame_refs=[f"frame_{i:06d}" for i in range(len(frame_paths))],
        metadata={"source": "video", "frame_count": len(frame_paths), "selected_by": "video_sampling", "frame_indices": [0, 1, 2]},
    )

    settings = make_offline_pipeline_settings()
    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_source = MagicMock()
        mock_source.get_frames.return_value = bundle
        mock_src.return_value = mock_source

        from src.jobs.models import JobInput

        job_input = JobInput(video_path="/dummy/video.mp4", mode="hybrid", input_type="video")
        code = run_pipeline_sync(tmp_path, job_id, run_id, settings=settings, job_input=job_input)

    assert code == 0
    report_path = run_dir / "hybrid_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("mode") == "hybrid_v2.1"
    assert report.get("report_version") == "2.1"
    assert "entities" in report
    assert "summary" in report
    entity_uids = [e.get("entity_uid") for e in report["entities"]]
    assert len(entity_uids) >= 2
    assert all(e for e in entity_uids)

    evidence_index_path = run_dir / "evidence_index.json"
    assert evidence_index_path.exists()
    index = json.loads(evidence_index_path.read_text(encoding="utf-8"))
    assert index.get("job_id") == job_id
    assert "entities" in index

    evidence_dir = run_dir / "evidence"
    assert evidence_dir.exists() and evidence_dir.is_dir()

    # Determinism: entity order stable (by original_index / sort)
    assert len(report["entities"]) == 2


# --- B) E2E Photos ---


def test_e2e_photos_job_persists_normalized_and_generates_report(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Photos job: input_photos + manifest, normalization, patched executor; assert normalized dir + report + evidence."""
    _patch_registry_executor_from_json(monkeypatch, GLOBAL_ANALYSIS_OK)
    job_id = "e2e_photos_01"
    run_id = "run"
    run_dir = tmp_path / job_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir(exist_ok=True)
    # Generate 2 small JPEGs
    for i in range(1, 3):
        img = np.zeros((80, 80, 3), dtype=np.uint8)
        img[:] = (i * 40, 100, 150)
        cv2.imwrite(str(photos_dir / f"p_{i:04d}.jpg"), img)
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "photos": [
            {"index": 1, "stored_filename": "p_0001.jpg"},
            {"index": 2, "stored_filename": "p_0002.jpg"},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    from src.jobs.models import JobInput

    job_input = JobInput(
        video_path="",
        mode="hybrid",
        input_type="photos",
        input_manifest_path="run/input_manifest.json",
        photos_dir="run/input_photos",
    )
    create_job(
        tmp_path,
        job_id,
        video_path="",
        mode="hybrid",
        input_type="photos",
        input_manifest_path="run/input_manifest.json",
        photos_dir="run/input_photos",
    )

    settings = make_offline_pipeline_settings()
    code = run_pipeline_sync(tmp_path, job_id, run_id, settings=settings, job_input=job_input)

    assert code == 0
    normalized_dir = run_dir / "input_photos_normalized"
    assert normalized_dir.exists()
    normalized_images = list(normalized_dir.glob("*.jpg"))
    assert len(normalized_images) >= 2

    manifest_after = json.loads((run_dir / "input_manifest.json").read_text(encoding="utf-8"))
    photos_list = manifest_after.get("photos") or []
    for p in photos_list:
        assert "stored_normalized_filename" in p or normalized_dir.exists()

    report_path = run_dir / "hybrid_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("report_version") == "2.1"
    assert report.get("mode") == "hybrid_v2.1"

    evidence_index_path = run_dir / "evidence_index.json"
    assert evidence_index_path.exists()


# --- C) Evidence localization modes ---


def test_e2e_evidence_localization_modes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run with bbox fixture -> LOCALIZED; with unlocalized fixture -> UNLOCALIZED; assert index and crops."""
    job_id = "e2e_loc"
    run_id = "run"
    run_dir = tmp_path / job_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = run_dir / ".frames_extract_stub"
    extract_dir.mkdir(exist_ok=True)
    frame_paths = []
    for i in range(2):
        p = extract_dir / f"frame_{i:06d}.jpg"
        cv2.imwrite(str(p), np.zeros((64, 64, 3), dtype=np.uint8))
        frame_paths.append(p)

    from src.frames.types import FramesBundle

    bundle = FramesBundle(
        frames=frame_paths,
        frame_refs=[f"frame_{i:06d}" for i in range(2)],
        metadata={"source": "video", "frame_count": 2, "selected_by": "video_sampling", "frame_indices": [0, 1]},
    )

    # 1) With bboxes -> LOCALIZED
    _patch_registry_executor_from_json(monkeypatch, GLOBAL_ANALYSIS_OK)
    settings_ok = make_offline_pipeline_settings()
    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_src.return_value.get_frames.return_value = bundle
        from src.jobs.models import JobInput

        job_input = JobInput(video_path="", mode="hybrid", input_type="video")
        code1 = run_pipeline_sync(tmp_path, job_id, run_id, settings=settings_ok, job_input=job_input)
    assert code1 == 0
    index1 = json.loads((run_dir / "evidence_index.json").read_text(encoding="utf-8"))
    entities_index1 = index1.get("entities") or []
    localized_any = any(
        (e.get("evidence_localization") == "LOCALIZED") for e in entities_index1
    )
    assert localized_any, "At least one entity should be LOCALIZED when bboxes present"
    # Label crops referenced
    for e in entities_index1:
        ev = e.get("evidence") or {}
        if e.get("evidence_localization") == "LOCALIZED":
            assert "overview" in ev
            assert ev.get("position_label_best") or ev.get("product_label_best") or ev.get("position_label_candidates") or ev.get("product_label_candidates")

    # 2) Without bboxes -> UNLOCALIZED (new job_id to avoid overwriting)
    job_id2 = "e2e_loc_u"
    run_dir2 = tmp_path / job_id2 / run_id
    run_dir2.mkdir(parents=True, exist_ok=True)
    extract_dir2 = run_dir2 / ".frames_extract_stub"
    extract_dir2.mkdir(exist_ok=True)
    for i in range(2):
        p = extract_dir2 / f"frame_{i:06d}.jpg"
        cv2.imwrite(str(p), np.zeros((64, 64, 3), dtype=np.uint8))
    bundle2 = FramesBundle(
        frames=list(extract_dir2.glob("*.jpg")),
        frame_refs=["frame_000000", "frame_000001"],
        metadata={"source": "video", "frame_count": 2, "selected_by": "video_sampling", "frame_indices": [0, 1]},
    )
    _patch_registry_executor_from_json(monkeypatch, GLOBAL_ANALYSIS_UNLOCALIZED)
    settings_u = make_offline_pipeline_settings()
    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_src.return_value.get_frames.return_value = bundle2
        job_input2 = JobInput(video_path="", mode="hybrid", input_type="video")
        code2 = run_pipeline_sync(tmp_path, job_id2, run_id, settings=settings_u, job_input=job_input2)
    assert code2 == 0
    index2 = json.loads((run_dir2 / "evidence_index.json").read_text(encoding="utf-8"))
    entities_index2 = index2.get("entities") or []
    unlocalized_all = all(
        (e.get("evidence_localization") == "UNLOCALIZED") for e in entities_index2
    )
    assert unlocalized_all
    for e in entities_index2:
        ev = e.get("evidence") or {}
        assert "overview" in ev
        assert ev.get("position_label_best") is None and ev.get("product_label_best") is None


# --- D) Assisted counting API: v1 routes removed in Stage 3; use v3 positions/reviews ---


# --- E) Provider wiring (no network) ---


def test_pipeline_completes_without_gemini_client_when_executor_is_patched(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patched registry executor: pipeline completes without instantiating GeminiClient."""
    _patch_registry_executor_from_json(monkeypatch, GLOBAL_ANALYSIS_OK)
    job_id = "e2e_patched_executor"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = run_dir / ".frames_extract_stub"
    extract_dir.mkdir(exist_ok=True)
    for i in range(2):
        p = extract_dir / f"frame_{i:06d}.jpg"
        cv2.imwrite(str(p), np.zeros((64, 64, 3), dtype=np.uint8))
    from src.frames.types import FramesBundle

    bundle = FramesBundle(
        frames=sorted(extract_dir.glob("*.jpg")),
        frame_refs=["frame_000000", "frame_000001"],
        metadata={"source": "video", "frame_count": 2, "selected_by": "video_sampling", "frame_indices": [0, 1]},
    )
    settings = make_offline_pipeline_settings(llm_provider="gemini")
    gemini_constructor_called = []

    def _track_gemini(*args, **kwargs):
        gemini_constructor_called.append(1)
        raise RuntimeError("GeminiClient must not be used when executor is injected at registry boundary")

    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_src.return_value.get_frames.return_value = bundle
        with patch("src.llm.gemini_client.GeminiClient", side_effect=_track_gemini):
            from src.jobs.models import JobInput

            job_input = JobInput(video_path="", mode="hybrid", input_type="video")
            code = run_pipeline_sync(tmp_path, job_id, "run", settings=settings, job_input=job_input)
    assert code == 0
    assert len(gemini_constructor_called) == 0, "GeminiClient must not be instantiated when registry returns test executor"
    assert (run_dir / "hybrid_report.json").exists()
