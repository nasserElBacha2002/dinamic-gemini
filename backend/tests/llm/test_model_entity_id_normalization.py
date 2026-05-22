"""OpenAI / shared repair of missing or duplicate model_entity_id before v2.1 validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np

from src.llm.normalization.model_entity_id import normalize_model_entity_ids
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter, _openai_parse_validate_global_analysis_json
from src.llm.types import LLMRequest
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21


def _entity(**kwargs: object) -> dict:
    base = {
        "entity_type": "PALLET",
        "confidence": 0.9,
        "has_boxes": True,
    }
    base.update(kwargs)
    return base


def test_null_model_entity_id_repaired_to_e1() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [_entity(model_entity_id=None, source_image_id="img_001")],
    }
    out, diagnostics = normalize_model_entity_ids(data)
    assert out["entities"][0]["model_entity_id"] == "E1"
    assert diagnostics
    assert diagnostics[0].index == 0
    validate_global_analysis_structure_v21(out)


def test_missing_model_entity_id_repaired() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [_entity(source_image_id="img_001")],
    }
    out, diagnostics = normalize_model_entity_ids(data)
    assert out["entities"][0]["model_entity_id"] == "E1"
    assert diagnostics
    assert diagnostics[0].index == 0
    validate_global_analysis_structure_v21(out)


def test_empty_string_model_entity_id_repaired() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [_entity(model_entity_id="", source_image_id="img_001")],
    }
    out, _ = normalize_model_entity_ids(data)
    assert out["entities"][0]["model_entity_id"] == "E1"
    validate_global_analysis_structure_v21(out)


def test_existing_model_entity_id_preserved() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [_entity(model_entity_id="CUSTOM_7")],
    }
    out, diagnostics = normalize_model_entity_ids(data)
    assert out["entities"][0]["model_entity_id"] == "CUSTOM_7"
    assert diagnostics == []


def test_duplicate_model_entity_id_repaired() -> None:
    data = {
        "total_entities_detected": 2,
        "entities": [
            _entity(model_entity_id="E1"),
            _entity(model_entity_id="E1"),
        ],
    }
    out, diagnostics = normalize_model_entity_ids(data)
    ids = [e["model_entity_id"] for e in out["entities"]]
    assert ids == ["E1", "E2"]
    assert any(d.kind == "duplicated" for d in diagnostics)
    validate_global_analysis_structure_v21(out)


def test_openai_adapter_accepts_null_model_entity_id() -> None:
    adapter = OpenAiSdkAdapter()
    settings = MagicMock()
    settings.openai_api_key = "sk-test"
    settings.openai_model = "gpt-4o"
    settings.openai_request_timeout_sec = 60.0
    settings.openai_vision_max_image_side = 2048
    settings.hybrid_prompt = "global_v21"

    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": None,
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "img_001",
            }
        ],
    }
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content=json.dumps(payload)))
    ]
    mock_completion.usage = None

    req = LLMRequest(
        job_id="job-openai-null-mid",
        frames=[],
        frame_refs=["img_001"],
        prompt="p",
        schema_version="v2.1",
        metadata={},
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )

    with patch("src.llm.openai_sdk_adapter.OpenAI") as client_cls:
        client_inst = MagicMock()
        client_inst.chat.completions.create.return_value = mock_completion
        client_cls.return_value = client_inst
        out = adapter.execute(req, settings)

    assert out.parsed_json["entities"][0]["model_entity_id"] == "E1"
    assert out.usage.get("model_entity_id_repair_warnings")


def test_repair_does_not_invent_business_fields() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [_entity(model_entity_id=None)],
    }
    out, diagnostics = normalize_model_entity_ids(data)
    ent = out["entities"][0]
    assert ent["model_entity_id"] == "E1"
    assert diagnostics and diagnostics[0].kind == "missing"
    assert set(ent.keys()) <= {"entity_type", "confidence", "has_boxes", "model_entity_id"}
    assert "source_image_id" not in ent
    assert "internal_code" not in ent
    assert "product_label_quantity" not in ent


def test_openai_parse_validate_regression_null_mid() -> None:
    raw = json.dumps(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "model_entity_id": None,
                    "confidence": 0.9,
                    "has_boxes": True,
                }
            ],
        }
    )
    data, warnings = _openai_parse_validate_global_analysis_json(
        raw, prov="openai", v=OpenAiSdkAdapter()._v, job_id="j-reg"
    )
    assert data["entities"][0]["model_entity_id"] == "E1"
    assert warnings and "index 0" in warnings[0]
