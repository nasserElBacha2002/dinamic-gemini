"""Phase 4.4 hotfix — execution_log JSON safety and runtime metadata redaction."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
from google.genai import types
from PIL import Image

from src.pipeline.execution_log import ExecutionLogWriter, validate_execution_log_jsonl_file
from src.pipeline.execution_log_sanitizer import (
    REDACTED_RUNTIME_OBJECT_KEY,
    make_json_safe_for_execution_log,
)
from src.pipeline.llm_metadata_json_safety import (
    assert_metadata_json_serializable,
    sanitize_llm_metadata,
)


def test_ndarray_redacted_with_shape() -> None:
    arr = np.zeros((2, 3, 4), dtype=np.uint8)
    safe = make_json_safe_for_execution_log({"image": arr})
    assert isinstance(safe, dict)
    redacted = safe["image"]
    assert redacted[REDACTED_RUNTIME_OBJECT_KEY] == "ndarray"
    assert redacted["shape"] == [2, 3, 4]
    json.dumps(safe)


def test_pil_image_redacted() -> None:
    img = Image.new("RGB", (8, 6))
    safe = make_json_safe_for_execution_log({"ref": img})
    assert safe["ref"]["mode"] == "RGB"
    assert safe["ref"]["size"] == [8, 6]
    json.dumps(safe)


def test_bytes_redacted_without_content() -> None:
    safe = make_json_safe_for_execution_log({"blob": b"secret"})
    assert safe["blob"]["byte_length"] == 6
    assert "secret" not in json.dumps(safe)


def test_gemini_part_redacted() -> None:
    part = types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png")
    safe = make_json_safe_for_execution_log({"part": part})
    assert safe["part"][REDACTED_RUNTIME_OBJECT_KEY] == "Part"
    json.dumps(safe)


def test_runtime_metadata_keys_redacted() -> None:
    safe = make_json_safe_for_execution_log(
        {
            "_serialized_multimodal_payload": object(),
            "_provider_execution_request_object": {"nested": np.zeros((1, 1))},
        }
    )
    assert REDACTED_RUNTIME_OBJECT_KEY in safe["_serialized_multimodal_payload"]
    json.dumps(safe)


def test_sanitize_llm_metadata_json_serializable() -> None:
    meta = sanitize_llm_metadata(
        {
            "frames_sent_ids": ["img_001"],
            "leak": np.zeros((2, 2, 3)),
            "_serialized_multimodal_payload": object(),
        }
    )
    assert_metadata_json_serializable(meta)
    assert "_serialized_multimodal_payload" not in meta or isinstance(
        meta.get("_serialized_multimodal_payload"), dict
    )


def test_execution_log_writer_publishes_safe_analysis_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        writer = ExecutionLogWriter(run_dir)
        writer.info(
            "AnalysisStage",
            "Analysis request finished",
            payload={
                "provider": "gemini",
                "multimodal_order": [{"manifest_entry_id": "IMG_001", "kind": "primary_evidence"}],
                "runtime_leak": np.zeros((4, 4, 3)),
                "_serialized_multimodal_payload": object(),
            },
        )
        validate_execution_log_jsonl_file(writer.path)
        line = json.loads(writer.path.read_text(encoding="utf-8").strip())
        assert line["payload"]["runtime_leak"][REDACTED_RUNTIME_OBJECT_KEY] == "ndarray"


def test_execution_log_staging_regression_five_photo_metadata() -> None:
    """Simulate post-analysis metadata shape; file must stage as valid JSONL."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        writer = ExecutionLogWriter(run_dir)
        metadata = sanitize_llm_metadata(
            {
                "provider_image_manifest_order": [
                    {
                        "provider_position": 0,
                        "manifest_entry_id": "IMG_001",
                        "source_image_id": "img_001",
                        "role": "primary_evidence",
                    }
                ],
                "multimodal_order": [
                    {
                        "manifest_entry_id": "IMG_001",
                        "source_image_id": "img_001",
                        "kind": "primary_evidence",
                    }
                ],
                "frames_sent_ids": ["img_001"],
                "prompt_composition": {
                    "execution_image_manifest": {"version": 1, "entries": []},
                },
            }
        )
        writer.info(
            "AnalysisStage",
            "Analysis request prepared",
            payload={
                "event_type": "analysis_request",
                "provider": "gemini",
                **{k: metadata[k] for k in ("frames_sent_ids", "multimodal_order")},
                "prompt_composition": metadata.get("prompt_composition"),
            },
        )
        validate_execution_log_jsonl_file(run_dir / "execution_log.jsonl")
