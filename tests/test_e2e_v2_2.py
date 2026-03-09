"""
Stage 2.2.E — E2E tests and compatibility validation.

Offline, deterministic integration tests using FakeProvider (no network).
Validates: video path, photos path, evidence localization, assisted counting API, provider wiring.
"""

import json
import os
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.jobs.job_store import create_job, get_job, update_job
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
    return pipeline._run_hybrid(
        video_path,
        settings=settings,
        video_id=job_id,
        output_path=output_dir,
        run_id=run_id,
        logger=logger,
        job_input=job_input,
    )


def make_fake_settings(
    *,
    llm_provider: str = "fake",
    fake_llm_fixture_path: Optional[str] = None,
    output_dir: Optional[Path] = None,
    photos_min_side: int = 64,
    photo_resize_max_side: int = 1280,
    photo_jpeg_quality: int = 85,
) -> MagicMock:
    """Build a MagicMock settings object for E2E (FakeProvider, no network)."""
    s = MagicMock()
    s.llm_provider = llm_provider
    s.fake_llm_fixture_path = fake_llm_fixture_path
    s.gemini_api_key = "unused"
    s.photo_resize_max_side = photo_resize_max_side
    s.photo_jpeg_quality = photo_jpeg_quality
    s.photos_min_side = photos_min_side
    s.debug_save_frames = False
    s.hybrid_max_frames = None
    if output_dir is not None:
        s.output_dir = str(output_dir)
    return s


# --- A) E2E Video ---


def test_e2e_video_job_generates_report_and_evidence(tmp_path):
    """Video path: stub frame extraction, FakeProvider with fixture; assert report + evidence + stable order."""
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

    settings = make_fake_settings(fake_llm_fixture_path=str(GLOBAL_ANALYSIS_OK))
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


def test_e2e_photos_job_persists_normalized_and_generates_report(tmp_path):
    """Photos job: input_photos + manifest, normalization, FakeProvider; assert normalized dir + report + evidence."""
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

    settings = make_fake_settings(fake_llm_fixture_path=str(GLOBAL_ANALYSIS_OK))
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


def test_e2e_evidence_localization_modes(tmp_path):
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
    settings_ok = make_fake_settings(fake_llm_fixture_path=str(GLOBAL_ANALYSIS_OK))
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
    settings_u = make_fake_settings(fake_llm_fixture_path=str(GLOBAL_ANALYSIS_UNLOCALIZED))
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


# --- D) Assisted counting API ---


def test_api_review_flow_on_succeeded_job(tmp_path):
    """API: GET entities, GET evidence, POST review, GET audit, GET report?resolved=true."""
    from fastapi.testclient import TestClient

    from src.api.server import app
    from src.config import load_settings

    job_id = "e2e_api_job"
    run_id = "run"
    run_dir = tmp_path / job_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Pre-create succeeded job with report + evidence
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "video": {"path": "", "name": ""},
        "frames_selected": 2,
        "summary": {"total_entities": 1, "pallets": 1, "counted": 0, "needs_review": 1, "counted_manual": 0, "empty_pallets": 0, "loose_boxes": 0, "not_countable": 0, "invalid_structure": 0},
        "entities": [
            {
                "entity_uid": f"{job_id}_e1",
                "entity_type": "PALLET",
                "model_entity_id": "e1",
                "pallet_id": "A1",
                "count_status": "NEEDS_REVIEW",
                "final_quantity": None,
                "evidence_path": "evidence/e2e_api_job_e1",
            }
        ],
    }
    (run_dir / "hybrid_report.json").write_text(json.dumps(report), encoding="utf-8")
    evidence_dir = run_dir / "evidence" / "e2e_api_job_e1"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "overview_00.jpg").write_bytes(b"\xff\xd8\xff")
    index = {
        "job_id": job_id,
        "mode": "hybrid_v2.1",
        "entities": [
            {"entity_uid": f"{job_id}_e1", "evidence_localization": "UNLOCALIZED", "evidence": {"overview": ["evidence/e2e_api_job_e1/overview_00.jpg"]}},
        ],
    }
    (run_dir / "evidence_index.json").write_text(json.dumps(index), encoding="utf-8")
    create_job(tmp_path, job_id, video_path="", mode="hybrid", input_type="video")
    update_job(tmp_path, job_id, status=JobStatus.SUCCEEDED, output={"report_json_path": str(run_dir / "hybrid_report.json"), "report_csv_path": None, "artifacts_dir": str(tmp_path / job_id)})

    def _settings():
        s = load_settings()
        s.output_dir = str(tmp_path)
        return s

    with patch("src.api.routes.jobs.load_settings", side_effect=_settings), patch("src.config.load_settings", side_effect=_settings), patch("src.jobs.job_store._db_repos", return_value=None), patch("src.api.routes.jobs._get_db_repos", return_value=None):
            client = TestClient(app)
            # GET entities (uses _resolve_report_and_run_dir -> _base_path -> load_settings)
            r = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
            assert r.status_code == 200
            data = r.json()
            assert "entities" in data
            assert len(data["entities"]) == 1
            entity_uid = data["entities"][0]["entity_uid"]

            # GET evidence
            r2 = client.get(f"/api/v1/inventory/jobs/{job_id}/entities/{entity_uid}/evidence")
            assert r2.status_code == 200
            assert "evidence" in r2.json()

            # POST review SET_COUNT
            r3 = client.post(
                f"/api/v1/inventory/jobs/{job_id}/entities/{entity_uid}/review",
                json={"action": "SET_COUNT", "final_quantity": 12, "actor": "test"},
            )
            assert r3.status_code == 200

            # GET audit
            r4 = client.get(f"/api/v1/inventory/jobs/{job_id}/entities/{entity_uid}/audit")
            assert r4.status_code == 200
            audit = r4.json()
            assert "events" in audit
            assert len(audit["events"]) >= 1

            # GET report?resolved=true
            r5 = client.get(f"/api/v1/inventory/jobs/{job_id}/report", params={"resolved": "true"})
            assert r5.status_code == 200
            merged = r5.json()
            assert merged.get("report_version") == "2.1"
            entities_merged = merged.get("entities") or []
            assert len(entities_merged) == 1
            assert entities_merged[0].get("final_quantity") == 12
            assert entities_merged[0].get("count_status") == "COUNTED_MANUAL"


# --- E) Provider wiring (no network) ---


def test_pipeline_uses_fake_provider_no_network(tmp_path):
    """LLM_PROVIDER=fake: pipeline completes without calling GeminiClient."""
    job_id = "e2e_fake_only"
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
    settings = make_fake_settings(llm_provider="fake", fake_llm_fixture_path=str(GLOBAL_ANALYSIS_OK))
    gemini_constructor_called = []

    def _track_gemini(*args, **kwargs):
        gemini_constructor_called.append(1)
        raise RuntimeError("GeminiClient must not be used when provider is fake")

    with patch("src.pipeline.stages.frame_acquisition_stage.get_frame_source") as mock_src:
        mock_src.return_value.get_frames.return_value = bundle
        with patch("src.llm.providers.gemini_provider.GeminiClient", side_effect=_track_gemini):
            from src.jobs.models import JobInput

            job_input = JobInput(video_path="", mode="hybrid", input_type="video")
            code = run_pipeline_sync(tmp_path, job_id, "run", settings=settings, job_input=job_input)
    assert code == 0
    assert len(gemini_constructor_called) == 0, "GeminiClient must not be instantiated when using FakeProvider"
    assert (run_dir / "hybrid_report.json").exists()
