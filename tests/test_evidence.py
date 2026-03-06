"""Stage 2.1.D — Evidence pack tests.

- Frame scoring determinism
- Hash deduplication
- Evidence generation with bbox (LOCALIZED)
- Evidence generation without bbox (UNLOCALIZED)
- evidence_index.json structure
- Max images limit respected
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.domain.entity import Entity
from src.evidence.evidence_pack import (
    EVIDENCE_LOCALIZED,
    EVIDENCE_UNLOCALIZED,
    generate_evidence_pack,
    parse_bbox_to_pixels,
    _select_overview_frames,
    _select_best_crop_candidates,
    _crop_bbox,
)
from src.evidence.paths import entity_evidence_path, slug
from src.evidence.scoring import dedupe_by_hash, dedupe_indexed_by_hash, score_frame_sharpness


# --- scoring ---


def test_score_frame_sharpness_deterministic():
    """Same frame yields same sharpness score."""
    rng = np.random.default_rng(42)
    frame = (rng.random((100, 100, 3)) * 255).astype(np.uint8)
    a = score_frame_sharpness(frame)
    b = score_frame_sharpness(frame)
    assert a == b
    assert isinstance(a, float)
    assert a >= 0


def test_score_frame_sharpness_empty_returns_zero():
    """Empty or None frame returns 0."""
    assert score_frame_sharpness(np.array([])) == 0.0


def test_dedupe_by_hash_removes_duplicates():
    """Identical frames reduced to one; different frames kept."""
    rng = np.random.default_rng(1)
    f1 = (rng.random((50, 50, 3)) * 255).astype(np.uint8)
    f2 = f1.copy()
    f3 = (rng.random((50, 50, 3)) * 255).astype(np.uint8)
    result = dedupe_by_hash([f1, f2, f3], threshold=10)
    assert len(result) == 2
    assert np.array_equal(result[0], f1)
    assert np.array_equal(result[2] if len(result) > 2 else result[1], f3)


def test_dedupe_by_hash_empty():
    assert dedupe_by_hash([]) == []


def test_dedupe_set_based_compares_to_all():
    """Set-based dedupe: new frame must be distinct from ALL selected, not just last."""
    rng = np.random.default_rng(77)
    f1 = (rng.random((40, 40, 3)) * 255).astype(np.uint8)
    f2 = (rng.random((40, 40, 3)) * 255).astype(np.uint8)
    f3 = f1.copy()
    result = dedupe_by_hash([f1, f2, f3], threshold=10)
    assert len(result) == 2
    assert np.array_equal(result[0], f1)
    assert np.array_equal(result[1], f2)


def test_dedupe_indexed_by_hash_set_based():
    """dedupe_indexed_by_hash uses set of hashes."""
    rng = np.random.default_rng(78)
    items = [(i, (rng.random((20, 20, 3)) * 255).astype(np.uint8)) for i in range(5)]
    items[3] = (3, items[0][1].copy())
    out = dedupe_indexed_by_hash(items, threshold=5)
    indices = [idx for idx, _ in out]
    assert len(out) <= 5
    assert (3 in indices) == (len(out) == 5)


# --- paths ---


def test_slug_filesystem_safe():
    assert slug("PALLET_001") == "PALLET_001"
    assert slug("job_abc_E1") == "job_abc_E1"
    assert " " not in slug("hello world")
    assert slug("a/b\\c") == "a_b_c"
    assert slug("") == "entity"
    assert slug("  __  ") == "entity"


def test_entity_evidence_path():
    run_dir = Path("/run")
    assert entity_evidence_path(run_dir, "job_j_E1") == run_dir / "evidence" / "job_j_E1"
    assert entity_evidence_path(run_dir, "PALLET-001") == run_dir / "evidence" / "PALLET-001"


# --- evidence_pack helpers ---


def test_parse_bbox_to_pixels_normalized():
    """Normalized bbox (all <= 1) scaled to frame size."""
    out = parse_bbox_to_pixels([0.25, 0.25, 0.75, 0.75], 100, 100)
    assert out == (25, 25, 75, 75)


def test_parse_bbox_to_pixels_pixel():
    """Pixel bbox (any > 1) used as-is, clamped."""
    out = parse_bbox_to_pixels([10, 20, 50, 80], 100, 100)
    assert out == (10, 20, 50, 80)
    out2 = parse_bbox_to_pixels([-5, 0, 200, 150], 100, 100)
    assert out2 == (0, 0, 100, 100)


def test_parse_bbox_to_pixels_invalid_returns_none():
    """Invalid bbox or empty frame -> None."""
    assert parse_bbox_to_pixels(None, 100, 100) is None
    assert parse_bbox_to_pixels([], 100, 100) is None
    assert parse_bbox_to_pixels([0.1, 0.2], 100, 100) is None
    assert parse_bbox_to_pixels([0.5, 0.2, 0.1, 0.6], 100, 100) is None  # x1 >= x2 degenerate
    assert parse_bbox_to_pixels([0.1, 0.6, 0.5, 0.2], 100, 100) is None  # y1 >= y2 degenerate
    assert parse_bbox_to_pixels([0.1, 0.2, 0.5, 0.6], 0, 100) is None
    assert parse_bbox_to_pixels([0.1, 0.2, 0.5, 0.6], 100, 0) is None


def test_crop_bbox_normalized():
    """Crop from normalized bbox [0.25, 0.25, 0.75, 0.75] on 100x100 frame."""
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
    crop = _crop_bbox(frame, [0.25, 0.25, 0.75, 0.75])
    assert crop is not None
    assert crop.shape == (50, 50, 3)


def test_crop_bbox_pixel():
    """Crop from pixel bbox on frame."""
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
    crop = _crop_bbox(frame, [10, 10, 60, 60])
    assert crop is not None
    assert crop.shape == (50, 50, 3)


def test_select_overview_frames_limit_k():
    rng = np.random.default_rng(99)
    frames = [(rng.random((30, 30, 3)) * 255).astype(np.uint8) for _ in range(10)]
    result = _select_overview_frames(frames, k=3)
    assert len(result) <= 3
    for idx, fr in result:
        assert 0 <= idx < len(frames)
        assert fr.shape == frames[0].shape


# --- LOCALIZED: bbox present ---


def test_evidence_generation_localized():
    """When bbox present: evidence_localization = LOCALIZED, label crops exist."""
    run_dir = Path(tempfile.mkdtemp())
    job_id = "job_test"
    rng = np.random.default_rng(42)
    frames = [(rng.random((80, 80, 3)) * 255).astype(np.uint8) for _ in range(5)]
    metadata = {"fps": 30.0, "frame_indices": list(range(5))}
    entity = Entity(
        entity_uid="job_test_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_label_bbox=[0.1, 0.1, 0.5, 0.4],
        product_label_bbox=[0.5, 0.5, 0.9, 0.9],
    )
    entities = [entity]

    index = generate_evidence_pack(job_id, run_dir, frames, metadata, entities)

    assert entity.evidence_localization == EVIDENCE_LOCALIZED
    assert entity.evidence_path is not None
    assert "evidence" in entity.evidence_path

    assert index["job_id"] == job_id
    assert index["mode"] == "hybrid_v2.1"
    assert len(index["entities"]) == 1
    ent_idx = index["entities"][0]
    assert ent_idx["evidence_localization"] == EVIDENCE_LOCALIZED
    assert "overview" in ent_idx["evidence"]
    assert len(ent_idx["evidence"]["overview"]) > 0
    for p in ent_idx["evidence"]["overview"]:
        assert p.startswith("evidence/") and "/" in p and p.endswith(".jpg")
    assert "position_label_best" in ent_idx["evidence"] or "position_label_candidates" in ent_idx["evidence"]
    assert "product_label_best" in ent_idx["evidence"] or "product_label_candidates" in ent_idx["evidence"]

    entity_dir = run_dir / "evidence" / slug(entity.entity_uid)
    assert entity_dir.exists()
    assert (run_dir / "evidence_index.json").exists()


# --- UNLOCALIZED: bbox missing ---


def test_evidence_generation_unlocalized():
    """When bbox missing: evidence_localization = UNLOCALIZED, only overview."""
    run_dir = Path(tempfile.mkdtemp())
    job_id = "job_test2"
    rng = np.random.default_rng(43)
    frames = [(rng.random((60, 60, 3)) * 255).astype(np.uint8) for _ in range(4)]
    metadata = {"fps": 30.0, "frame_indices": list(range(4))}
    entity = Entity(
        entity_uid="job_test2_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_label_bbox=None,
        product_label_bbox=None,
    )
    entities = [entity]

    index = generate_evidence_pack(job_id, run_dir, frames, metadata, entities)

    assert entity.evidence_localization == EVIDENCE_UNLOCALIZED
    assert entity.evidence_path is not None

    ent_idx = index["entities"][0]
    assert ent_idx["evidence_localization"] == EVIDENCE_UNLOCALIZED
    assert "overview" in ent_idx["evidence"]
    assert ent_idx["evidence"].get("position_label_best") is None or "position_label_best" not in ent_idx["evidence"]
    assert ent_idx["evidence"].get("product_label_best") is None or "product_label_best" not in ent_idx["evidence"]


def test_evidence_unlocalized_when_bbox_invalid():
    """Invalid bbox (e.g. wrong length) -> evidence_localization = UNLOCALIZED, no label crops."""
    run_dir = Path(tempfile.mkdtemp())
    rng = np.random.default_rng(44)
    frames = [(rng.random((50, 50, 3)) * 255).astype(np.uint8) for _ in range(3)]
    entity = Entity(
        entity_uid="job_inv_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_label_bbox=[0.1, 0.2],  # invalid: only 2 coords
        product_label_bbox=None,
    )
    index = generate_evidence_pack("job_inv", run_dir, frames, {}, [entity])
    assert entity.evidence_localization == EVIDENCE_UNLOCALIZED
    assert "overview" in index["entities"][0]["evidence"]
    assert "position_label_best" not in index["entities"][0]["evidence"]


def test_evidence_unlocalized_when_bbox_degenerate():
    """Degenerate bbox (x1==x2 or y1==y2) yields no pixel crop -> UNLOCALIZED, overview only."""
    run_dir = Path(tempfile.mkdtemp())
    frames = [np.ones((100, 100, 3), dtype=np.uint8) * 128]
    entity = Entity(
        entity_uid="job_degen_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_label_bbox=[0.5, 0.5, 0.5, 0.5],
        product_label_bbox=None,
    )
    index = generate_evidence_pack("job_degen", run_dir, frames, {}, [entity])
    assert entity.evidence_localization == EVIDENCE_UNLOCALIZED
    assert "overview" in index["entities"][0]["evidence"]
    assert index["entities"][0]["evidence"].get("position_label_best") is None
    assert "position_label_candidates" not in index["entities"][0]["evidence"] or not index["entities"][0]["evidence"]["position_label_candidates"]


# --- evidence_index.json structure ---


def test_evidence_index_structure():
    """evidence_index.json has job_id, mode, entities[].entity_uid, evidence (paths self-contained)."""
    run_dir = Path(tempfile.mkdtemp())
    entity = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
    )
    frames = [np.ones((40, 40, 3), dtype=np.uint8) * 100]
    index = generate_evidence_pack("job_x", run_dir, frames, {}, [entity])

    assert "job_id" in index
    assert "mode" in index
    assert index["mode"] == "hybrid_v2.1"
    assert "entities" in index
    for e in index["entities"]:
        assert "entity_uid" in e
        assert "pallet_id" in e
        assert "entity_type" in e
        assert "count_status" in e
        assert "evidence_localization" in e
        assert "evidence" in e
        assert "overview" in e["evidence"]
        for path in e["evidence"]["overview"]:
            assert path.startswith("evidence/"), "index paths must be self-contained relative paths"


# --- Max images limit ---


def test_evidence_max_images_respected(monkeypatch):
    """Total images per entity <= EVIDENCE_MAX_IMAGES_PER_PALLET."""
    monkeypatch.setenv("EVIDENCE_MAX_IMAGES_PER_PALLET", "5")
    monkeypatch.setenv("EVIDENCE_K_OVERVIEW", "10")
    # Reload so config picks new env
    import src.config
    src.config.reload_settings()

    run_dir = Path(tempfile.mkdtemp())
    entity = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_label_bbox=[0.1, 0.1, 0.5, 0.5],
        product_label_bbox=[0.5, 0.5, 0.9, 0.9],
    )
    rng = np.random.default_rng(123)
    frames = [(rng.random((50, 50, 3)) * 255).astype(np.uint8) for _ in range(15)]
    index = generate_evidence_pack("job_m", run_dir, frames, {}, [entity])

    ent_ev = index["entities"][0]["evidence"]
    total = len(ent_ev.get("overview", []))
    total += len(ent_ev.get("position_label_candidates", []))
    total += len(ent_ev.get("product_label_candidates", []))
    best_pos = ent_ev.get("position_label_best")
    best_prod = ent_ev.get("product_label_best")
    if best_pos and best_pos not in ent_ev.get("position_label_candidates", []):
        total += 1
    if best_prod and best_prod not in ent_ev.get("product_label_candidates", []):
        total += 1
    assert total <= 5

    # Restore config for other tests
    src.config.reload_settings()


def test_jobs_result_prefer_report_mode():
    """GET /jobs/{id}/result: returned mode is report['mode'] when present, not input.mode."""
    from src.api.routes.jobs import _merge_report_metadata
    report = {"mode": "hybrid_v2.1", "summary": {}, "entities": []}
    out = _merge_report_metadata(report, "job_1", "succeeded", "hybrid", 0.7)
    assert out["mode"] == "hybrid_v2.1"
    report2 = {"summary": {}}
    out2 = _merge_report_metadata(report2, "job_2", "succeeded", "hybrid", 0.5)
    assert out2["mode"] == "hybrid"
