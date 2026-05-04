"""Epic 5 — Backend: optional source_image_original_filename in API, report, and export.

Tests: build_hybrid_report with source_image_filename_map; write_report_csv column;
list_entities exposes source_image_original_filename; backward compatibility when absent.
Corrections-scoped: public path helper, legacy behavior (new reports only), CSV contract,
video job (no map), entity with source_image_id not in map.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.domain.entity import Entity
from src.jobs.models import JobInput
from src.jobs.photos_paths import photos_dir_relative_for_manifest, resolve_manifest_path
from src.pipeline.context.run_context import RunContext
from src.pipeline.stages.reporting_stage import ReportingStage, ReportingStageInput
from src.reporting.artifacts import write_report_csv
from src.reporting.hybrid_report import build_hybrid_report

# ---------- build_hybrid_report source_image_original_filename ----------


def test_resolve_manifest_path_default():
    """Public helper: default manifest path is run_dir/input_manifest.json when job_input has no path."""
    run_dir = Path("/tmp/job_123/run")
    job_input = JobInput(input_type="photos")
    assert resolve_manifest_path(run_dir, job_input) == run_dir / "input_manifest.json"


def test_resolve_manifest_path_custom():
    """Public helper: custom input_manifest_path is resolved relative to job dir (run_dir.parent)."""
    run_dir = Path("/tmp/job_123/run")
    job_input = JobInput(input_type="photos", input_manifest_path="run/input_manifest.json")
    assert resolve_manifest_path(run_dir, job_input) == Path("/tmp/job_123/run/input_manifest.json")


def test_photos_dir_relative_for_manifest_default():
    """Public helper: default photos_dir relative string is run/input_photos."""
    job_input = JobInput(input_type="photos")
    assert photos_dir_relative_for_manifest(job_input) == "run/input_photos"


def test_photos_dir_relative_for_manifest_custom():
    """Public helper: custom photos_dir from job_input is returned as-is."""
    job_input = JobInput(input_type="photos", photos_dir="run/input_photos")
    assert photos_dir_relative_for_manifest(job_input) == "run/input_photos"


def test_no_private_helper_in_reporting_stage():
    """ReportingStage must use public path helpers from jobs.photos_paths, not private helpers from photos_source."""
    import inspect

    import src.pipeline.stages.reporting_stage as reporting_stage_module

    source = inspect.getsource(reporting_stage_module)
    assert "photos_paths" in source and "resolve_manifest_path" in source
    assert "photos_source" not in source
    assert "_resolve_manifest_path" not in source


def test_reporting_stage_video_job_no_source_image_original_filename(tmp_path):
    """Video job: no filename map is built; report entities have no source_image_original_filename."""
    run_dir = tmp_path / "job_v" / "run"
    run_dir.mkdir(parents=True)
    job_input = JobInput(input_type="video", video_path="/tmp/v.mp4")
    context = RunContext(
        job_id="job_v",
        run_id="run_1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=MagicMock(),
        logger=MagicMock(),
    )
    entities = [
        Entity("u1", "PALLET", "m1", source_image_id="img_001"),
    ]
    data = ReportingStageInput(
        entities=entities,
        frames_count=5,
        frame_indices=None,
        video_path_for_report="/tmp/v.mp4",
    )
    stage = ReportingStage()
    result = stage.run(context, data)
    assert "entities" in result.report
    assert len(result.report["entities"]) == 1
    assert result.report["entities"][0].get("source_image_original_filename") is None
    assert result.report["entities"][0]["source_image_id"] == "img_001"


def test_build_hybrid_report_with_filename_map_sets_source_image_original_filename():
    """When source_image_filename_map is provided and entity has source_image_id, entity dict gets source_image_original_filename."""
    entities = [
        Entity("u1", "PALLET", "m1", source_image_id="img_001"),
        Entity("u2", "PALLET", "m2", source_image_id="img_002"),
        Entity("u3", "PALLET", "m3", source_image_id=None),
    ]
    filename_map = {"img_001": "photo_a.jpg", "img_002": "photo_b.png"}
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=5,
        source_image_filename_map=filename_map,
    )
    entity_dicts = report["entities"]
    assert len(entity_dicts) == 3
    assert entity_dicts[0]["source_image_id"] == "img_001"
    assert entity_dicts[0]["source_image_original_filename"] == "photo_a.jpg"
    assert entity_dicts[1]["source_image_id"] == "img_002"
    assert entity_dicts[1]["source_image_original_filename"] == "photo_b.png"
    assert entity_dicts[2]["source_image_id"] is None
    assert entity_dicts[2].get("source_image_original_filename") is None


def test_build_hybrid_report_without_map_omits_source_image_original_filename():
    """When source_image_filename_map is not passed, entity dicts do not get source_image_original_filename (or None)."""
    entities = [
        Entity("u1", "PALLET", "m1", source_image_id="img_001"),
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=5,
    )
    entity_dicts = report["entities"]
    assert len(entity_dicts) == 1
    assert entity_dicts[0]["source_image_id"] == "img_001"
    assert entity_dicts[0].get("source_image_original_filename") is None


def test_build_hybrid_report_map_missing_id_returns_none():
    """When source_image_id is not in the map, source_image_original_filename is None."""
    entities = [
        Entity("u1", "PALLET", "m1", source_image_id="img_999"),
    ]
    filename_map = {"img_001": "photo_a.jpg"}
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=5,
        source_image_filename_map=filename_map,
    )
    entity_dicts = report["entities"]
    assert entity_dicts[0]["source_image_id"] == "img_999"
    assert entity_dicts[0].get("source_image_original_filename") is None


# ---------- write_report_csv source_image_original_filename ----------


def test_write_report_csv_includes_source_image_original_filename_column():
    """CSV has header and row value for source_image_original_filename (Epic 5)."""
    report = {
        "entities": [
            {
                "entity_uid": "e1",
                "pallet_id": "P01",
                "entity_type": "PALLET",
                "count_status": "COUNTED",
                "final_quantity": 10,
                "internal_code": "SKU1",
                "confidence": 0.9,
                "source_image_id": "img_001",
                "traceability_status": "valid",
                "source_image_original_filename": "uploaded_photo.jpg",
            },
            {
                "entity_uid": "e2",
                "pallet_id": "P02",
                "entity_type": "PALLET",
                "count_status": "NEEDS_REVIEW",
                "final_quantity": None,
                "internal_code": "SKU2",
                "confidence": 0.7,
                "source_image_id": None,
                "traceability_status": "missing",
                "source_image_original_filename": None,
            },
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.csv"
        write_report_csv(path, report)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "source_image_original_filename" in content
        assert "uploaded_photo.jpg" in content
        lines = content.strip().splitlines()
        assert len(lines) == 3
        header = lines[0]
        assert "source_image_original_filename" in header


def test_write_report_csv_empty_entities_has_epic5_header():
    """Empty entities list still writes header including source_image_original_filename."""
    report = {"entities": []}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.csv"
        write_report_csv(path, report)
        line = path.read_text(encoding="utf-8").strip()
        assert "source_image_original_filename" in line


def test_write_report_csv_backward_compat_no_source_image_original_filename():
    """Entities without source_image_original_filename get empty cell (backward compat)."""
    report = {
        "entities": [
            {
                "entity_uid": "e1",
                "pallet_id": "P01",
                "entity_type": "PALLET",
                "count_status": "COUNTED",
                "final_quantity": 5,
                "internal_code": "X",
                "confidence": 0.8,
                "source_image_id": "img_001",
            },
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.csv"
        write_report_csv(path, report)
        content = path.read_text(encoding="utf-8")
        assert "e1" in content
        assert "source_image_original_filename" in content
        lines = content.strip().splitlines()
        assert len(lines) == 2


# ---------- list_entities API source_image_original_filename ----------


# v1 list_entities tests removed in Stage 3; v3 positions expose source_image_original_filename
