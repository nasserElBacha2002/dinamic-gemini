"""Unit tests for the Phase 3 CodeScanProcessingStrategy (fake scanner, no pyzbar)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.image_processing.code_detection_consolidator import (
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.code_scans.entities import CodeScanDetectionStatus, CodeType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)


class FakeCodeScanner:
    engine_name = "fake"

    def __init__(self, candidates: list[CodeScanDetectionCandidate] | Exception) -> None:
        self._candidates = candidates

    def scan_asset(self, asset, content=None):
        if isinstance(self._candidates, Exception):
            raise self._candidates
        return list(self._candidates)


class FakeReader:
    def __init__(self, content: bytes | Exception = b"bytes") -> None:
        self._content = content

    def read_image_bytes(self, asset) -> bytes:
        if isinstance(self._content, Exception):
            raise self._content
        return self._content


def _candidate(value: str, code_type: CodeType = CodeType.QR) -> CodeScanDetectionCandidate:
    return CodeScanDetectionCandidate(
        code_type=code_type,
        code_value=value,
        detection_status=CodeScanDetectionStatus.DETECTED,
        bounding_box_json={"left": 1, "top": 2, "width": 3, "height": 4},
        metadata_json={"pyzbar_type": "QRCODE"},
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="asset1.jpg",
        storage_path="/asset1.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _context() -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="job1",
        asset_id="asset1",
        aisle_id="a1",
        inventory_id="inv1",
        client_id=None,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
    )


def _strategy(scanner, reader) -> CodeScanProcessingStrategy:
    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=reader,
        parser=EncodedLabelPayloadParser(quantity_max=99999999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=99999999, enable_rotations=False),
    )


def test_resolved_internal_with_hashed_evidence() -> None:
    strategy = _strategy(FakeCodeScanner([_candidate("ABC|5")]), FakeReader())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "ABC"
    assert result.quantity == 5.0
    assert result.execution_scope is ExecutionScope.SINGLE_ASSET
    assert result.logical_asset_attempt is False
    assert result.evidence["symbology"] == "QR_CODE"
    assert result.evidence["raw_value_hash"] == hashlib.sha256(b"ABC|5").hexdigest()
    # No raw payload leaked into evidence.
    assert "ABC|5" not in str(result.evidence)


def test_unrecognized_when_no_detection() -> None:
    strategy = _strategy(FakeCodeScanner([]), FakeReader())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.UNRECOGNIZED


def test_missing_quantity_is_manual_review() -> None:
    strategy = _strategy(FakeCodeScanner([_candidate("PLAINCODE")]), FakeReader())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.internal_code == "PLAINCODE"


def test_multiple_distinct_codes_is_manual_review() -> None:
    strategy = _strategy(
        FakeCodeScanner([_candidate("ABC|5"), _candidate("XYZ|3")]), FakeReader()
    )
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code == "MULTIPLE_DISTINCT_CODES"


def test_missing_file_is_failed_technical() -> None:
    strategy = _strategy(FakeCodeScanner([]), FakeReader(FileNotFoundError("nope")))
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "SOURCE_ASSET_NOT_FOUND"


def test_scanner_error_is_failed_technical() -> None:
    strategy = _strategy(FakeCodeScanner(ValueError("boom")), FakeReader())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "CODE_SCAN_SCANNER_ERROR"


def test_programming_error_from_scanner_propagates() -> None:
    strategy = _strategy(FakeCodeScanner(RuntimeError("boom")), FakeReader())
    with pytest.raises(RuntimeError, match="boom"):
        strategy.process(_context(), _asset())
