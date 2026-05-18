"""
Stage 3 — Prompt hardening & strict response contract.

Tests:
- validate_global_analysis_structure: valid JSON passes, missing key / bad confidence / total mismatch raise.
- Extra root keys allowed.
- GeminiGlobalAnalyzer raises GlobalAnalysisParsingError / GlobalAnalysisValidationError; valid response passes.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.validation.global_analysis_schema import validate_global_analysis_structure

VALID_PAYLOAD = {
    "total_pallets_detected": 2,
    "pallets": [
        {
            "pallet_id": "P1",
            "has_label": True,
            "internal_code": "10145317",
            "quantity": 15,
            "estimated_visible_boxes": None,
            "confidence": 0.94,
        },
        {
            "pallet_id": "P2",
            "has_label": False,
            "internal_code": None,
            "quantity": None,
            "estimated_visible_boxes": 12,
            "confidence": 0.78,
        },
    ],
}

VALID_V21_JSON = '{"total_entities_detected": 0, "entities": []}'


def test_validate_global_analysis_structure_valid_passes():
    """Valid JSON with required keys and types passes validation."""
    validate_global_analysis_structure(VALID_PAYLOAD)


def test_validate_global_analysis_structure_extra_root_keys_allowed():
    """Extra root keys are allowed and do not fail validation."""
    data = {**VALID_PAYLOAD, "extra_key": "ignored", "another": 123}
    validate_global_analysis_structure(data)


def test_validate_global_analysis_structure_missing_total_raises():
    """Missing required key total_pallets_detected raises GlobalAnalysisValidationError."""
    data = {"pallets": []}
    with pytest.raises(GlobalAnalysisValidationError, match="total_pallets_detected"):
        validate_global_analysis_structure(data)


def test_validate_global_analysis_structure_missing_pallets_raises():
    """Missing required key pallets raises GlobalAnalysisValidationError."""
    data = {"total_pallets_detected": 0}
    with pytest.raises(GlobalAnalysisValidationError, match="pallets"):
        validate_global_analysis_structure(data)


def test_validate_global_analysis_structure_confidence_out_of_range_raises():
    """confidence outside [0, 1] raises GlobalAnalysisValidationError."""
    data = {
        "total_pallets_detected": 1,
        "pallets": [
            {
                "pallet_id": "P1",
                "has_label": False,
                "confidence": 1.5,
            },
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="0, 1"):
        validate_global_analysis_structure(data)


def test_validate_global_analysis_structure_total_mismatch_raises():
    """total_pallets_detected != len(pallets) raises GlobalAnalysisValidationError."""
    data = {
        "total_pallets_detected": 3,
        "pallets": [
            {
                "pallet_id": "P1",
                "has_label": False,
                "confidence": 0.9,
            },
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="must equal"):
        validate_global_analysis_structure(data)


def test_validate_global_analysis_structure_not_dict_raises():
    """Non-dict root raises GlobalAnalysisValidationError."""
    with pytest.raises(GlobalAnalysisValidationError, match="JSON object"):
        validate_global_analysis_structure([])


def test_analyzer_valid_response_passes():
    """Analyzer returns data when Gemini returns valid JSON that passes validation."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = VALID_V21_JSON
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((50, 50, 3), dtype=np.uint8)]

    result = analyzer.analyze_video_frames(one_frame, frame_refs=["img_001"])

    assert result["total_entities_detected"] == 0
    assert result["entities"] == []


def test_analyzer_invalid_json_raises_parsing_error():
    """Analyzer raises GlobalAnalysisParsingError when response is not valid JSON."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = "not json at all"
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((50, 50, 3), dtype=np.uint8)]

    with pytest.raises(GlobalAnalysisParsingError, match="Invalid JSON"):
        analyzer.analyze_video_frames(one_frame, frame_refs=["img_001"])


def test_analyzer_invalid_structure_raises_validation_error():
    """Analyzer raises GlobalAnalysisValidationError when JSON is valid but structure fails."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = '{"total_entities_detected": 1}'
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((50, 50, 3), dtype=np.uint8)]

    with pytest.raises(GlobalAnalysisValidationError, match="entities"):
        analyzer.analyze_video_frames(one_frame, frame_refs=["img_001"])


def test_analyzer_uses_provided_logger_for_all_logs():
    """When logger= is passed, analyzer uses it for info and warning (not module logger)."""
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = VALID_V21_JSON
    mock_logger = MagicMock()
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((50, 50, 3), dtype=np.uint8)]

    analyzer.analyze_video_frames(one_frame, frame_refs=["img_001"], logger=mock_logger)

    mock_logger.info.assert_called_once()
    call_args = mock_logger.info.call_args[0]
    assert "Enviando" in call_args[0]
    assert "interleaved" in call_args[0].lower()
    assert call_args[-1] == 1  # primary frame count
