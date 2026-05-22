"""Epic 3.1.A — Backend image identity and prompt enrichment.

Tests: image_id generation, manifest registration, load_job_images_from_manifest,
enrich_prompt_with_image_ids, PhotosFrameSource frame_ref (image_id vs fallback),
and provider using request.prompt. No traceability parsing or response validation.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.frames.sources.photos_source import PhotosFrameSource
from src.jobs.image_identity import (
    JobImage,
    generate_image_id,
    load_job_images_from_manifest,
)
from src.jobs.models import JobInput
from src.llm.prompts import enrich_prompt_with_image_ids, get_hybrid_prompt

# ---------- generate_image_id ----------


def test_generate_image_id_format():
    """image_id is img_NNN with 1-based index, zero-padded to 3 digits."""
    assert generate_image_id(1) == "img_001"
    assert generate_image_id(2) == "img_002"
    assert generate_image_id(10) == "img_010"
    assert generate_image_id(999) == "img_999"


def test_generate_image_id_rejects_zero():
    """upload_order 0 raises ValueError (strict 1-based)."""
    with pytest.raises(ValueError, match="must be >= 1"):
        generate_image_id(0)


def test_generate_image_id_rejects_negative():
    """upload_order < 1 raises ValueError."""
    with pytest.raises(ValueError, match="must be >= 1"):
        generate_image_id(-1)


def test_generate_image_id_rejects_non_int():
    """upload_order must be int."""
    with pytest.raises(ValueError, match="must be an int"):
        generate_image_id(1.0)


# ---------- load_job_images_from_manifest ----------


def test_load_job_images_from_manifest_with_image_id(tmp_path):
    """When manifest has image_id per photo, returns List[JobImage] with correct upload_order."""
    manifest = {
        "input_type": "photos",
        "photos": [
            {
                "index": 1,
                "image_id": "img_001",
                "original_filename": "a.jpg",
                "stored_filename": "0001_a.jpg",
            },
            {
                "index": 2,
                "image_id": "img_002",
                "original_filename": "b.jpg",
                "stored_filename": "0002_b.jpg",
            },
        ],
    }
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = load_job_images_from_manifest(path, "run/input_photos")

    assert len(result) == 2
    assert result[0].image_id == "img_001"
    assert result[0].original_filename == "a.jpg"
    assert result[0].upload_order == 1
    assert result[0].storage_path == "run/input_photos/0001_a.jpg"
    assert result[1].image_id == "img_002"
    assert result[1].upload_order == 2


def test_load_job_images_from_manifest_skips_entries_without_image_id(tmp_path):
    """Entries without image_id are skipped (Epic A expects image_id in manifest)."""
    manifest = {
        "input_type": "photos",
        "photos": [
            {"index": 1, "original_filename": "a.jpg", "stored_filename": "0001_a.jpg"},
            {
                "index": 2,
                "image_id": "img_002",
                "original_filename": "b.jpg",
                "stored_filename": "0002_b.jpg",
            },
        ],
    }
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = load_job_images_from_manifest(path, "run/input_photos")

    assert len(result) == 1
    assert result[0].image_id == "img_002"


def test_load_job_images_from_manifest_missing_file_returns_empty():
    """When manifest path does not exist, returns empty list."""
    result = load_job_images_from_manifest(Path("/nonexistent/manifest.json"), "run/input_photos")
    assert result == []


def test_load_job_images_from_manifest_non_photos_returns_empty(tmp_path):
    """When input_type is not 'photos', returns empty list."""
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps({"input_type": "video"}), encoding="utf-8")
    result = load_job_images_from_manifest(path, "run/input_photos")
    assert result == []


def test_load_job_images_from_manifest_upload_order_1based(tmp_path):
    """upload_order is always 1-based; legacy index 0 yields position-based order."""
    manifest = {
        "input_type": "photos",
        "photos": [
            {
                "index": 0,
                "image_id": "img_001",
                "original_filename": "a.jpg",
                "stored_filename": "0001_a.jpg",
            },
            {
                "index": 0,
                "image_id": "img_002",
                "original_filename": "b.jpg",
                "stored_filename": "0002_b.jpg",
            },
        ],
    }
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = load_job_images_from_manifest(path, "run/input_photos")
    assert len(result) == 2
    assert result[0].upload_order == 1
    assert result[1].upload_order == 2


def test_load_job_images_from_manifest_skips_duplicate_image_id(tmp_path):
    """Duplicate image_id in manifest: first kept, second skipped (with warning)."""
    manifest = {
        "input_type": "photos",
        "photos": [
            {
                "index": 1,
                "image_id": "img_001",
                "original_filename": "a.jpg",
                "stored_filename": "0001_a.jpg",
            },
            {
                "index": 2,
                "image_id": "img_001",
                "original_filename": "b.jpg",
                "stored_filename": "0002_b.jpg",
            },
        ],
    }
    path = tmp_path / "input_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = load_job_images_from_manifest(path, "run/input_photos")
    assert len(result) == 1
    assert result[0].image_id == "img_001"


# ---------- enrich_prompt_with_image_ids ----------


def test_enrich_prompt_with_image_ids_appends_list_and_instruction():
    """Enriched prompt contains image list and traceability instruction; upload_order 1-based."""
    base = "Analyze the frames."
    images = [
        JobImage("img_001", "a.jpg", 1, "run/input_photos/0001_a.jpg"),
        JobImage("img_002", "b.jpg", 2, "run/input_photos/0002_b.jpg"),
    ]
    out = enrich_prompt_with_image_ids(base, images)
    assert "Analyze the frames." in out
    assert "img_001" in out
    assert "img_002" in out
    assert "upload_order=1" in out
    assert "original_filename='a.jpg'" in out
    assert "source_image_id" in out
    assert "Do not invent IDs" in out


def test_enrich_prompt_with_image_ids_empty_list_returns_unchanged():
    """When images is empty, base prompt is returned unchanged."""
    base = "Analyze the frames."
    assert enrich_prompt_with_image_ids(base, []) == base


# ---------- photos_handler manifest contains image_id ----------


def test_persist_photos_from_uploads_writes_image_id_in_manifest(tmp_path):
    """persist_photos_from_uploads writes image_id per photo in manifest."""
    import asyncio

    from src.api.photos_handler import persist_photos_from_uploads

    img = np.zeros((64, 64, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    raw = buf.tobytes()

    class FakeUpload:
        def __init__(self, filename: str, data: bytes):
            self.filename = filename
            self._data = data
            self._read = False

        async def read(self, size: int = 1024 * 1024):
            if self._read:
                return b""
            self._read = True
            return self._data

    uploads = [
        FakeUpload("one.jpg", raw),
        FakeUpload("two.jpg", raw),
    ]

    async def run():
        return await persist_photos_from_uploads(
            tmp_path, uploads, max_total_bytes=10 * 1024 * 1024
        )

    manifest, manifest_rel, photos_rel = asyncio.run(run())

    assert manifest["input_type"] == "photos"
    assert len(manifest["photos"]) == 2
    assert manifest["photos"][0]["image_id"] == "img_001"
    assert manifest["photos"][0]["upload_order"] == 1
    assert manifest["photos"][0]["original_filename"] == "one.jpg"
    assert manifest["photos"][1]["image_id"] == "img_002"
    assert manifest["photos"][1]["upload_order"] == 2
    assert manifest["photos"][1]["original_filename"] == "two.jpg"

    manifest_path = tmp_path / "run" / "input_manifest.json"
    assert manifest_path.exists()
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["photos"][0]["image_id"] == "img_001"
    assert loaded["photos"][1]["image_id"] == "img_002"


# ---------- PhotosFrameSource frame_ref: image_id vs fallback ----------


def test_photos_frame_source_uses_image_id_when_present(tmp_path):
    """When manifest has image_id, frame_refs are those image_ids."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "photos": [
            {"index": 1, "image_id": "img_001", "stored_filename": "0001_a.jpg"},
            {"index": 2, "image_id": "img_002", "stored_filename": "0002_b.jpg"},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    cv2.imwrite(str(photos_dir / "0002_b.jpg"), img)

    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    bundle = source.get_frames("job_1", run_dir, job_input)

    assert bundle.frame_refs == ["img_001", "img_002"]


def test_photos_frame_source_fallback_when_no_image_id(tmp_path):
    """When manifest has no image_id, frame_refs fall back to photo_0001, photo_0002."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    photos_dir = run_dir / "input_photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "total_photos": 2,
        "photos": [
            {"index": 1, "stored_filename": "0001_a.jpg"},
            {"index": 2, "stored_filename": "0002_b.jpg"},
        ],
    }
    (run_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    cv2.imwrite(str(photos_dir / "0001_a.jpg"), img)
    cv2.imwrite(str(photos_dir / "0002_b.jpg"), img)

    job_input = JobInput(video_path="", input_type="photos")
    source = PhotosFrameSource()
    bundle = source.get_frames("job_1", run_dir, job_input)

    assert bundle.frame_refs == ["photo_0001", "photo_0002"]


# ---------- GeminiProvider uses request.prompt ----------


def test_gemini_provider_uses_request_prompt_when_provided():
    """When request.prompt is non-empty, GeminiProvider passes it to the analyzer."""
    from src.llm.providers.gemini_provider import GeminiProvider
    from src.llm.types import LLMRequest

    settings = MagicMock()
    settings.gemini_api_key = "test-key"
    settings.gemini_model_name = "gemini-2.0-flash-exp"
    settings.gemini_max_retries = 1
    settings.gemini_retry_delay = 0.1

    img = np.zeros((64, 64, 3), dtype=np.uint8)
    custom_prompt = "CUSTOM_PROMPT_MARKER_XYZ"
    request = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt=custom_prompt,
        schema_version="v2.1",
        metadata={},
        frames_nd=[img],
    )

    with (
        patch("src.llm.gemini_sdk_adapter.GeminiClient") as mock_client_cls,
        patch("src.llm.gemini_sdk_adapter.GeminiGlobalAnalyzer") as analyzer_cls,
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        inst = MagicMock()
        inst.analyze_video_frames.return_value = {"total_entities_detected": 0, "entities": []}
        analyzer_cls.return_value = inst

        provider = GeminiProvider(settings)
        response = provider.analyze_global(request)

    assert response.provider == "gemini"
    kwargs = analyzer_cls.call_args.kwargs
    assert kwargs.get("prompt_text") == custom_prompt


def test_gemini_provider_fallback_to_hybrid_prompt_when_request_prompt_empty():
    """When request.prompt is empty, Gemini uses compose_hybrid_base_from_settings (always v22)."""
    from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
    from src.llm.providers.gemini_provider import GeminiProvider
    from src.llm.types import LLMRequest

    settings = MagicMock()
    settings.gemini_api_key = "test-key"
    settings.gemini_model_name = "gemini-2.0-flash-exp"
    settings.gemini_max_retries = 1
    settings.gemini_retry_delay = 0.1
    settings.hybrid_prompt = "global_v21"

    img = np.zeros((64, 64, 3), dtype=np.uint8)
    request = LLMRequest(
        job_id="j1",
        frames=[],
        frame_refs=[],
        prompt="",
        schema_version="v2.1",
        metadata={},
        frames_nd=[img],
    )

    with (
        patch("src.llm.gemini_sdk_adapter.GeminiClient") as mock_client_cls,
        patch("src.llm.gemini_sdk_adapter.GeminiGlobalAnalyzer") as analyzer_cls,
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        inst = MagicMock()
        inst.analyze_video_frames.return_value = {"total_entities_detected": 0, "entities": []}
        analyzer_cls.return_value = inst

        provider = GeminiProvider(settings)
        provider.analyze_global(request)

    kwargs = analyzer_cls.call_args.kwargs
    passed_prompt = kwargs.get("prompt_text") or ""
    assert "Analyze the provided warehouse aisle evidence" in passed_prompt
    expected = compose_hybrid_base_from_settings(settings, pipeline_provider_key=None)
    assert passed_prompt == expected
    assert passed_prompt == get_hybrid_prompt("global_v22")
    assert "Label-first" in passed_prompt
